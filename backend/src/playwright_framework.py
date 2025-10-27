"""
Tool-calling framework for async Python Playwright with remote browser control.

This module provides an abstraction layer over Playwright for LLM agents to control
browsers and generate test scripts.
"""

import asyncio
import base64
import os
from typing import Optional, Any, Callable, Literal
import json
from pydantic import BaseModel, Field
from playwright.async_api import async_playwright, Browser, Page, BrowserContext
from src.vision_labeler import VisionLabeler, ElementInfo


class ToolParameter(BaseModel):
    """Defines a parameter for a tool."""
    name: str = Field(..., description="Parameter name")
    type: Literal["string", "number", "boolean", "object", "array"] = Field(
        ..., description="Parameter type"
    )
    description: str = Field(..., description="Parameter description")
    required: bool = Field(True, description="Whether parameter is required")
    enum: Optional[list[str]] = Field(None, description="Allowed values for the parameter")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    
    model_config = {"extra": "forbid"}
    
    def to_dict(self) -> dict:
        """Convert to dictionary format for LLM tool schema."""
        schema = {
            "type": self.type,
            "description": self.description
        }
        if self.enum:
            schema["enum"] = self.enum
        if self.default is not None:
            schema["default"] = self.default
        return schema


class Tool(BaseModel):
    """Defines a tool/function that can be called by an LLM agent."""
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    parameters: list[ToolParameter] = Field(..., description="Tool parameters")
    handler: Any = Field(..., description="Async callable handler function")
    
    model_config = {"arbitrary_types_allowed": True, "extra": "forbid"}
    
    def to_function_declaration(self) -> dict:
        """Convert to Gemini function declaration format."""
        properties = {}
        required = []
        
        for param in self.parameters:
            properties[param.name] = param.to_dict()
            if param.required:
                required.append(param.name)
        
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }


