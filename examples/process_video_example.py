"""
Example: Process a screen recording video to generate a workflow.

This example demonstrates how to use the VideoProcessor to analyze
a screen recording and generate a WorkflowInput JSON.

PREREQUISITES:
1. Google Cloud credentials set up (vertex-ai-credentials.json in project root)
2. Set GOOGLE_APPLICATION_CREDENTIALS environment variable:
   export GOOGLE_APPLICATION_CREDENTIALS="vertex-ai-credentials.json"
3. Or use Application Default Credentials:
   gcloud auth application-default login
"""

import asyncio
import os
import sys
from pathlib import Path

# Add parent directory to path to import src modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.video_processor import process_video_to_workflow


def check_credentials():
    """Check if Google Cloud credentials are configured."""
    creds_file = Path("vertex-ai-credentials.json")
    env_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    if creds_file.exists() and not env_creds:
        print("📍 Found vertex-ai-credentials.json")
        print("   Setting GOOGLE_APPLICATION_CREDENTIALS environment variable...")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_file.absolute())
        return True
    elif env_creds:
        print(f"📍 Using credentials from: {env_creds}")
        return True
    else:
        print("❌ Google Cloud credentials not found!")
        print("\nPlease set up credentials using one of these methods:")
        print("1. Copy your credentials file to: vertex-ai-credentials.json")
        print("2. Set GOOGLE_APPLICATION_CREDENTIALS environment variable")
        print("3. Run: gcloud auth application-default login")
        return False


async def main():
    """Process a video and generate workflow JSON."""
    
    # Check credentials first
    if not check_credentials():
        return

    # Example 1: Basic usage
    print("\n" + "=" * 60)
    print("Example 1: Processing a login flow video")
    print("=" * 60)

    workflow = await process_video_to_workflow(
        video_path="recordings/login_flow.webm",  # Path to your WebM screen recording
        starting_url="https://example.com",  # Starting URL in the video
        workflow_name="User Login Flow",
        workflow_description="Complete user authentication process with email and password",
        output_json_path="workflows/login_workflow.json",  # Output JSON path
    )

    print(f"\n✅ Workflow generated successfully!")
    print(f"  Name: {workflow.metadata.name}")
    print(f"  Actions: {len(workflow.actions)}")
    print(f"  Starting URL: {workflow.starting_url}")

    # Print detected actions
    print(f"\n📋 Detected Actions:")
    for idx, action in enumerate(workflow.actions, 1):
        print(f"  {idx}. [{action.action_type}] {action.description}")
        if action.input_text:
            print(f"     Input: {action.input_text}")
        if action.expected_outcome:
            print(f"     Expected: {action.expected_outcome}")

    # Example 2: Using VideoProcessor directly for more control
    print("\n" + "=" * 60)
    print("Example 2: Using VideoProcessor class directly")
    print("=" * 60)

    from src.video_processor import VideoProcessor

    processor = VideoProcessor(
        frame_sample_rate=3,  # Extract 3 frames per second
        min_frame_interval_ms=300,  # Minimum 300ms between frames
    )

    workflow2 = await processor.process_video(
        video_path="recordings/checkout_flow.webm",
        starting_url="https://shop.example.com",
        workflow_name="E-commerce Checkout",
        workflow_description="Complete product purchase from cart to confirmation",
        output_json_path="workflows/checkout_workflow.json",
    )

    print(f"\n✅ Second workflow generated!")
    print(f"  Actions: {len(workflow2.actions)}")

    # Example 3: Validate and inspect the generated workflow
    print("\n" + "=" * 60)
    print("Example 3: Inspecting generated workflow JSON")
    print("=" * 60)

    # Convert to dict for inspection
    workflow_dict = workflow.model_dump()

    print(f"\nMetadata:")
    print(f"  Browser: {workflow_dict['metadata']['browser']}")
    print(
        f"  Viewport: {workflow_dict['metadata']['viewport']['width']}x{workflow_dict['metadata']['viewport']['height']}"
    )
    print(f"  Created: {workflow_dict['metadata']['created_at']}")

    print(f"\nFirst Action Details:")
    if workflow_dict["actions"]:
        first_action = workflow_dict["actions"][0]
        print(f"  Type: {first_action['action_type']}")
        print(f"  Description: {first_action['description']}")
        print(f"  Timestamp: {first_action['timestamp']}")
        if first_action.get("screenshot_url"):
            print(f"  Screenshot: {first_action['screenshot_url']}")

    # Example 4: Use the workflow with the agent
    print("\n" + "=" * 60)
    print("Example 4: Using workflow with WorkflowAgent")
    print("=" * 60)

    print(
        """
To use the generated workflow with the agent:

```python
from src.agent import WorkflowAgent
from src.playwright_framework import PlaywrightToolkit
from src.workflow_schema import WorkflowInput

# Load the workflow
workflow = WorkflowInput.model_validate_json(
    open("workflows/login_workflow.json").read()
)

# Initialize toolkit and agent
toolkit = PlaywrightToolkit(headless=False)
await toolkit.initialize()

agent = WorkflowAgent(toolkit=toolkit)

# Generate test script from workflow
result = await agent.generate_test_script(
    workflow=workflow,
    output_path="tests/test_login.py"
)

await toolkit.cleanup()
```
    """
    )


if __name__ == "__main__":
    # Check credentials first
    if not check_credentials():
        sys.exit(1)
    
    # Check if video file is provided as argument
    if len(sys.argv) > 1:
        video_path = sys.argv[1]
        
        if not os.path.exists(video_path):
            print(f"❌ Video file not found: {video_path}")
            sys.exit(1)

        async def process_custom_video():
            workflow = await process_video_to_workflow(
                video_path=video_path,
                starting_url="https://example.com",
                workflow_name="Test Workflow",
                workflow_description="Test workflow description",
                output_json_path=f"workflows/{Path(video_path).stem}_workflow.json",
            )
            print(f"\n✅ Workflow saved to: workflows/{Path(video_path).stem}_workflow.json")

        asyncio.run(process_custom_video())
    else:
        # Run examples
        print("💡 Tip: Run with a video file argument to process your own recording:")
        print(f"   python {sys.argv[0]} recordings/your_video.webm\n")
        asyncio.run(main())
