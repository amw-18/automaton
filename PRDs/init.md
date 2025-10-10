# Automaton
Auto QA Agent for the entire web.


## Flow
Automated repetitive QA script generation

Frontend developers need a low friction way to test their code and watch for regressions.
Attempt to build an intelligent code generation tool that takes care of majority of the 
failure cases that prop up in frontend testing.

Input: Video of a particular 'flow' of a website.
Output: A playwright test script that tests that flow.


## Details
For supporting the flow defined above. We need 3 distinct steps:
- High density information on relevant actions and interactions in the flow.
- Automated repetition by controlling a remote browser and imitating the flow
    - To be done by an automated reasoning agent
    - Reasoning agent to generate a playwright script in parallel to test the flow
- Refinement
    - To be done by an automated reasoning agent
    - Test and debug the script

Output: A reliable playwright test script to be integrated into automated actions.


## Implementation details
Tools:
- Reasoning agent (gemini-2.5-flash-thinking)
- Remote browser controller (playwright)
- async python

### Task 1
Generate a high level schema of a input json document that defines the high information density workflow. 
It should have starting url details, actions a user took, corresponding screenshots (url), timestamp, description of the step. Optionally can have dom element details for each action.

#### Solution
Created `src/workflow_schema.py` with comprehensive Pydantic-based schema:
- **WorkflowInput**: Main Pydantic model with metadata, starting_url, actions list, and expected final state
- **WorkflowAction**: Individual action model with timestamp validation, action_type (Literal enum), description, screenshot_url, and optional DOM element details
- **DOMElement**: Optional DOM details including selectors (CSS/XPath), tag name, text content, attributes, and bounding box
- **WorkflowMetadata**: Workflow metadata with validated browser types, viewport dimensions, and ISO 8601 timestamp validation
- **ScrollPosition**: Scroll coordinates with validation (x, y >= 0)
- **Viewport**: Browser viewport model with positive integer validation
- Built-in Pydantic validation ensures type safety and data integrity
- Example workflow demonstrating a complete login flow
- Supports action types: click, type, navigate, scroll, select, hover, wait (enforced via Literal)
- JSON schema export via `model_json_schema()` for API documentation
- Serialization/deserialization with `model_validate()` and `model_dump_json()`

The schema is extensible, type-safe, and captures high-density information needed for test generation.


### Task 2
Generate a tool-calling framework for async python playwright connected to a remote browser.
The agent should have access to functions to navigate to a url, click on an element, type in an element, etc.
Along with that, the agent should be using a writing tool to edit a test script that encodes the actions, handling exceptions and cases that arise during interactions with the browser to reproduce the original flow.
Do not worry about the exact agent to use right now. Only implement the abstraction on top of playwright and the ability to specify the function, their arguments, descriptions etc. to an llm agent.

#### Solution
Created `src/playwright_framework.py` with complete tool-calling abstraction:

**Core Classes (Pydantic Models):**
- **ToolParameter**: Pydantic model defining function parameters with validated type (Literal), description, required flag, enum values, and defaults
- **Tool**: Pydantic model encapsulating a callable function with name, description, validated parameters list, and handler
- **PlaywrightToolkit**: Main toolkit class managing browser lifecycle and tool registry

**Available Tools (12 total):**

*Browser Control (8 tools):*
1. **navigate_to_url**: Navigate to URL with configurable wait states
2. **click_element**: Click elements by selector with timeout and force options
3. **type_text**: Type text into inputs with clear and delay options
4. **select_option**: Select dropdown options
5. **wait_for_selector**: Wait for elements with state conditions (visible/hidden/attached/detached)
6. **take_screenshot**: Capture full page or element screenshots
7. **get_text_content**: Extract text from elements
8. **is_visible**: Check element visibility

*Test Script Management (4 tools):*
9. **read_test_script**: Read the entire test script content being generated
10. **write_test_script**: Write or completely replace the test script content
11. **edit_test_script**: Find and replace in test script (exact string match required)
12. **save_test_script_to_file**: Save test script to disk

**Key Features:**
- All tools export to Gemini function declaration format via `to_function_declaration()`
- Async/await support throughout
- Exception handling in `execute_tool()` method
- Browser lifecycle management (initialize/cleanup)
- Robust test script editing tools (read/write/edit/save) - no fragile line-by-line updates
- Generates standalone async Python scripts (no pytest dependency)
- Configurable browser types (chromium/firefox/webkit)
- Headless/headed mode support

**Usage Pattern:**
```python
# Initialize toolkit
toolkit = PlaywrightToolkit(headless=False)
await toolkit.initialize()

# Control browser
await toolkit.execute_tool("navigate_to_url", url="https://example.com")
await toolkit.execute_tool("click_element", selector="button.login")

# Manage test script
script = '''import asyncio
from playwright.async_api import async_playwright

async def test_flow():
    # Test implementation here
    pass
'''
await toolkit.execute_tool("write_test_script", content=script)
await toolkit.execute_tool("read_test_script")  # Read current content
await toolkit.execute_tool("edit_test_script", old_string="# Test implementation here", 
                          new_string="await page.goto('https://example.com')")
await toolkit.execute_tool("save_test_script_to_file", file_path="tests/test_flow.py")

# Get tool declarations for LLM
tools = toolkit.get_tool_declarations()
```

The framework is ready for integration with Gemini-2.5-flash-thinking or any LLM that supports function calling.

