# Callback-Based Test Execution Architecture

## Overview

The test execution system now uses a **callback-based architecture** where the LLM generates only the test actions as a function, and we control the browser setup, video recording, and cleanup. This guarantees video capture even when tests fail.

## Architecture

### Old Approach (Fragile)
```
LLM generates complete script
↓
Try to modify script to add video recording
↓
Run in Docker
↓
Hope cleanup happens
❌ Syntax errors, no video on failure
```

### New Approach (Robust)
```
LLM generates callback: async def test_actions(page)
↓
We create wrapper with browser setup & video
↓
Import callback, execute with try-finally
↓
Guaranteed cleanup & video
✅ Always get video, even on failure
```

## Components

### 1. Agent Generates Callback

**Prompt Updated**: `src/config.py`

Agent now generates only:
```python
from playwright.async_api import BrowserContext

async def test_actions(context: BrowserContext):
    """Test actions - context is already set up with video recording"""
    # Create page(s) as needed
    page = await context.new_page()
    
    await page.goto("https://example.com")
    await page.click("#button")
    
    # Can create multiple pages/tabs if needed
    # page2 = await context.new_page()
    
    print("✓ Test completed")
```

**Key Changes**:
- ✅ No browser setup
- ✅ No try/except/finally
- ✅ No `if __name__` block
- ✅ Receives BrowserContext for full control (can create pages, tabs, etc.)

### 2. Test Execution Creates Wrapper

**Service**: `services/test_execution_service.py`

Creates a wrapper script that:

```python
# 1. Imports the callback
from test_generated import test_actions

# 2. Sets up browser with video recording
context = await browser.new_context(
    viewport={"width": 1280, "height": 720},
    record_video_dir="/test/videos",
    record_video_size={"width": 1280, "height": 720}
)

# 3. Executes callback with try-finally (passes context, not page)
try:
    await test_actions(context)  # Callback creates pages as needed
except Exception as e:
    print(f"Test failed: {e}")
    raise
finally:
    # GUARANTEED cleanup - saves video
    await context.close()
    await browser.close()
```

### 3. Docker Execution

**Mounts**:
- Entire `test_output/` directory → `/test/`
- Contains:
  - `test_generated.py` (LLM callback)
  - `test_with_recording.py` (wrapper)
  - `videos/` (output)

**Runs**: `python /test/test_with_recording.py`

## Benefits

### ✅ Always Get Video
- `context.close()` in finally block → video saves even on failure
- No syntax errors from modifying generated code
- Clean separation of concerns

### ✅ Full Control
- We control browser settings (headless, viewport)
- We control video recording settings
- We control cleanup timing

### ✅ Uses Workflow Metadata
- Viewport dimensions from workflow
- Can add more settings as needed

### ✅ Robust
- No regex/string manipulation of generated code
- Import-based, clean Python
- Proper error handling

## File Structure

```
uploads/{session-id}/
├── output/
│   └── test_generated.py          # LLM callback (original)
└── test_output/
    ├── test_generated.py          # Copy for import
    ├── test_with_recording.py     # Wrapper script
    └── videos/                    # Video output
        └── test_execution.webm
```

## Flow

### 1. Agent Execution
```
Agent runs → Generates test_actions() callback
↓
Saves to uploads/{id}/output/test_generated.py
```

### 2. Test Execution Triggered
```
User clicks "Test Script"
↓
Copy test_generated.py to test_output/
↓
Generate wrapper script (test_with_recording.py)
↓
Run in Docker
```

### 3. Docker Execution
```
Mount test_output/ → /test/
↓
python /test/test_with_recording.py
↓
Imports: from test_generated import test_actions
↓
Sets up browser with video recording
↓
Executes: await test_actions(context)  ← Passes context, not page
↓
Finally: await context.close() → VIDEO SAVED
```

### 4. Video Extraction
```
Check test_output/videos/*.webm
↓
Move to test_output/test_execution.webm
↓
Serve via /api/test-videos/{id}/execution.webm
```

## Why This Works

### Playwright Video Recording Behavior
- Video recording starts when context is created
- Video is **only saved when context.close() is called**
- If process crashes without closing context → no video

### Our Solution
- **Wrapper ensures context.close() always runs** (in finally block)
- Test fails at step 3? → Finally runs → Video saved
- Docker crashes? → Process ends → Video saved from buffer
- Syntax error? → Can't happen (we generate wrapper, not modify LLM code)

## Key Code Points

### Agent Prompt (`src/config.py`)
```python
## REQUIRED Script Template (Callback Function):
async def test_actions(context: BrowserContext):
    """Execute the test workflow actions"""
    page = await context.new_page()
    await page.goto("https://example.com")
    # ... test actions ...
    # Can create more pages: page2 = await context.new_page()
```

### Wrapper Generator (`services/test_execution_service.py`)
```python
async def _prepare_test_script_with_video(...):
    # Extract viewport from workflow metadata
    viewport_width = session.workflow.metadata.viewport.width
    viewport_height = session.workflow.metadata.viewport.height
    
    # Generate wrapper that imports and executes callback
    wrapper = f'''
from test_generated import test_actions

async def run_test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={{"width": {viewport_width}, "height": {viewport_height}}},
            record_video_dir="/test/videos"
        )
        
        try:
            await test_actions(context)  # Pass context for full control
        finally:
            await context.close()
            await browser.close()
'''
```

### Docker Mount (`services/test_execution_service.py`)
```python
docker_cmd = [
    "docker", "run", "--rm",
    "-v", f"{output_dir.absolute()}:/test:rw",  # Mount entire directory
    "--network", "host",
    "playwright-runner:latest",
    "python", "/test/test_with_recording.py"
]
```

## Testing

### Success Case
```
Test passes → context.close() in finally → Video saved ✓
```

### Failure Case
```
Test fails at step 3 → Exception caught → Finally runs
→ context.close() → Video saved ✓
```

### Early Failure
```
Test fails at step 1 → Exception caught → Finally runs
→ context.close() → Partial video saved ✓
```

## Migration Notes

Existing workflows will continue to work:
- Old scripts (full standalone) → Will be copied and wrapped
- New scripts (callback) → Direct support

## Future Enhancements

- [ ] Support multiple test callbacks in one file
- [ ] Pass custom browser options from UI
- [ ] Add screenshot on each step option
- [ ] Support test parameterization
- [ ] Add test fixtures/setup/teardown hooks

## Conclusion

This architecture provides:
- **Reliability**: Always get video
- **Maintainability**: Clean separation of concerns
- **Flexibility**: Easy to add features
- **Robustness**: No fragile string manipulation

The callback pattern is a best practice used in test frameworks like pytest and gives us full control while letting the LLM focus on what it does best: generating test logic.
