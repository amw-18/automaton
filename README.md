# Automaton

**Auto QA Agent for the entire web** - Automated repetitive QA script generation using AI.

Automaton is an intelligent code generation tool that takes screen recordings of user workflows and automatically generates reliable Playwright test scripts. It combines multi-modal AI (Gemini vision), automated browser control (Playwright), and reasoning agents (LangGraph) to create production-ready test automation.

## Overview

**Input:** Video of a particular 'flow' of a website  
**Output:** A Playwright test script that tests that flow

## Features

- 🎬 **Video-to-Workflow**: Process screen recordings to extract user actions automatically
- 🤖 **AI-Powered Analysis**: Uses Gemini's multi-modal vision to detect clicks, typing, navigation
- 🎭 **Playwright Automation**: Vision-based browser control with labeled screenshots
- 🧠 **Reasoning Agent**: LangGraph-based agent that generates test scripts autonomously
- ✅ **Schema Validation**: Type-safe workflow definitions with Pydantic
- 📝 **Production-Ready Output**: Generates clean, maintainable test scripts

## Quick Start

### Prerequisites

1. **Python 3.11+** with `uv` package manager
2. **Google Cloud Project** with Vertex AI API enabled
3. **Application Default Credentials**:
   ```bash
   gcloud auth application-default login
   ```
4. **Environment Variables**:
   ```bash
   export GCP_PROJECT_ID="your-project-id"
   export GCP_LOCATION="us-central1"
   ```

### Installation

```bash
# Clone repository
git clone <repository-url>
cd automaton

# Install dependencies
uv sync

# Install Playwright browsers
uv run playwright install
```

### Usage

#### 1. Process a Screen Recording Video

```python
import asyncio
from src.video_processor import process_video_to_workflow

async def main():
    workflow = await process_video_to_workflow(
        video_path="recordings/login_flow.mp4",
        starting_url="https://example.com",
        workflow_name="User Login Flow",
        workflow_description="Complete user authentication process",
        output_json_path="workflows/login_workflow.json"
    )
    print(f"✅ Generated workflow with {len(workflow.actions)} actions")

asyncio.run(main())
```

#### 2. Generate Test Script from Workflow

```python
from src.agent import WorkflowAgent
from src.playwright_framework import PlaywrightToolkit
from src.workflow_schema import WorkflowInput

# Load workflow
workflow = WorkflowInput.model_validate_json(
    open("workflows/login_workflow.json").read()
)

# Initialize toolkit and agent
toolkit = PlaywrightToolkit(headless=False, use_vision=True)
await toolkit.initialize()

agent = WorkflowAgent(toolkit=toolkit)

# Generate test script
result = await agent.generate_test_script(
    workflow=workflow,
    output_path="tests/test_login.py"
)

await toolkit.cleanup()
```

#### 3. Run the Generated Test

```bash
uv run python tests/test_login.py
```

## Architecture

```
┌─────────────────┐
│ Screen Video    │ (WebM/MP4)
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│   VideoProcessor            │
│   (Gemini Vision AI)        │
│   - Extract frames          │
│   - Detect actions          │
│   - Generate WorkflowInput  │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────┐
│ WorkflowInput   │ (JSON)
│ - Metadata      │
│ - Actions       │
│ - Screenshots   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────┐
│   WorkflowAgent             │
│   (LangGraph + Gemini)      │
│   - Execute workflow        │
│   - Generate test script    │
└────────┬────────────────────┘
         │
         ▼
┌─────────────────┐
│ Playwright Test │ (Python)
│ - Async script  │
│ - Error handling│
│ - Assertions    │
└─────────────────┘
```

## Components

### 1. Video Processor (Task 4)
- **File**: `src/video_processor.py`
- **Purpose**: Converts screen recordings to structured workflow definitions
- **Features**:
  - OpenCV frame extraction (2 FPS default)
  - Gemini multi-modal analysis
  - Action detection (click, type, navigate, scroll, etc.)
  - Screenshot generation
- **Docs**: `docs/VIDEO_PROCESSOR.md`

### 2. Workflow Schema (Task 1)
- **File**: `src/workflow_schema.py`
- **Purpose**: Type-safe workflow definitions using Pydantic
- **Models**:
  - `WorkflowInput`: Complete workflow document
  - `WorkflowAction`: Individual user actions
  - `DOMElement`: Optional DOM details
  - `WorkflowMetadata`: Browser and viewport info

