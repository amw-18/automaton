"""Quick test to verify vision labeling works"""
import asyncio
from src.playwright_framework import PlaywrightToolkit

async def test_vision():
    toolkit = PlaywrightToolkit(headless=False, use_vision=True)
    
    try:
        await toolkit.initialize()
        
        # Navigate
        result = await toolkit.execute_tool("navigate_to_url", url="https://www.wikipedia.org")
        print(f"Navigate result: {result}")
        
        # Capture
        result = await toolkit.execute_tool("capture_labeled_screenshot")
        print(f"\n{'='*60}")
        print("CAPTURE LABELED SCREENSHOT")
        print('='*60)
        print(f"Success: {result['success']}")
        if result['success']:
            data = result['result']
            print(f"\nScreenshot Path: {data['screenshot_path']}")
            print(f"Element Count: {data['element_count']}")
            print(f"\nElements Summary (Grouped by Type):")
            print(data['elements_summary'])
            print(f"\nImage Data: {len(data['image_base64'])} bytes (base64 encoded)")
        else:
            print(f"Error: {result.get('error')}")
        
        # Test inspect_label on the first element
        print(f"\n{'='*60}")
        print("INSPECT LABEL #1")
        print('='*60)
        result = await toolkit.execute_tool("inspect_label", label=1)
        if result['success']:
            print(result['result'])
        else:
            print(f"Error: {result.get('error')}")
        
    finally:
        await toolkit.cleanup()

if __name__ == "__main__":
    asyncio.run(test_vision())