class PlaywrightToolkit:
    """
    Toolkit providing Playwright browser control functions for LLM agents.
    Manages browser lifecycle and provides tool definitions.
    """
    
    def __init__(
        self, 
        headless: bool = False, 
        browser_type: str = "chromium", 
        use_vision: bool = True,
        screenshot_dir: str = "screenshots",
        target_output_path: Optional[str] = None
    ):
        self.headless = headless
        self.browser_type = browser_type
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # Test script being generated (full content as string)
        self.test_script_content: str = ""
        self.script_file_path: Optional[str] = None
        
        # Target output path (where to actually save the script, overrides LLM's path)
        self.target_output_path = target_output_path
        
        # Vision-based element labeling
        self.use_vision = use_vision
        self.vision_labeler = VisionLabeler() if use_vision else None
        self.current_elements: list[ElementInfo] = []  # Current labeled elements on page
        self.last_screenshot_path: Optional[str] = None
        
        # Screenshot directory and callback
        self.screenshot_dir = screenshot_dir
        self.screenshot_counter = 0
        self.screenshot_callback: Optional[Callable[[str], Any]] = None
        
        # Create screenshots directory if using vision
        if self.use_vision:
            os.makedirs(self.screenshot_dir, exist_ok=True)
        
        # Tool registry
        self.tools: dict[str, Tool] = {}
        self._register_tools()
    
    def set_screenshot_callback(self, callback: Callable[[str], Any]):
        """Set callback to be called after each screenshot"""
        self.screenshot_callback = callback
    
    def _register_tools(self):
        """Register all available tools."""
        
        # Navigation tool (still needed)
        self.register_tool(Tool(
            name="navigate_to_url",
            description="Navigate to a URL in the browser. After navigation, you MUST call capture_labeled_screenshot to see what's on the page.",
            parameters=[
                ToolParameter(name="url", type="string", description="The URL to navigate to"),
                ToolParameter(name="wait_until", type="string", description="When to consider navigation complete (load, domcontentloaded, networkidle)", required=False, default="load", enum=["load", "domcontentloaded", "networkidle", "commit"])
            ],
            handler=self._navigate_to_url
        ))
        
        # Vision-based tools (REQUIRED - the ONLY way to interact with pages)
        if self.use_vision:
            self.register_tool(Tool(
                name="capture_labeled_screenshot",
                description="Capture a screenshot with all interactive elements labeled with numbers. Returns the list of labeled elements that you can interact with.",
                parameters=[],
                handler=self._capture_labeled_screenshot
            ))
            
            self.register_tool(Tool(
                name="inspect_label",
                description="Get detailed information about a specific labeled element including its full text content, all attributes, and DOM details. Use this when you need more information about an element before interacting with it.",
                parameters=[
                    ToolParameter(name="label", type="number", description="The label number of the element to inspect")
                ],
                handler=self._inspect_label
            ))
            
            self.register_tool(Tool(
                name="click_label",
                description="Click on an element by its label number (from the labeled screenshot). Much more reliable than CSS selectors.",
                parameters=[
                    ToolParameter(name="label", type="number", description="The label number of the element to click")
                ],
                handler=self._click_label
            ))
            
            self.register_tool(Tool(
                name="type_into_label",
                description="Type text into an input field by its label number (from the labeled screenshot).",
                parameters=[
                    ToolParameter(name="label", type="number", description="The label number of the input field"),
                    ToolParameter(name="text", type="string", description="The text to type")
                ],
                handler=self._type_into_label
            ))
            
            self.register_tool(Tool(
                name="hover_label",
                description="Hover over an element by its label number (from the labeled screenshot). Use this to trigger hover effects like dropdown menus.",
                parameters=[
                    ToolParameter(name="label", type="number", description="The label number of the element to hover over")
                ],
                handler=self._hover_label
            ))
            
            self.register_tool(Tool(
                name="select_from_label",
                description="Select an option from a dropdown by its label number. Use this for <select> dropdowns or similar selection elements.",
                parameters=[
                    ToolParameter(name="label", type="number", description="The label number of the dropdown/select element"),
                    ToolParameter(name="value", type="string", description="The value to select (can be text or value attribute)", required=False),
                    ToolParameter(name="index", type="number", description="Or select by index (0-based)", required=False)
                ],
                handler=self._select_from_label
            ))
            
            self.register_tool(Tool(
                name="wait_for_seconds",
                description="Wait for a specified number of seconds. Use this when you need to wait for content to load or animations to complete.",
                parameters=[
                    ToolParameter(name="seconds", type="number", description="Number of seconds to wait")
                ],
                handler=self._wait_for_seconds
            ))
        
        # Tab/Page management tools
        self.register_tool(Tool(
            name="get_context_info",
            description="Get information about all open tabs/pages in the browser context. Returns a list of tabs with their index, URL, and title.",
            parameters=[],
            handler=self._get_context_info
        ))
        
        self.register_tool(Tool(
            name="switch_to_tab",
            description="Switch to a different tab/page by its index (from get_context_info). After switching, you must call capture_labeled_screenshot to see the new page.",
            parameters=[
                ToolParameter(name="tab_index", type="number", description="The index of the tab to switch to (0-based)")
            ],
            handler=self._switch_to_tab
        ))
        
        self.register_tool(Tool(
            name="create_new_tab",
            description="Create and switch to a new tab/page. Optionally navigate to a URL.",
            parameters=[
                ToolParameter(name="url", type="string", description="Optional URL to navigate to in the new tab", required=False)
            ],
            handler=self._create_new_tab
        ))
        
        self.register_tool(Tool(
            name="close_tab",
            description="Close a specific tab by its index. Cannot close the last remaining tab. After closing, switches to tab 0.",
            parameters=[
                ToolParameter(name="tab_index", type="number", description="The index of the tab to close (0-based)")
            ],
            handler=self._close_tab
        ))
        
        # Test script tools - similar to file editing tools
        self.register_tool(Tool(
            name="read_test_script",
            description="Read the current content of the test script being generated. Returns the full script content.",
            parameters=[],
            handler=self._read_test_script
        ))
        
        self.register_tool(Tool(
            name="write_test_script",
            description="Write or completely replace the test script content. This overwrites any existing content.",
            parameters=[
                ToolParameter(name="content", type="string", description="The complete Python/Playwright script content to write")
            ],
            handler=self._write_test_script
        ))
        
        self.register_tool(Tool(
            name="edit_test_script",
            description="Edit the test script by finding and replacing a specific string. Similar to find-and-replace. The old_string must match exactly (including whitespace).",
            parameters=[
                ToolParameter(name="old_string", type="string", description="The exact string to find and replace in the test script"),
                ToolParameter(name="new_string", type="string", description="The string to replace it with")
            ],
            handler=self._edit_test_script
        ))
        
        self.register_tool(Tool(
            name="save_test_script_to_file",
            description="Save the current test script content to a file on disk",
            parameters=[
                ToolParameter(name="file_path", type="string", description="Path where the test script should be saved (e.g., 'gen_tests/test_login.py')")
            ],
            handler=self._save_test_script_to_file
        ))
    
    def register_tool(self, tool: Tool):
        """Register a new tool."""
        self.tools[tool.name] = tool
    
    def get_tool_declarations(self) -> list[dict]:
        """Get all tools as function declarations for LLM."""
        return [tool.to_function_declaration() for tool in self.tools.values()]
    
    async def initialize(self):
        """Initialize the browser and create a new page."""
        if not self.playwright:
            self.playwright = await async_playwright().start()
            
            if self.browser_type == "chromium":
                self.browser = await self.playwright.chromium.launch(headless=self.headless)
            elif self.browser_type == "firefox":
                self.browser = await self.playwright.firefox.launch(headless=self.headless)
            elif self.browser_type == "webkit":
                self.browser = await self.playwright.webkit.launch(headless=self.headless)
            else:
                raise ValueError(f"Unknown browser type: {self.browser_type}")
            
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080}
            )
            self.page = await self.context.new_page()
    
    async def cleanup(self):
        """Close browser and cleanup resources."""
        try:
            if self.context:
                await self.context.close()
        except Exception as e:
            print(f"⚠️  Error closing context: {e}")
        
        try:
            if self.browser:
                await self.browser.close()
        except Exception as e:
            print(f"⚠️  Error closing browser: {e}")
        
        try:
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            print(f"⚠️  Error stopping playwright: {e}")
    
    async def execute_tool(self, tool_name: str, **kwargs) -> dict:
        """
        Execute a tool by name with given arguments.
        
        Returns:
            dict with 'success', 'result', and optionally 'error' keys
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        tool = self.tools[tool_name]
        
        try:
            result = await tool.handler(**kwargs)
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"{type(e).__name__}: {str(e)}"
            }
    
    # Tool handler implementations
    
    async def _navigate_to_url(self, url: str, wait_until: str = "load") -> str:
        """Navigate to URL."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        await self.page.goto(url, wait_until=wait_until)
        
        # Get page context for LLM
        current_url = self.page.url
        title = await self.page.title()
        
        return f"Navigated to {url}\nCurrent URL: {current_url}\nPage Title: {title}"
    
    async def _click_element(self, selector: str, timeout: int = 30000, force: bool = False) -> str:
        """Click an element."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        # Get element text before clicking (if available)
        element_text = ""
        try:
            element = await self.page.query_selector(selector)
            if element:
                element_text = await element.text_content()
                element_text = f" (text: '{element_text.strip()[:50]}')" if element_text and element_text.strip() else ""
        except:
            pass
        
        await self.page.click(selector, timeout=timeout, force=force)
        
        # Get page context after click
        current_url = self.page.url
        
        return f"Clicked element: {selector}{element_text}\nCurrent URL after click: {current_url}"
    
    async def _type_text(self, selector: str, text: str, clear_first: bool = True, delay: int = 0) -> str:
        """Type text into an element."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if clear_first:
            await self.page.fill(selector, text)
        else:
            await self.page.type(selector, text, delay=delay)
        
        # Verify what was actually typed
        try:
            element = await self.page.query_selector(selector)
            if element:
                actual_value = await element.input_value()
                return f"Typed '{text}' into {selector}\nActual value in field: '{actual_value}'"
        except:
            pass
        
        return f"Typed '{text}' into {selector}"
    
    async def _select_option(self, selector: str, value: str) -> str:
        """Select an option from dropdown."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        await self.page.select_option(selector, value)
        
        # Verify what was actually selected
        try:
            selected_value = await self.page.evaluate(f"""
                document.querySelector('{selector}').value
            """)
            return f"Selected option '{value}' in {selector}\nCurrent selected value: '{selected_value}'"
        except:
            pass
        
        return f"Selected option '{value}' in {selector}"
    
    async def _wait_for_selector(self, selector: str, timeout: int = 30000, state: str = "visible") -> str:
        """Wait for selector to appear."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        await self.page.wait_for_selector(selector, timeout=timeout, state=state)
        
        # Get element details if visible
        element_info = ""
        if state == "visible":
            try:
                element = await self.page.query_selector(selector)
                if element:
                    text = await element.text_content()
                    if text and text.strip():
                        element_info = f"\nElement text: '{text.strip()[:100]}'"
            except:
                pass
        
        return f"Element {selector} is {state}{element_info}"
    
    async def _take_screenshot(self, path: str, selector: Optional[str] = None, full_page: bool = False) -> str:
        """Take a screenshot."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        # Ensure parent directory exists
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        
        if selector:
            element = await self.page.query_selector(selector)
            if element:
                await element.screenshot(path=path)
            else:
                raise ValueError(f"Element not found: {selector}")
        else:
            await self.page.screenshot(path=path, full_page=full_page)
        
        return f"Screenshot saved to {path}"
    
    async def _get_text_content(self, selector: str) -> str:
        """Get text content of element."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        text = await self.page.text_content(selector)
        return text or ""
    
    async def _is_visible(self, selector: str) -> bool:
        """Check if element is visible."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        return await self.page.is_visible(selector)
    
    async def _get_page_state(self) -> str:
        """Get comprehensive page state information."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        try:
            url = self.page.url
            title = await self.page.title()
            
            # Get some key page elements for context
            page_info = f"""Page State:
URL: {url}
Title: {title}

Key Elements Present:
"""
            
            # Check for common interactive elements
            common_selectors = {
                "input fields": "input[type='text'], input[type='search'], input[type='email'], textarea",
                "buttons": "button, input[type='submit']",
                "links": "a[href]",
                "forms": "form"
            }
            
            for element_type, selector in common_selectors.items():
                try:
                    count = await self.page.locator(selector).count()
                    if count > 0:
                        page_info += f"- {count} {element_type}\n"
                except:
                    pass
            
            return page_info.strip()
            
        except Exception as e:
            return f"Error getting page state: {str(e)}"
    
    async def _capture_labeled_screenshot(self) -> dict:
        """Capture screenshot with labeled interactive elements."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.vision_labeler:
            raise RuntimeError("Vision labeling is not enabled.")
        
        # Ensure screenshots directory exists
        os.makedirs(self.screenshot_dir, exist_ok=True)
        print(f"📸 Capturing labeled screenshot...")
        
        try:
            # Generate output path using the configured screenshot directory
            self.screenshot_counter += 1
            output_path = os.path.join(self.screenshot_dir, f"labeled_{self.screenshot_counter}.png")
            
            # Capture and label with explicit path
            screenshot_path, elements, image_bytes = await self.vision_labeler.capture_and_label_page(
                self.page,
                output_path=output_path
            )
            
            print(f"📸 Screenshot saved to: {screenshot_path}")
            print(f"📸 Found {len(elements)} interactive elements")
            
            # Store current elements
            self.current_elements = elements
            self.last_screenshot_path = screenshot_path
            
            # Call callback if set
            if self.screenshot_callback:
                result = self.screenshot_callback(screenshot_path)
                # Handle both sync and async callbacks
                if asyncio.iscoroutine(result):
                    await result
            
            # Format element list for LLM
            elements_text = self.vision_labeler.format_elements_for_llm(elements)
            
            # Encode image as base64 for vision models
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')
            
            # Return structured data with both text and image
            return {
                "screenshot_path": screenshot_path,
                "elements_summary": elements_text,
                "image_base64": image_base64,
                "element_count": len(elements),
                "text_description": f"""Captured labeled screenshot with {len(elements)} interactive elements.

