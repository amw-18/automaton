"""
Video-to-Workflow Processor using Gemini Multi-modal AI.

This module processes screen recording videos of user workflows and generates
WorkflowInput JSON using Gemini's vision capabilities to detect user actions.
"""

import base64
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Optional

import cv2
from langchain_core.messages import HumanMessage
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel, Field

from .config import GCP_LOCATION, GCP_PROJECT_ID
from .workflow_schema import (
    Viewport,
    VisualWorkflowAction,
    WorkflowAction,
    WorkflowInput,
    WorkflowMetadata,
)


# Pydantic model for structured output from Gemini
class VideoAnalysisResult(BaseModel):
    """Result of video analysis containing all detected actions."""

    actions: list[VisualWorkflowAction] = Field(
        ..., description="List of detected user actions in chronological order"
    )
    workflow_name: Optional[str] = Field(None, description="Short name for the workflow (e.g., 'Login flow', 'Checkout process')")
    workflow_description: Optional[str] = Field(None, description="Brief description of what the workflow does")


class VideoProcessor:
    """
    Processes screen recording videos to generate WorkflowInput.

    Uses Gemini's multi-modal capabilities to analyze video files and
    detect user interactions (clicks, typing, navigation, etc.).
    """

    def __init__(
        self,
        project_id: str = GCP_PROJECT_ID,
        location: str = GCP_LOCATION,
        model_name: str = "gemini-2.5-flash",
    ):
        """
        Initialize the video processor.

        Args:
            project_id: Google Cloud project ID
            location: GCP location (e.g., 'us-central1')
            model_name: Gemini model to use
        """
        self.project_id = project_id
        self.location = location
        self.model_name = model_name

        # Initialize Gemini model
        self.llm = ChatVertexAI(
            model_name=model_name,
            project=project_id,
            location=location,
            temperature=0.2,  # Lower temperature for more consistent output
            max_output_tokens=8192,
        )
        
        # Create structured output version for action detection
        self.llm_structured = self.llm.with_structured_output(
            VideoAnalysisResult,
            method="function_calling",
            include_raw=False,
        )

    async def process_video(
        self,
        video_path: str,
        starting_url: str,
        workflow_name: str,
        workflow_description: str,
        output_json_path: Optional[str] = None,
    ) -> WorkflowInput:
        """
        Process a video and generate WorkflowInput.

        Args:
            video_path: Path to the screen recording video
            starting_url: The initial URL shown in the video
            workflow_name: Name of the workflow
            workflow_description: Description of what the workflow does
            output_json_path: Optional path to save the JSON output

        Returns:
            WorkflowInput object with detected actions
        """
        print(f"📹 Processing video: {video_path}")

        # Step 1: Analyze entire video with Gemini to detect actions and extract metadata
        print("🤖 Analyzing video with Gemini...")
        analysis_result = await self._analyze_video_with_gemini(video_path, starting_url)
        print(f"✓ Detected {len(analysis_result.actions)} actions")
        
        # Use Gemini-extracted metadata if not provided by user
        final_workflow_name = workflow_name
        final_workflow_description = workflow_description
        
        if not workflow_name and analysis_result.workflow_name:
            final_workflow_name = analysis_result.workflow_name
            print(f"  ℹ️  Using AI-extracted workflow name: {final_workflow_name}")
        
        if not workflow_description and analysis_result.workflow_description:
            final_workflow_description = analysis_result.workflow_description
            print(f"  ℹ️  Using AI-extracted description: {final_workflow_description}")

        # Step 2: Get video metadata
        video_metadata = await self._get_video_metadata(video_path)

        # Step 3: Generate WorkflowInput
        print("📝 Generating WorkflowInput...")
        workflow_input = self._generate_workflow_input(
            workflow_name=final_workflow_name,
            workflow_description=final_workflow_description,
            starting_url=starting_url,
            actions=analysis_result.actions,
            video_metadata=video_metadata,
        )

        # Step 5: Save to JSON if path provided
        if output_json_path:
            self._save_workflow_to_json(workflow_input, output_json_path)
            print(f"✓ Saved workflow to: {output_json_path}")

        print("✅ Video processing complete!")
        return workflow_input

    def _build_analysis_prompt(self, starting_url: str) -> str:
        """Build the prompt for Gemini video analysis."""
        # Generate schema from Pydantic models
        video_analysis_schema = VideoAnalysisResult.model_json_schema()
        schema_json = json.dumps(video_analysis_schema, indent=2)
        
        return f"""You are analyzing a screen recording video of a user interacting with a website.
The video starts at: {starting_url}

I'm providing you with the complete video file for analysis.

## Your Task:

Analyze the video to identify the user's workflow and extract all significant actions.

## Output Schema:

Return a JSON object that follows this exact schema:

```json
{schema_json}
```

## Guidelines:

- Focus on significant actions that accomplish the user's goal
- Ignore minor mouse movements and visual-only changes
- Describe UI elements clearly for automation purposes
- Look for visual cues like button states, form changes, page transitions
- Infer text input from visible form field changes
- Order actions chronologically as they appear in the video
- Be precise about action types
- Only include fields that are relevant to each action type
- Use null for optional fields that don't apply

Analyze the video now and provide the workflow metadata and all detected actions according to the schema above."""

    def _parse_gemini_response(
        self, response_text: str
    ) -> list[dict[str, Any]]:
        """
        Parse Gemini's response to extract action data.

        Args:
            response_text: Raw response from Gemini

        Returns:
            List of action dictionaries
        """
        import json
        import re

        # Extract JSON from response (handle code blocks)
        json_match = re.search(r"```json\s*(\[.*?\])\s*```", response_text, re.DOTALL)
        if json_match:
            json_text = json_match.group(1)
        else:
            # Try to find JSON array directly
            json_match = re.search(r"(\[.*\])", response_text, re.DOTALL)
            if json_match:
                json_text = json_match.group(1)
            else:
                print("⚠️ No valid JSON found in Gemini response")
                print(f"Response: {response_text[:500]}")
                return []

        try:
            actions = json.loads(json_text)
            return actions
        except json.JSONDecodeError as e:
            print(f"⚠️ Failed to parse JSON: {e}")
            print(f"JSON text: {json_text[:500]}")
            return []

    async def _analyze_video_with_gemini(
        self, video_path: str, starting_url: str
    ) -> VideoAnalysisResult:
        """
        Analyze entire video using Gemini to detect user actions and extract workflow metadata.
        Sends the complete video file instead of individual frames for cost efficiency.

        Args:
            video_path: Path to the video file
            starting_url: Starting URL of the workflow

        Returns:
            VideoAnalysisResult with actions, workflow_name, and workflow_description
        """
        print(f"  Analyzing entire video file: {video_path}")

        # Build the prompt for Gemini
        prompt = self._build_analysis_prompt(starting_url)

        # Read and encode the entire video file
        with open(video_path, "rb") as video_file:
            video_data = base64.b64encode(video_file.read()).decode("utf-8")

        # Create message with video
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "media",
                "mime_type": "video/mp4",
                "data": video_data,
            },
        ]

        message = HumanMessage(content=content)  # pyright: ignore[reportArgumentType]

        # Call Gemini with structured output
        print("  Calling Gemini with structured output...")
        try:
            result: VideoAnalysisResult = await self.llm_structured.ainvoke([message])
            
            if result.workflow_name:
                print(f"  Workflow name: {result.workflow_name}")
            if result.workflow_description:
                print(f"  Workflow description: {result.workflow_description}")
            
            # Return full VideoAnalysisResult
            return result
        except Exception as e:
            print(f"⚠️ Structured output failed: {e}")
            print(f"  Error details: {str(e)}")
            print("  Falling back to manual parsing...")
            
            # Fallback to unstructured call
            response = await self.llm.ainvoke([message])
            actions_dict = self._parse_gemini_response(response.content)
            return VideoAnalysisResult(
                actions=[VisualWorkflowAction(**action) for action in actions_dict],
                workflow_name=None,
                workflow_description=None,
            )

    async def _get_video_metadata(self, video_path: str) -> dict[str, Any]:
        """
        Extract metadata from video file.
        Uses robust extraction that handles WebM and other formats.
        """
        cap = cv2.VideoCapture(video_path)

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Validate and correct metadata
        if fps <= 0 or fps > 500:
            fps = 30.0  # Default to 30 FPS for WebM

        if total_frames <= 0 or total_frames > 1_000_000:
            # Count frames manually
            total_frames = 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            while cap.grab():
                total_frames += 1
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

        if width <= 0:
            width = 1920  # Default HD width
        if height <= 0:
            height = 1080  # Default HD height

        duration_sec = total_frames / fps if fps > 0 else 0

        cap.release()

        return {
            "fps": fps,
            "width": width,
            "height": height,
            "total_frames": total_frames,
            "duration_sec": duration_sec,
        }

    def _generate_workflow_input(
        self,
        workflow_name: str,
        workflow_description: str,
        starting_url: str,
        actions: list[VisualWorkflowAction],
        video_metadata: dict[str, Any],
    ) -> WorkflowInput:
        """
        Generate WorkflowInput from detected actions.

        Args:
            workflow_name: Name of the workflow
            workflow_description: Description of the workflow
            starting_url: Starting URL
            actions: Detected actions from Gemini
            video_metadata: Video metadata

        Returns:
            WorkflowInput object
        """
        # Create metadata
        metadata = WorkflowMetadata(
            name=workflow_name,
            description=workflow_description,
            created_at=datetime.now().isoformat(),
            browser="chromium",  # Default to chromium
            viewport=Viewport(width=video_metadata["width"], height=video_metadata["height"]),
        )

        # Convert VisualWorkflowAction to WorkflowAction
        workflow_actions = []

        for idx, visual_action in enumerate(actions):
            # Create WorkflowAction from VisualWorkflowAction (without screenshots)
            workflow_action = WorkflowAction(
                action_type=visual_action.action_type,
                description=visual_action.description,
                target_url=visual_action.target_url,
                input_text=visual_action.input_text,
                expected_outcome=visual_action.expected_outcome,
            )

            workflow_actions.append(workflow_action)

        # Create WorkflowInput
        workflow_input = WorkflowInput(
            metadata=metadata,
            starting_url=starting_url,
            actions=workflow_actions,
            expected_final_state=workflow_description,
        )

        return workflow_input

    def _save_workflow_to_json(self, workflow_input: WorkflowInput, output_path: str) -> None:
        """Save WorkflowInput to JSON file."""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            _ = f.write(workflow_input.model_dump_json(indent=2))


