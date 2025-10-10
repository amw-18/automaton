"""
Tool-calling framework for async Python Playwright with remote browser control.

This module provides an abstraction layer over Playwright for LLM agents to control
browsers and generate test scripts.
"""

import asyncio
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
    
    def __init__(self, headless: bool = False, browser_type: str = "chromium", use_vision: bool = True):
        self.headless = headless
        self.browser_type = browser_type
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # Test script being generated (full content as string)
        self.test_script_content: str = ""
        self.script_file_path: Optional[str] = None
        
        # Vision-based element labeling
        self.use_vision = use_vision
        self.vision_labeler = VisionLabeler() if use_vision else None
        self.current_elements: list[ElementInfo] = []  # Current labeled elements on page
        self.last_screenshot_path: Optional[str] = None
        
        # Create screenshots directory if using vision
        if self.use_vision:
            os.makedirs("screenshots", exist_ok=True)
        
        # Tool registry
        self.tools: dict[str, Tool] = {}
        self._register_tools()
    
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
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
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
    
    async def _capture_labeled_screenshot(self) -> str:
        """Capture screenshot with labeled interactive elements."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Call initialize() first.")
        
        if not self.vision_labeler:
            raise RuntimeError("Vision labeling is not enabled.")
        
        # Ensure screenshots directory exists
        os.makedirs("screenshots", exist_ok=True)
        print(f"📸 Capturing labeled screenshot...")
        
        try:
            # Capture and label
            screenshot_path, elements, image_bytes = await self.vision_labeler.capture_and_label_page(
                self.page,
                output_path=None  # Will auto-generate path
            )
            
            print(f"📸 Screenshot saved to: {screenshot_path}")
            print(f"📸 Found {len(elements)} interactive elements")
            
            # Store current elements
            self.current_elements = elements
            self.last_screenshot_path = screenshot_path
            
            # Format element list for LLM
            elements_text = self.vision_labeler.format_elements_for_llm(elements)
            
            return f"""Captured labeled screenshot: {screenshot_path}

{elements_text}

You can now interact with these elements using their label numbers:
- Use click_label(label=N) to click an element
- Use type_into_label(label=N, text="...") to type into an input field"""
        
        except Exception as e:
            print(f"❌ Error in capture_labeled_screenshot: {e}")
            import traceback
            traceback.print_exc()
            raise
    
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
        
        # Click using the selector
        await self.page.click(element_info.selector)
        
        # Get page context after click
        current_url = self.page.url
        
        return f"""Clicked element [Label {label}]
Element: {element_info.element_type}
Text: {element_info.text[:50] if element_info.text else '(no text)'}
Selector: {element_info.selector}
Current URL after click: {current_url}

Consider calling capture_labeled_screenshot again to see the updated page."""
    
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
        
        # Type using the selector
        await self.page.fill(element_info.selector, text)
        
        # Verify what was typed
        try:
            element = await self.page.query_selector(element_info.selector)
            if element:
                actual_value = await element.input_value()
                return f"""Typed '{text}' into element [Label {label}]
Element: {element_info.element_type}
Placeholder: {element_info.attributes.get('placeholder', '(none)')}
Selector: {element_info.selector}
Actual value in field: '{actual_value}'"""
        except:
            pass
        
        return f"Typed '{text}' into element [Label {label}]"
    
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
        """Save the test script to a file."""
        if not self.test_script_content:
            raise ValueError("Test script is empty. Use write_test_script first.")
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(self.test_script_content)
        
        self.script_file_path = file_path
        return f"Test script saved to {file_path} ({len(self.test_script_content)} characters)"


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