{elements_text}

Available actions:
- Use inspect_label(label=N) to get detailed info about an element
- Use click_label(label=N) to click an element  
- Use type_into_label(label=N, text="...") to type into an input field

The labeled screenshot image shows numbered boxes over each interactive element."""
            }
        
        except Exception as e:
            print(f"❌ Error in capture_labeled_screenshot: {e}")
            import traceback
            traceback.print_exc()
            raise
    
    async def _inspect_label(self, label: int) -> str:
        """Get detailed information about a specific labeled element."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.current_elements:
            raise RuntimeError("No labeled elements available. Call capture_labeled_screenshot first.")
        
        # Find element by label
        element_info = None
        for elem in self.current_elements:
            if elem.label == label:
                element_info = elem
                break
        
        if not element_info:
            available_labels = [e.label for e in self.current_elements]
            raise ValueError(f"Label {label} not found. Available labels: {available_labels}")
        
        # Get detailed information from the page
        try:
            js_code = f"""
            () => {{
                const element = document.querySelector('{element_info.selector}');
                if (!element) return null;
                
                // Get all attributes
                const attrs = {{}};
                for (const attr of element.attributes) {{
                    attrs[attr.name] = attr.value;
                }}
                
                // Get computed styles
                const style = window.getComputedStyle(element);
                
                return {{
                    tagName: element.tagName.toLowerCase(),
                    textContent: element.textContent || '',
                    innerText: element.innerText || '',
                    innerHTML: element.innerHTML ? element.innerHTML.substring(0, 500) : '',
                    value: element.value || '',
                    attributes: attrs,
                    isVisible: style.display !== 'none' && style.visibility !== 'hidden',
                    isEnabled: !element.disabled,
                    classList: Array.from(element.classList),
                    href: element.href || '',
                    src: element.src || '',
                }};
            }}
            """
            
            detailed_info = await self.page.evaluate(js_code)
            
            if not detailed_info:
                return f"Element [Label {label}] not found in DOM (may have been removed)"
            
            # Format the output
            output = f"""Element [Label {label}] Detailed Information:

Tag: {detailed_info['tagName']}
Type: {element_info.element_type}
Selector: {element_info.selector}

Text Content: {detailed_info['textContent'][:200] if detailed_info['textContent'] else '(empty)'}
Inner Text: {detailed_info['innerText'][:200] if detailed_info['innerText'] else '(empty)'}
"""
            
            if detailed_info.get('value'):
                output += f"\nCurrent Value: {detailed_info['value']}"
            
            if detailed_info.get('href'):
                output += f"\nHref: {detailed_info['href']}"
                
            if detailed_info.get('src'):
                output += f"\nSrc: {detailed_info['src']}"
            
            output += f"\n\nVisibility: {'Visible' if detailed_info['isVisible'] else 'Hidden'}"
            output += f"\nEnabled: {'Yes' if detailed_info['isEnabled'] else 'No (disabled)'}"
            
            if detailed_info['classList']:
                output += f"\nCSS Classes: {', '.join(detailed_info['classList'])}"
            
            output += "\n\nAttributes:"
            for attr_name, attr_value in detailed_info['attributes'].items():
                if attr_value and len(str(attr_value)) < 100:
                    output += f"\n  {attr_name}: {attr_value}"
                elif attr_value:
                    output += f"\n  {attr_name}: {str(attr_value)[:100]}..."
            
            if detailed_info['innerHTML'] and len(detailed_info['innerHTML']) > 0:
                output += f"\n\nInner HTML (truncated): {detailed_info['innerHTML'][:300]}..."
            
            return output
            
        except Exception as e:
            return f"Error inspecting element [Label {label}]: {str(e)}"
    
    async def _click_label(self, label: int) -> str:
        """Click an element by its label number."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.current_elements:
            raise RuntimeError("No labeled elements available. Call capture_labeled_screenshot first.")
        
        # Find element by label
        element_info = None
        for elem in self.current_elements:
            if elem.label == label:
                element_info = elem
                break
        
        if not element_info:
            available_labels = [e.label for e in self.current_elements]
            raise ValueError(f"Label {label} not found. Available labels: {available_labels}")
        
        # Determine if this element is likely to trigger navigation
        is_navigation_element = (
            element_info.element_type in ['a', 'submit'] or
            'link' in element_info.element_type.lower() or
            element_info.attributes.get('href') or
            element_info.element_type == 'button' and 'submit' in element_info.text.lower()
        )
        
        # Calculate center coordinates from bounding box
        bbox = element_info.bbox
        center_x = bbox['x'] + bbox['width'] / 2
        center_y = bbox['y'] + bbox['height'] / 2
        
        # Try clicking - use coordinates if selector is None or unreliable
        use_coordinates = element_info.selector is None
        new_page = None
        
        try:
            if use_coordinates:
                # Click by coordinates (most reliable)
                print(f"📍 Clicking at coordinates ({int(center_x)}, {int(center_y)})...")
                if is_navigation_element:
                    # Handle both new page and same-page navigation
                    async with self.context.expect_page(timeout=1000) as new_page_info:
                        await self.page.mouse.click(center_x, center_y)
                    try:
                        new_page = await new_page_info.value
                        print(f"🆕 New page opened, switching to it...")
                        self.page = new_page
                        await self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                    except:
                        # No new page, check for navigation on current page
                        await self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                else:
                    await self.page.mouse.click(center_x, center_y)
                    await self.page.wait_for_timeout(100)
            else:
                # Try clicking by selector first
                if is_navigation_element:
                    print(f"🔗 Clicking navigation element, waiting for page load...")
                    async with self.context.expect_page(timeout=1000) as new_page_info:
                        await self.page.click(element_info.selector, timeout=2000)
                    try:
                        new_page = await new_page_info.value
                        print(f"🆕 New page opened, switching to it...")
                        self.page = new_page
                        await self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                    except:
                        # No new page, check for navigation on current page
                        await self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                else:
                    await self.page.click(element_info.selector, timeout=2000, no_wait_after=True)
                    await self.page.wait_for_timeout(100)
        except Exception as e:
            # Fallback: click by coordinates (most reliable)
            print(f"⚠️  Selector-based click failed, using coordinates: {e}")
            try:
                if is_navigation_element:
                    # Try to catch new page
                    async with self.context.expect_page(timeout=1000) as new_page_info:
                        await self.page.mouse.click(center_x, center_y)
                    try:
                        new_page = await new_page_info.value
                        print(f"🆕 New page opened, switching to it...")
                        self.page = new_page
                        await self.page.wait_for_load_state('domcontentloaded', timeout=10000)
                    except:
                        # No new page, just wait a bit
                        await self.page.wait_for_timeout(500)
                else:
                    await self.page.mouse.click(center_x, center_y)
                    await self.page.wait_for_timeout(100)
            except:
                # Last resort: just click the coordinates, don't wait for navigation
                await self.page.mouse.click(center_x, center_y)
                await self.page.wait_for_timeout(100)
        
        # Get page context after click
        current_url = self.page.url
        new_page_opened = new_page is not None
        
        # Build detailed automation context
        automation_notes = []
        
        # Note the method used
        if use_coordinates:
            automation_notes.append(f"✓ Clicked using COORDINATES: ({int(center_x)}, {int(center_y)})")
            automation_notes.append(f"  Python code: await page.mouse.click({center_x}, {center_y})")
        elif element_info.selector:
            automation_notes.append(f"✓ Clicked using SELECTOR: {element_info.selector}")
            automation_notes.append(f"  Python code: await page.click('{element_info.selector}')")
        
        # Note if new page opened
        if new_page_opened:
            automation_notes.append(f"✓ NEW PAGE OPENED (target='_blank' or window.open)")
            automation_notes.append(f"  Python code: async with context.expect_page() as new_page_info:")
            automation_notes.append(f"              await page.click(...)")
            automation_notes.append(f"              new_page = await new_page_info.value")
            automation_notes.append(f"              page = new_page  # Switch to new page")
        elif is_navigation_element:
            automation_notes.append(f"✓ Navigation occurred on SAME PAGE")
            automation_notes.append(f"  Python code: await page.click(...)")
            automation_notes.append(f"              await page.wait_for_load_state('domcontentloaded')")
        else:
            automation_notes.append(f"✓ In-page interaction (no navigation)")
        
        # Provide alternative selectors if available
        selector_alternatives = []
        if element_info.attributes.get('id'):
            selector_alternatives.append(f"By ID: #{element_info.attributes['id']}")
        if element_info.attributes.get('name'):
            selector_alternatives.append(f"By name: [name='{element_info.attributes['name']}']")
        if element_info.attributes.get('ariaLabel'):
            selector_alternatives.append(f"By aria-label: [aria-label='{element_info.attributes['ariaLabel']}']")
        if element_info.text and len(element_info.text.strip()) > 0:
            text_preview = element_info.text.strip()[:30]
            selector_alternatives.append(f"By text: text='{text_preview}'")
        
        result = f"""Clicked element [Label {label}] successfully!

