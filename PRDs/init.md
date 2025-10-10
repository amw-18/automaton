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


### Task 3
Implement a reasoning agent that uses the workflow input schema and playwright toolkit to autonomously generate test scripts. The agent should execute the workflow in a live browser, observe behavior, and codify it into a reliable test script.

#### Solution
Created complete LangGraph-based agent with Vertex AI Gemini integration in multiple files:

**Core Agent Files:**
- **`src/agent.py`**: Main `WorkflowAgent` class using LangGraph StateGraph
- **`src/agent_nodes.py`**: Node functions (parse_workflow, agent reasoning, tool execution, routing logic)
- **`src/agent_state.py`**: State management with `AgentState` and `AgentOutput` models
- **`src/config.py`**: Configuration (GCP settings, model parameters, comprehensive system prompt)
- **`src/README_AGENT.md`**: Complete usage documentation and troubleshooting guide

**Architecture:**
```
Parse Workflow → Agent (Gemini) ⟷ Execute Tools (Playwright) → END
```

**Agent Capabilities:**
- Parses and validates WorkflowInput using Pydantic
- Executes workflow actions in live browser
- Observes actual page behavior
- Generates complete test scripts using toolkit's script management tools
- Adds assertions based on expected outcomes
- Includes error handling and cleanup
- Tracks metrics (actions executed, assertions added, execution time)

**LangGraph Integration:**
- StateGraph with nodes: parse, agent (reasoning), execute_tools
- Conditional routing based on tool calls and execution state
- Messages-based state management (extends MessagesState)
- Support for checkpointing and streaming (optional)

**Vertex AI Gemini Setup:**
- Uses `ChatVertexAI` from `langchain-google-vertexai`
- Model: `gemini-2.0-flash-001` (configurable to 2.5-flash-thinking)
- Temperature: 0.3 for deterministic output
- Tool binding: All 12 Playwright toolkit functions
- Configurable via environment variables or `config.py`

**Dependencies Added:**
```bash
uv add langchain-google-vertexai langgraph langchain-core
```

**Usage Pattern:**
```python
import asyncio
from src.agent import WorkflowAgent
from src.playwright_framework import PlaywrightToolkit
from src.workflow_schema import WorkflowInput

async def main():
    # Load and validate workflow
    workflow = WorkflowInput.model_validate(workflow_data)
    
    # Initialize browser toolkit
    toolkit = PlaywrightToolkit(headless=False)
    await toolkit.initialize()
    
    try:
        # Create agent
        agent = WorkflowAgent(
            toolkit=toolkit,
            model_name="gemini-2.0-flash-001",
            project_id="YOUR_PROJECT_ID"
        )
        
        # Generate test script
        result = await agent.generate_test_script(
            workflow=workflow,
            output_path="tests/test_output.py"
        )
        
        if result.success:
            print(f"✅ Generated: {result.file_path}")
            print(f"   Actions: {result.actions_count}")
            print(f"   Assertions: {result.assertions_count}")
        else:
            print(f"❌ Error: {result.error}")
            
    finally:
        await toolkit.cleanup()

asyncio.run(main())
```

**Key Features:**
- Autonomous decision making via LLM reasoning
- Live browser execution with observation
- Simultaneous execution and codification
- Error recovery and retry logic
- Comprehensive state tracking
- Production-ready output with metrics

**Setup Requirements:**
1. Google Cloud project with Vertex AI enabled
2. Application Default Credentials configured
3. Environment variables: `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS`

See `PRDs/agent_implementation.md` for complete implementation details and `src/README_AGENT.md` for usage guide.

