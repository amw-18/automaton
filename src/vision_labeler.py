"""
Vision-based element labeling for browser automation.

This module captures screenshots with numbered bounding boxes overlaid on interactive elements,
allowing LLMs with vision capabilities to understand and interact with web pages.
"""

import base64
from io import BytesIO
from typing import List, Dict, Any, Optional
from PIL import Image, ImageDraw, ImageFont
from playwright.async_api import Page


class ElementInfo:
    """Information about a labeled interactive element."""
    
    def __init__(self, label: int, selector: str, element_type: str, text: str, 
                 bbox: Dict[str, float], attributes: Dict[str, str]):
        self.label = label
        self.selector = selector
        self.element_type = element_type
        self.text = text
        self.bbox = bbox  # {x, y, width, height}
        self.attributes = attributes
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format. Primarily used for debugging and detailed inspection."""
        return {
            "label": self.label,
            "selector": self.selector,
            "type": self.element_type,
            "text": self.text[:100] if self.text else "",  # Truncate long text
            "position": f"({int(self.bbox['x'])}, {int(self.bbox['y'])})",
            "size": f"{int(self.bbox['width'])}x{int(self.bbox['height'])}",
            "attributes": self.attributes
        }


class VisionLabeler:
    """
    Captures screenshots with numbered labels on interactive elements.
    """
    
    def __init__(self):
        self.screenshot_counter = 0
    
    async def capture_and_label_page(
        self, 
        page: Page,
        output_path: Optional[str] = None
    ) -> tuple[str, List[ElementInfo], bytes]:
        """
        Capture page screenshot with labeled interactive elements.
        
        Args:
            page: Playwright page object
            output_path: Optional path to save the annotated screenshot
            
        Returns:
            Tuple of (screenshot_path, element_info_list, image_bytes)
        """
        # Get all interactive elements
        elements = await self._get_interactive_elements(page)
        
        # Take screenshot
        screenshot_bytes = await page.screenshot(full_page=False)
        
        # Annotate screenshot with labels
        annotated_bytes, element_infos = await self._annotate_screenshot(
            screenshot_bytes, 
            elements,
            page
        )
        
        # Generate path if not provided
        if not output_path:
            self.screenshot_counter += 1
            output_path = f"screenshots/labeled_{self.screenshot_counter}.png"
        
        # Always save the annotated screenshot
        with open(output_path, 'wb') as f:
            f.write(annotated_bytes)
        
        return output_path, element_infos, annotated_bytes
    
    async def _get_interactive_elements(self, page: Page) -> List[Dict[str, Any]]:
        """
        Get all interactive elements with their bounding boxes.
        
        Returns list of dicts with: selector, type, text, bbox, attributes
        """
        # JavaScript to find all interactive elements
        js_code = """
        () => {
            const elements = [];
            const selectors = [
                'a[href]',
                'button',
                'input[type="text"]',
                'input[type="search"]',
                'input[type="email"]',
                'input[type="password"]',
                'input[type="submit"]',
                'input[type="button"]',
                'textarea',
                'select',
                '[role="button"]',
                '[onclick]',
                '[contenteditable="true"]'
            ];
            
            const allElements = new Set();
            selectors.forEach(selector => {
                document.querySelectorAll(selector).forEach(el => allElements.add(el));
            });
            
            // Convert Set to Array to get proper index
            const elementsArray = Array.from(allElements);
            elementsArray.forEach((el, index) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                
                // Check if element is truly visible
                const isVisible = (
                    // Has reasonable size
                    rect.width > 10 && rect.height > 10 &&
                    // Is within viewport
                    rect.top < window.innerHeight && 
                    rect.left < window.innerWidth &&
                    rect.bottom > 0 &&
                    rect.right > 0 &&
                    // CSS visibility checks
                    style.display !== 'none' &&
                    style.visibility !== 'hidden' &&
                    style.opacity !== '0' &&
                    // Element is not covered (basic check)
                    el.offsetParent !== null
                );
                
                if (isVisible) {
                    
                    const tagName = el.tagName.toLowerCase();
                    const type = el.getAttribute('type') || tagName;
                    const text = el.textContent?.trim().substring(0, 100) || '';
                    const id = el.id;
                    const className = el.className;
                    const name = el.getAttribute('name');
                    const placeholder = el.getAttribute('placeholder');
                    const ariaLabel = el.getAttribute('aria-label');
                    
                    elements.push({
                        index: index,
                        tagName: tagName,
                        type: type,
                        text: text,
                        bbox: {
                            x: rect.x,
                            y: rect.y,
                            width: rect.width,
                            height: rect.height
                        },
                        attributes: {
                            id: id || '',
                            class: className || '',
                            name: name || '',
                            placeholder: placeholder || '',
                            ariaLabel: ariaLabel || ''
                        }
                    });
                }
            });
            
            return elements;
        }
        """
        
        elements = await page.evaluate(js_code)
        return elements
    
    async def _annotate_screenshot(
        self, 
        screenshot_bytes: bytes, 
        elements: List[Dict[str, Any]],
        page: Page
    ) -> tuple[bytes, List[ElementInfo]]:
        """
        Draw numbered boxes on screenshot for each interactive element.
        
        Returns: (annotated_image_bytes, element_info_list)
        """
        # Load image
        image = Image.open(BytesIO(screenshot_bytes))
        draw = ImageDraw.Draw(image, 'RGBA')
        
        # Try to load a font (fallback to default if not available)
        try:
            # Try to use a TrueType font if available
            font = ImageFont.truetype("arial.ttf", 16)
            label_font = ImageFont.truetype("arial.ttf", 20)
        except:
            # Use default font
            font = ImageFont.load_default()
            label_font = ImageFont.load_default()
        
        element_infos = []
        
        for idx, elem in enumerate(elements):
            label = idx + 1
            bbox = elem['bbox']
            
            # Generate a selector for this element
            selector = self._generate_selector(elem)
            
            # Create ElementInfo object
            element_info = ElementInfo(
                label=label,
                selector=selector,
                element_type=elem['type'],
                text=elem['text'],
                bbox=bbox,
                attributes=elem['attributes']
            )
            element_infos.append(element_info)
            
            # Draw semi-transparent box
            box_coords = [
                bbox['x'],
                bbox['y'],
                bbox['x'] + bbox['width'],
                bbox['y'] + bbox['height']
            ]
            
            # Draw box with red border
            draw.rectangle(box_coords, outline='red', width=2)
            
            # Draw semi-transparent fill
            overlay = Image.new('RGBA', image.size, (255, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(overlay)
            overlay_draw.rectangle(box_coords, fill=(255, 0, 0, 30))
            image = Image.alpha_composite(image.convert('RGBA'), overlay)
            draw = ImageDraw.Draw(image)
            
            # Draw label number in top-left corner with background
            label_text = str(label)
            label_pos = (bbox['x'] + 2, bbox['y'] + 2)
            
            # Draw white background for label
            try:
                bbox_label = draw.textbbox(label_pos, label_text, font=label_font)
                draw.rectangle(bbox_label, fill='red')
                draw.text(label_pos, label_text, fill='white', font=label_font)
            except:
                # Fallback for older PIL versions
                draw.text(label_pos, label_text, fill='white', font=label_font)
        
        # Convert back to bytes
        output_buffer = BytesIO()
        image.convert('RGB').save(output_buffer, format='PNG')
        annotated_bytes = output_buffer.getvalue()
        
        return annotated_bytes, element_infos
    
    def _generate_selector(self, elem: Dict[str, Any]) -> str:
        """Generate a CSS selector for the element. Returns None if no good selector available."""
        attrs = elem['attributes']
        
        # Priority: id > name > aria-label > class combinations
        if attrs['id']:
            return f"#{attrs['id']}"
        elif attrs['name']:
            return f"{elem['tagName']}[name='{attrs['name']}']"
        elif attrs['ariaLabel']:
            return f"{elem['tagName']}[aria-label='{attrs['ariaLabel']}']"
        elif attrs['class']:
            # Try using class if it looks somewhat unique
            classes = attrs['class'].strip().split()
            if classes and len(classes) <= 3:  # Not too many classes
                class_selector = '.'.join(classes)
                return f"{elem['tagName']}.{class_selector}"
        
        # No good selector available - will use coordinates instead
        return None
    
    def format_elements_for_llm(self, elements: List[ElementInfo]) -> str:
        """
        Format element list for LLM consumption.
        Groups elements by type and shows only label numbers.
        
        Returns a concise string with elements grouped by type.
        """
        if not elements:
            return "No interactive elements found on the page."
        
        # Group elements by type
        type_groups = {}
        for elem in elements:
            elem_type = elem.element_type
            if elem_type not in type_groups:
                type_groups[elem_type] = []
            type_groups[elem_type].append(elem.label)
        
        # Format output
        output = f"Found {len(elements)} interactive elements:\n\n"
        
        # Sort by type name for consistency
        for elem_type in sorted(type_groups.keys()):
            labels = type_groups[elem_type]
            labels_str = ", ".join(str(label) for label in sorted(labels))
            output += f"{elem_type}: {labels_str}\n"
        
        return output.strip()