Element Details:
- Type: {element_info.element_type}
- Text: {element_info.text[:50] if element_info.text else '(no text)'}
- Position: ({int(bbox['x'])}, {int(bbox['y'])})

Automation Method Used:
{chr(10).join(automation_notes)}

Alternative Selectors Available:
{chr(10).join(f"- {alt}" for alt in selector_alternatives) if selector_alternatives else "- (coordinates only - no stable selectors)"}

Result:
- Current URL: {current_url}
- Page changed: {'Yes - new page opened' if new_page_opened else 'No - same page'}

💡 IMPORTANT FOR SCRIPT GENERATION:
{'- Use context.expect_page() to catch new page opening' if new_page_opened else '- Use page.click() for same-page navigation' if is_navigation_element else '- Use page.click() with no_wait_after=True for in-page interactions'}

Consider calling capture_labeled_screenshot again to see the updated page state."""
        
        return result
    
    async def _type_into_label(self, label: int, text: str) -> str:
        """Type text into an input element by its label number."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.current_elements:
            raise RuntimeError("No labeled elements available. Call capture_labeled_screenshot first.")
        
        # Find element by label
        element_info = None
        for elem in self.current_elements:
            if elem.label == label:
                element_info = elem
                break
        
        if not element_info:
            available_labels = [e.label for e in self.current_elements]
            raise ValueError(f"Label {label} not found. Available labels: {available_labels}")
        
        # Type using the selector or coordinates
        bbox = element_info.bbox
        center_x = bbox['x'] + bbox['width'] / 2
        center_y = bbox['y'] + bbox['height'] / 2
        used_method = None
        
        try:
            if element_info.selector:
                await self.page.fill(element_info.selector, text, timeout=2000)
                used_method = "fill"
            else:
                # Click to focus, then type
                print(f"📍 Clicking input at coordinates ({int(center_x)}, {int(center_y)}) to focus...")
                await self.page.mouse.click(center_x, center_y)
                await self.page.wait_for_timeout(50)
                await self.page.keyboard.type(text)
                used_method = "click_and_type"
        except Exception as e:
            # Fallback: click coordinates and type
            print(f"⚠️  Fill failed, using click + type: {e}")
            await self.page.mouse.click(center_x, center_y)
            await self.page.wait_for_timeout(50)
            # Clear existing content
            await self.page.keyboard.press("Control+A")
            await self.page.keyboard.type(text)
            used_method = "click_and_type_with_clear"
        
        # Verify what was typed and build detailed response
        actual_value = text  # default
        if element_info.selector:
            try:
                element = await self.page.query_selector(element_info.selector)
                if element:
                    actual_value = await element.input_value()
            except:
                pass
        
        # Build automation context
        automation_notes = []
        
        if used_method == "fill":
            automation_notes.append(f"✓ Typed using FILL method with selector")
            automation_notes.append(f"  Python code: await page.fill('{element_info.selector}', '{text}')")
        elif used_method in ["click_and_type", "click_and_type_with_clear"]:
            automation_notes.append(f"✓ Typed using CLICK + TYPE method (coordinates)")
            automation_notes.append(f"  Python code: await page.mouse.click({center_x}, {center_y})")
            if used_method == "click_and_type_with_clear":
                automation_notes.append(f"              await page.keyboard.press('Control+A')  # Clear existing")
            automation_notes.append(f"              await page.keyboard.type('{text}')")
        
        # Provide alternative selectors
        selector_alternatives = []
        if element_info.attributes.get('id'):
            selector_alternatives.append(f"By ID: #{element_info.attributes['id']}")
        if element_info.attributes.get('name'):
            selector_alternatives.append(f"By name: [name='{element_info.attributes['name']}']")
        if element_info.attributes.get('placeholder'):
            selector_alternatives.append(f"By placeholder: [placeholder='{element_info.attributes['placeholder']}']")
        if element_info.attributes.get('ariaLabel'):
            selector_alternatives.append(f"By aria-label: [aria-label='{element_info.attributes['ariaLabel']}']")
        
        result = f"""Typed '{text}' into element [Label {label}] successfully!

Element Details:
- Type: {element_info.element_type}
- Placeholder: {element_info.attributes.get('placeholder', '(none)')}
- Position: ({int(bbox['x'])}, {int(bbox['y'])})

Automation Method Used:
{chr(10).join(automation_notes)}

Alternative Selectors Available:
{chr(10).join(f"- {alt}" for alt in selector_alternatives) if selector_alternatives else "- (coordinates only - no stable selectors)"}

Result:
- Actual value in field: '{actual_value}'
- Value matches input: {'✓ Yes' if actual_value == text else '✗ No'}

💡 IMPORTANT FOR SCRIPT GENERATION:
- Prefer page.fill() for simple text input (faster and more reliable)
- Use page.type() for character-by-character typing if needed
- Always verify input with element.input_value() in tests"""
        
        return result
    
    async def _hover_label(self, label: int) -> str:
        """Hover over an element by its label number using mouse coordinates."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.current_elements:
            raise RuntimeError("No labeled elements available. Call capture_labeled_screenshot first.")
        
        # Find element by label
        element_info = None
        for elem in self.current_elements:
            if elem.label == label:
                element_info = elem
                break
        
        if not element_info:
            available_labels = [e.label for e in self.current_elements]
            raise ValueError(f"Label {label} not found. Available labels: {available_labels}")
        
        # Calculate center coordinates
        bbox = element_info.bbox
        center_x = bbox['x'] + bbox['width'] / 2
        center_y = bbox['y'] + bbox['height'] / 2
        
        # ALWAYS use mouse.move() for reliable hover - no DOM selector magic
        print(f"🎯 Hovering at coordinates ({int(center_x)}, {int(center_y)})...")
        await self.page.mouse.move(center_x, center_y)
        
        # Wait for hover effects to trigger (dropdowns, menus, etc.)
        await self.page.wait_for_timeout(300)
        
        # Build automation context
        automation_notes = []
        automation_notes.append(f"✓ Hovered using MOUSE MOVE to coordinates")
        automation_notes.append(f"  Python code: await page.mouse.move({center_x}, {center_y})")
        automation_notes.append(f"              await page.wait_for_timeout(300)  # Wait for hover effects")
        
        # Provide alternative selectors if available (for script generation reference)
        selector_alternatives = []
        if element_info.selector:
            selector_alternatives.append(f"Alternative: await page.hover('{element_info.selector}')")
        if element_info.attributes.get('id'):
            selector_alternatives.append(f"By ID: await page.hover('#{element_info.attributes['id']}')")
        if element_info.attributes.get('ariaLabel'):
            selector_alternatives.append(f"By aria-label: await page.hover('[aria-label=\"{element_info.attributes['ariaLabel']}\"]')")
        
        result = f"""Hovered over element [Label {label}] successfully!