### 3. Playwright Framework (Task 2)
- **File**: `src/playwright_framework.py`
- **Purpose**: Tool-calling abstraction over Playwright
- **Tools** (12 total):
  - Navigation: `navigate_to_url`
  - Vision-based: `capture_labeled_screenshot`, `click_label`, `type_into_label`, `inspect_label`
  - Script management: `read/write/edit/save_test_script`
  - Browser control: `wait_for_selector`, `take_screenshot`, etc.

### 4. Workflow Agent (Task 3)
- **Files**: `src/agent.py`, `src/agent_nodes.py`, `src/agent_state.py`
- **Purpose**: LangGraph-based reasoning agent for test generation
- **Features**:
  - Parses and validates WorkflowInput
  - Executes workflow in live browser
  - Generates test scripts with assertions
  - Vision-based interaction (no CSS selectors needed)

## Video Recording Best Practices

### Recommended Format: WebM
**WebM is the primary supported format**, with automatic handling of metadata quirks. The processor also supports MP4, AVI, and MOV.

**Why WebM?**
- Native browser recording format
- Better compression for screen content
- Automatic metadata correction built-in
- No licensing issues

### Recording Guidelines

For best results with the video processor:

1. **Format**: Use WebM (preferred) or MP4
2. **Resolution**: Record at 1920x1080 or 1280x720
3. **Frame Rate**: 30 FPS (automatically detected)
4. **Pace**: Perform actions slowly with brief pauses
5. **Loading**: Wait for pages to fully load
6. **Focus**: Full screen browser, no dev tools
7. **Tools**: OBS Studio, Chrome screen recorder, or browser extensions

## Examples

See `examples/` directory for complete examples:
- `process_video_example.py`: Video processing demonstrations
- More examples coming soon...

## Testing

```bash
# Test video processor imports and basic functionality
uv run python test_video_processor.py

# Test vision labeling (requires browser)
uv run python test_vision.py
```

## Documentation

- **Video Processor**: `docs/VIDEO_PROCESSOR.md` - Complete guide to video-to-workflow processing
- **PRD**: `PRDs/init.md` - Project requirements and implementation details
- **Agent Usage**: `src/README_AGENT.md` - Workflow agent documentation

## Project Structure

```
automaton/
├── src/
│   ├── video_processor.py      # Task 4: Video-to-workflow processor
│   ├── workflow_schema.py      # Task 1: Pydantic workflow schema
│   ├── playwright_framework.py # Task 2: Playwright tool abstraction
│   ├── agent.py                # Task 3: LangGraph workflow agent
│   ├── agent_nodes.py          # Agent node functions
│   ├── agent_state.py          # Agent state management
│   ├── config.py               # Configuration and prompts
│   └── vision_labeler.py       # Vision-based element labeling
├── examples/
│   └── process_video_example.py
├── docs/
│   └── VIDEO_PROCESSOR.md
├── PRDs/
│   └── init.md
├── screenshots/                # Auto-generated screenshots
├── workflows/                  # Generated workflow JSONs
├── tests/                      # Generated test scripts
└── recordings/                 # Input video files
```

## Dependencies

Main dependencies (managed by `uv`):
- `playwright`: Browser automation
- `langchain-google-vertexai`: Gemini AI integration
- `langgraph`: Agent framework
- `pydantic`: Schema validation
- `opencv-python`: Video processing
- `pillow`: Image manipulation

## Limitations & Known Issues

1. **DOM Details**: Video analysis cannot extract CSS selectors - uses vision-based interaction instead
2. **Text Detection**: Typed text is inferred from visual cues (approximate)
3. **Complex Interactions**: Drag-and-drop may not be detected accurately
4. **Video Length**: Keep videos under 2 minutes for optimal results
5. **Frame Limits**: Max 20 frames analyzed due to token limits

## Future Enhancements

- [ ] OCR integration for text input detection
- [ ] Audio analysis for click detection
- [ ] Mouse cursor tracking
- [ ] Real-time video streaming
- [ ] Multi-language support
- [ ] Interactive action refinement UI

## Contributing

Contributions welcome! Areas of interest:
- Video recording best practices
- Gemini prompt improvements
- Additional test examples
- Bug reports and accuracy improvements

## License

[Your license here]
