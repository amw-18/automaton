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
        print(f"\nCapture result:")
        print(f"Success: {result['success']}")
        if result['success']:
            print(f"Result:\n{result['result'][:500]}...")
        else:
            print(f"Error: {result.get('error')}")
        
    finally:
        await toolkit.cleanup()

if __name__ == "__main__":
    asyncio.run(test_vision())