Element Details:
- Type: {element_info.element_type}
- Tag: {element_info.tag_name}
- Text: {element_info.text[:50] if element_info.text else '(no text)'}
- Position: ({int(bbox['x'])}, {int(bbox['y'])})

Automation Method Used:
{chr(10).join(automation_notes)}

Alternative Selectors for Script Generation:
{chr(10).join(f"- {alt}" for alt in selector_alternatives) if selector_alternatives else "- (coordinates only - most reliable for hover)"}

💡 IMPORTANT FOR SCRIPT GENERATION:
- Mouse coordinates are MOST RELIABLE for hover interactions
- Coordinates trigger :hover CSS pseudoclasses correctly
- DOM hover() may fail on complex dropdowns/menus
- Always wait 200-500ms after hover for animations

💡 TIP: Call capture_labeled_screenshot again to see if hover triggered a dropdown/menu."""
        
        return result
    
    async def _select_from_label(self, label: int, value: str = None, index: int = None) -> str:
        """Select an option from a dropdown by its label number."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.current_elements:
            raise RuntimeError("No labeled elements available. Call capture_labeled_screenshot first.")
        
        if value is None and index is None:
            raise ValueError("Must provide either 'value' or 'index' parameter")
        
        # Find element by label
        element_info = None
        for elem in self.current_elements:
            if elem.label == label:
                element_info = elem
                break
        
        if not element_info:
            available_labels = [e.label for e in self.current_elements]
            raise ValueError(f"Label {label} not found. Available labels: {available_labels}")
        
        if not element_info.selector:
            raise RuntimeError(f"Element [Label {label}] has no selector - cannot interact with it")
        
        # Select the option
        try:
            if index is not None:
                # Select by index
                await self.page.select_option(element_info.selector, index=index, timeout=2000)
                return f"""Selected option by index {index} in [Label {label}]

Element: {element_info.selector}
Python code: await page.select_option('{element_info.selector}', index={index})"""
            else:
                # Select by value or text
                await self.page.select_option(element_info.selector, value, timeout=2000)
                return f"""Selected option '{value}' in [Label {label}]

Element: {element_info.selector}
Python code: await page.select_option('{element_info.selector}', '{value}')"""
        except Exception as e:
            return f"❌ Failed to select option: {str(e)}\n\nTip: For non-<select> dropdowns, use click_label to open the menu first."
    
    async def _wait_for_seconds(self, seconds: float) -> str:
        """Wait for specified number of seconds."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        await self.page.wait_for_timeout(int(seconds * 1000))
        
        return f"""Waited for {seconds} seconds.