# Convenience function for direct usage
async def process_video_to_workflow(
    video_path: str,
    starting_url: str,
    workflow_name: str,
    workflow_description: str,
    output_json_path: Optional[str] = None,
    project_id: str = GCP_PROJECT_ID,
    location: str = GCP_LOCATION,
) -> WorkflowInput:
    """
    Process a video and generate WorkflowInput JSON.

    Args:
        video_path: Path to the screen recording video
        starting_url: The initial URL shown in the video
        workflow_name: Name of the workflow
        workflow_description: Description of what the workflow does
        output_json_path: Optional path to save the JSON output
        project_id: Google Cloud project ID
        location: GCP location

    Returns:
        WorkflowInput object

    Example:
        >>> workflow = await process_video_to_workflow(
        ...     video_path="recordings/login_flow.mp4",
        ...     starting_url="https://example.com",
        ...     workflow_name="User Login Flow",
        ...     workflow_description="Complete user authentication process",
        ...     output_json_path="workflows/login_workflow.json"
        ... )
    """
    processor = VideoProcessor(project_id=project_id, location=location)
    return await processor.process_video(
        video_path=video_path,
        starting_url=starting_url,
        workflow_name=workflow_name,
        workflow_description=workflow_description,
        output_json_path=output_json_path,
    )