Python code: await page.wait_for_timeout({int(seconds * 1000)})

💡 TIP: For production tests, prefer:
- page.wait_for_selector() - wait for specific elements
- page.wait_for_load_state() - wait for page loads
- Fixed timeouts should be avoided when possible"""
    
    # Tab/Page management tools
    
    async def _get_context_info(self) -> str:
        """Get information about all open tabs/pages in the browser context."""
        if not self.context:
            raise RuntimeError("Browser context not initialized. Call initialize() first.")
        
        # Get all pages in the context
        pages = self.context.pages
        
        if not pages:
            return "No pages/tabs open in the browser context."
        
        # Find current page index
        current_page_index = -1
        for idx, page in enumerate(pages):
            if page == self.page:
                current_page_index = idx
                break
        
        # Build context information
        output = f"Browser Context - {len(pages)} tab(s) open:\n\n"
        
        for idx, page in enumerate(pages):
            is_current = " ← CURRENT" if idx == current_page_index else ""
            try:
                url = page.url
                title = await page.title()
                output += f"[{idx}] {title}\n"
                output += f"     URL: {url}{is_current}\n\n"
            except Exception as e:
                output += f"[{idx}] (Error getting page info: {e}){is_current}\n\n"
        
        output += f"""💡 Usage:
- Use switch_to_tab(tab_index={0 if current_page_index != 0 else 1}) to switch tabs
- Use create_new_tab() to open a new tab
- Use close_tab(tab_index=X) to close a specific tab
- After switching, call capture_labeled_screenshot to see the page"""
        
        return output
    
    async def _switch_to_tab(self, tab_index: int | float) -> str:
        """Switch to a different tab by index."""
        # Convert to int if float (LLM sometimes passes floats)
        tab_index = int(tab_index)
        
        if not self.context:
            raise RuntimeError("Browser context not initialized. Call initialize() first.")
        
        pages = self.context.pages
        
        if not pages:
            raise RuntimeError("No pages/tabs available in the context.")
        
        if tab_index < 0 or tab_index >= len(pages):
            raise ValueError(f"Invalid tab index {tab_index}. Available tabs: 0 to {len(pages) - 1}")
        
        # Switch to the specified page
        old_page = self.page
        self.page = pages[tab_index]
        
        # Clear current elements since we're on a new page
        self.current_elements = []
        self.last_screenshot_path = None
        
        # Get new page info
        try:
            url = self.page.url
            title = await self.page.title()
            
            return f"""Switched to tab [{tab_index}] successfully!

Tab Details:
- Title: {title}
- URL: {url}
- Total tabs open: {len(pages)}

Python code: 
  pages = context.pages
  page = pages[{tab_index}]

💡 IMPORTANT: Call capture_labeled_screenshot to see what's on this page!"""
        except Exception as e:
            return f"Switched to tab [{tab_index}], but error getting page info: {e}"
    
    async def _create_new_tab(self, url: str = None) -> str:
        """Create a new tab and optionally navigate to a URL."""
        if not self.context:
            raise RuntimeError("Browser context not initialized. Call initialize() first.")
        
        # Create new page
        new_page = await self.context.new_page()
        
        # Switch to it
        self.page = new_page
        self.current_elements = []
        self.last_screenshot_path = None
        
        # Navigate if URL provided
        if url:
            await new_page.goto(url, wait_until="domcontentloaded")
            await new_page.wait_for_timeout(500)  # Wait for initial render
            
            title = await new_page.title()
            current_url = new_page.url
            
            return f"""Created and switched to new tab!

Tab Details:
- Title: {title}
- URL: {current_url}
- Total tabs open: {len(self.context.pages)}

Python code:
  new_page = await context.new_page()
  await new_page.goto('{url}')
  page = new_page

💡 IMPORTANT: Call capture_labeled_screenshot to see what's on this page!"""
        else:
            return f"""Created and switched to new blank tab!

- Total tabs open: {len(self.context.pages)}

Python code:
  new_page = await context.new_page()
  page = new_page

💡 TIP: Use navigate_to_url to go to a specific URL, then capture_labeled_screenshot."""
    
    async def _close_tab(self, tab_index: int | float) -> str:
        """Close a specific tab by index."""
        # Convert to int if float (LLM sometimes passes floats)
        tab_index = int(tab_index)
        
        if not self.context:
            raise RuntimeError("Browser context not initialized. Call initialize() first.")
        
        pages = self.context.pages
        
        if not pages:
            raise RuntimeError("No pages/tabs available in the context.")
        
        if len(pages) == 1:
            raise RuntimeError("Cannot close the last remaining tab. At least one tab must remain open.")
        
        if tab_index < 0 or tab_index >= len(pages):
            raise ValueError(f"Invalid tab index {tab_index}. Available tabs: 0 to {len(pages) - 1}")
        
        page_to_close = pages[tab_index]
        
        # Get info before closing
        try:
            url = page_to_close.url
            title = await page_to_close.title()
            page_info = f"'{title}' ({url})"
        except:
            page_info = f"tab {tab_index}"
        
        # Close the page
        await page_to_close.close()
        
        # If we closed the current page, switch to tab 0
        if page_to_close == self.page:
            remaining_pages = self.context.pages
            if remaining_pages:
                self.page = remaining_pages[0]
                self.current_elements = []
                self.last_screenshot_path = None
                switch_message = f"\n✓ Switched to tab [0]: {await self.page.title()}"
            else:
                switch_message = "\n⚠️ No pages remaining!"
        else:
            switch_message = ""
        
        return f"""Closed tab [{tab_index}]: {page_info}

Remaining tabs: {len(self.context.pages)}{switch_message}

Python code:
  pages = context.pages
  await pages[{tab_index}].close()
  page = pages[0]  # Switch to first tab

💡 TIP: Use get_context_info to see remaining tabs."""
    
    # Test script editing tools
    
    async def _read_test_script(self) -> str:
        """Read the current test script content."""
        if not self.test_script_content:
            return "(empty - no test script content yet)"
        return self.test_script_content
    
    async def _write_test_script(self, content: str) -> str:
        """Write/replace the entire test script content."""
        self.test_script_content = content
        return f"Test script updated ({len(content)} characters, {len(content.splitlines())} lines)"
    
    async def _edit_test_script(self, old_string: str, new_string: str) -> str:
        """Edit test script by replacing old_string with new_string."""
        if not self.test_script_content:
            raise ValueError("Test script is empty. Use write_test_script first.")
        
        if old_string not in self.test_script_content:
            raise ValueError(f"String not found in test script: {old_string[:100]}...")
        
        # Count occurrences
        count = self.test_script_content.count(old_string)
        if count > 1:
            raise ValueError(f"String appears {count} times in test script. Please provide a more specific string that appears only once.")
        
        self.test_script_content = self.test_script_content.replace(old_string, new_string)
        return f"Test script edited successfully (replaced 1 occurrence)"
    
    async def _save_test_script_to_file(self, file_path: str) -> str:
        """Save the test script to a file. Uses target_output_path if set, ignores file_path parameter."""
        if not self.test_script_content:
            raise ValueError("Test script is empty. Use write_test_script first.")
        
        # Use target_output_path if set (ignores LLM's file_path suggestion)
        actual_path = self.target_output_path if self.target_output_path else file_path
        
        # Ensure parent directory exists
        from pathlib import Path
        Path(actual_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(actual_path, 'w', encoding='utf-8') as f:
            f.write(self.test_script_content)
        
        self.script_file_path = actual_path
        return f"Test script saved to {actual_path} ({len(self.test_script_content)} characters)"


# Example usage
async def example_usage():
    """Demonstrate the toolkit usage."""
    toolkit = PlaywrightToolkit(headless=False)
    
    try:
        await toolkit.initialize()
        
        # Example: Navigate to a page
        result = await toolkit.execute_tool("navigate_to_url", url="https://example.com")
        print(result)
        
        # Get function declarations for LLM
        tools = toolkit.get_tool_declarations()
        print(f"\nAvailable tools: {len(tools)}")
        for tool in tools:
            print(f"  - {tool['name']}: {tool['description']}")
        
        # Build a test script using the new approach
        initial_script = '''"""
Example test script generated by Automaton.
"""

import asyncio
from playwright.async_api import async_playwright


async def test_example_flow():
    """Test the example flow."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=2000)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            # Navigate to example.com
            await page.goto("https://example.com", wait_until="networkidle")
            print("Navigated to example.com")
        except Exception as e:
            print(f"Error navigating to example.com: {e}")
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(test_example_flow())
'''
        
        # Write initial script
        await toolkit.execute_tool("write_test_script", content=initial_script)
        
        # Read it back
        current = await toolkit.execute_tool("read_test_script")
        print(f"\nCurrent script preview:\n{current['result'][:200]}...")
        
        # Edit to add a step
        await toolkit.execute_tool("edit_test_script",
                                  old_string="            # TODO: Add more steps here",
                                  new_string='''            # TODO: Add more steps here
            
            # Click on more information link
            await page.click("text=More information")''')
        
        # Save to file
        await toolkit.execute_tool("save_test_script_to_file", 
                                  file_path="generated_test.py")
        print("\n✓ Test script saved to generated_test.py")
        
    finally:
        await toolkit.cleanup()


if __name__ == "__main__":
    asyncio.run(example_usage())
