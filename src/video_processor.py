"""
Video-to-Workflow Processor using Gemini Multi-modal AI.

This module processes screen recording videos of user workflows and generates
WorkflowInput JSON using Gemini's vision capabilities to detect user actions.
"""

import base64
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import cv2
from langchain_core.messages import HumanMessage
from langchain_google_vertexai import ChatVertexAI

from .config import GCP_LOCATION, GCP_PROJECT_ID
from .workflow_schema import (
    Viewport,
    WorkflowAction,
    WorkflowInput,
    WorkflowMetadata,
)


class VideoFrame:
    """Represents a single frame from the video."""

    def __init__(self, frame_number: int, timestamp_ms: float, image: bytes):
        self.frame_number: int = frame_number
        self.timestamp_ms: float = timestamp_ms
        self.image: bytes = image  # PNG bytes
        self.base64_image: str = base64.b64encode(image).decode("utf-8")


class VideoProcessor:
    """
    Processes screen recording videos to generate WorkflowInput.

    Uses Gemini's multi-modal capabilities to analyze video frames and
    detect user interactions (clicks, typing, navigation, etc.).
    """

    def __init__(
        self,
        project_id: str = GCP_PROJECT_ID,
        location: str = GCP_LOCATION,
        model_name: str = "gemini-2.5-flash",
        frame_sample_rate: int = 2,  # Extract 2 frames per second
        min_frame_interval_ms: int = 500,  # Minimum 500ms between frames
    ):
        """
        Initialize the video processor.

        Args:
            project_id: Google Cloud project ID
            location: GCP location (e.g., 'us-central1')
            model_name: Gemini model to use
            frame_sample_rate: Frames to extract per second
            min_frame_interval_ms: Minimum time between sampled frames
        """
        self.project_id = project_id
        self.location = location
        self.model_name = model_name
        self.frame_sample_rate = frame_sample_rate
        self.min_frame_interval_ms = min_frame_interval_ms

        # Initialize Gemini model
        self.llm = ChatVertexAI(
            model_name=model_name,
            project=project_id,
            location=location,
            temperature=0.2,  # Lower temperature for more consistent output
            max_output_tokens=8192,
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

        # Step 1: Extract frames from video
        print("🎬 Extracting frames...")
        frames = await self._extract_frames(video_path)
        print(f"✓ Extracted {len(frames)} frames")

        # Step 2: Analyze frames with Gemini to detect actions
        print("🤖 Analyzing video with Gemini...")
        detected_actions = await self._analyze_video_with_gemini(frames, starting_url)
        print(f"✓ Detected {len(detected_actions)} actions")

        # Step 3: Get video metadata
        video_metadata = await self._get_video_metadata(video_path)

        # Step 4: Generate WorkflowInput
        print("📝 Generating WorkflowInput...")
        workflow_input = self._generate_workflow_input(
            workflow_name=workflow_name,
            workflow_description=workflow_description,
            starting_url=starting_url,
            actions=detected_actions,
            video_metadata=video_metadata,
            frames=frames,
        )

        # Step 5: Save to JSON if path provided
        if output_json_path:
            self._save_workflow_to_json(workflow_input, output_json_path)
            print(f"✓ Saved workflow to: {output_json_path}")

        print("✅ Video processing complete!")
        return workflow_input

    async def _extract_frames(self, video_path: str) -> list[VideoFrame]:
        """
        Extract frames from video at specified sample rate.
        Handles WebM and other formats with unreliable metadata.

        Args:
            video_path: Path to video file

        Returns:
            List of VideoFrame objects
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"Failed to open video: {video_path}")

        # Get metadata from OpenCV
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # Validate metadata - WebM files often have invalid metadata
        metadata_valid = (
            fps > 0
            and fps < 500  # Reasonable FPS range
            and total_frames > 0
            and total_frames < 1_000_000  # Reasonable frame count
            and width > 0
            and height > 0
        )

        if not metadata_valid:
            print(
                f"  ⚠️  Video metadata unreliable (FPS={fps:.2f}, frames={total_frames})"
            )
            print("  Counting frames manually (this may take a moment)...")

            # Count frames manually and estimate FPS
            actual_frame_count = 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # Reset to start
            while True:
                ret = cap.grab()  # Faster than read()
                if not ret:
                    break
                actual_frame_count += 1

            # Estimate FPS based on video format
            # WebM screen recordings are typically 30 FPS
            fps = 30.0
            total_frames = actual_frame_count
            print(f"  ✓ Counted {actual_frame_count} frames, assuming {fps:.0f} FPS")
            
            # Close and reopen video - WebM files don't seek reliably after grab()
            cap.release()
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                raise ValueError(f"Failed to reopen video after counting frames")
        else:
            print(f"  Video: {fps:.2f} FPS, {total_frames} frames")

        duration_sec = total_frames / fps if fps > 0 else 0
        print(f"  Duration: {duration_sec:.2f}s, Resolution: {width}x{height}")

        # Calculate frame interval
        # For unreliable metadata, always use calculated timestamps
        if not metadata_valid:
            # For WebM with bad metadata, calculate timestamps from frame number
            print(f"  Using calculated timestamps: {self.min_frame_interval_ms}ms intervals")
            use_calculated_timestamps = True
        elif fps > 100:
            # Very high FPS, use time-based sampling
            print(f"  Using time-based sampling: {self.min_frame_interval_ms}ms intervals")
            use_calculated_timestamps = False
        else:
            # Normal video with good metadata
            frame_interval = max(1, int(fps / self.frame_sample_rate))
            print(f"  Sampling every {frame_interval} frames")
            use_calculated_timestamps = False

        frames: list[VideoFrame] = []
        last_timestamp = -self.min_frame_interval_ms
        frame_num = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Calculate timestamp
            if use_calculated_timestamps or metadata_valid is False:
                # For bad metadata, always calculate from frame number
                timestamp_ms = (frame_num / fps) * 1000
            else:
                # For good metadata, try to use actual position
                timestamp_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                if timestamp_ms == 0 and frame_num > 0:
                    # Fallback to calculated if position is unreliable
                    timestamp_ms = (frame_num / fps) * 1000

            # Sample if enough time has passed
            if timestamp_ms - last_timestamp >= self.min_frame_interval_ms:
                # Convert frame to PNG bytes
                is_success, buffer = cv2.imencode(".png", frame)
                if is_success:
                    png_bytes = buffer.tobytes()
                    video_frame = VideoFrame(frame_num, timestamp_ms, png_bytes)
                    frames.append(video_frame)
                    last_timestamp = timestamp_ms

            frame_num += 1

        cap.release()

        if not frames:
            raise ValueError(
                f"No frames extracted from video. Video may be corrupt or empty."
            )

        print(f"  ✓ Extracted {len(frames)} frames for analysis")
        return frames

    async def _analyze_video_with_gemini(
        self, frames: list[VideoFrame], starting_url: str
    ) -> list[dict[str, Any]]:
        """
        Analyze video frames using Gemini to detect user actions.

        Args:
            frames: List of extracted video frames
            starting_url: Starting URL of the workflow

        Returns:
            List of detected actions as dictionaries
        """
        # Prepare frames for Gemini (limit to avoid token limits)
        # Use key frames: first, last, and evenly distributed middle frames
        max_frames = 20  # Limit frames to avoid overwhelming the model
        selected_frames = self._select_key_frames(frames, max_frames)

        # Build the prompt for Gemini
        prompt = self._build_analysis_prompt(starting_url, len(selected_frames))

        # Create message with images
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]

        # Add frame images
        for idx, frame in enumerate(selected_frames):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{frame.base64_image}"},
                }
            )

        message = HumanMessage(content=content)  # pyright: ignore[reportArgumentType]

        # Call Gemini
        response = await self.llm.ainvoke([message])

        # Parse response to extract actions
        actions = self._parse_gemini_response(response.content, selected_frames)

        return actions

    def _select_key_frames(self, frames: list[VideoFrame], max_frames: int) -> list[VideoFrame]:
        """
        Select key frames from the video for analysis.

        Args:
            frames: All extracted frames
            max_frames: Maximum number of frames to select

        Returns:
            List of selected key frames
        """
        if len(frames) <= max_frames:
            return frames

        # Always include first and last frame
        selected = [frames[0]]

        # Select evenly distributed frames from the middle
        middle_count = max_frames - 2
        if middle_count > 0:
            step = (len(frames) - 2) / middle_count
            for i in range(middle_count):
                idx = int(1 + i * step)
                if idx < len(frames) - 1:
                    selected.append(frames[idx])

        # Add last frame
        selected.append(frames[-1])

        return selected

    def _build_analysis_prompt(self, starting_url: str, num_frames: int) -> str:
        """Build the prompt for Gemini video analysis."""
        return f"""You are analyzing a screen recording video of a user interacting with a website.
The video starts at: {starting_url}

I'm providing you with {num_frames} key frames from this video. Your task is to:

1. **Identify user actions** in chronological order by comparing consecutive frames
2. **Detect changes** that indicate interactions:
   - Mouse clicks (buttons, links, navigation items)
   - Text input (typing into fields)
   - Page navigation (URL changes, new pages loading)
   - Scrolling
   - Dropdown selections
   - Hover effects

3. **For each detected action**, provide:
   - **action_type**: One of: click, type, navigate, scroll, select, hover, wait
   - **description**: Clear description of what the user did
   - **approximate_timestamp**: Frame number or relative time (e.g., "2.5s")
   - **element_description**: Description of the UI element (e.g., "Submit button", "Email input field")
   - **input_text**: (For 'type' actions only) What text was entered
   - **target_url**: (For 'navigate' actions only) The new URL
   - **expected_outcome**: What should happen after this action

4. **Focus on significant actions** - ignore minor mouse movements or purely visual changes

Return your analysis as a JSON array of actions in this format:
```json
[
  {{
    "action_type": "click",
    "description": "Click on the Login button",
    "approximate_timestamp": "1.5s",
    "element_description": "Blue 'Login' button in the top right corner",
    "expected_outcome": "Login form modal appears"
  }},
  {{
    "action_type": "type",
    "description": "Enter email address",
    "approximate_timestamp": "3.0s",
    "element_description": "Email input field in login form",
    "input_text": "user@example.com"
  }},
  {{
    "action_type": "navigate",
    "description": "Page redirected to dashboard",
    "approximate_timestamp": "5.5s",
    "target_url": "{starting_url}/dashboard",
    "expected_outcome": "Dashboard page loads with user content"
  }}
]
```

IMPORTANT:
- Only return the JSON array, no additional text
- Ensure valid JSON syntax
- Be precise about action types
- Describe elements clearly for future automation
- Estimate timestamps based on frame sequence

Analyze the frames now:"""

    def _parse_gemini_response(
        self, response_text: str, frames: list[VideoFrame]
    ) -> list[dict[str, Any]]:
        """
        Parse Gemini's response to extract action data.

        Args:
            response_text: Raw response from Gemini
            frames: The frames that were analyzed

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
        actions: list[dict[str, Any]],
        video_metadata: dict[str, Any],
        frames: list[VideoFrame],
    ) -> WorkflowInput:
        """
        Generate WorkflowInput from detected actions.

        Args:
            workflow_name: Name of the workflow
            workflow_description: Description of the workflow
            starting_url: Starting URL
            actions: Detected actions from Gemini
            video_metadata: Video metadata
            frames: Extracted video frames

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

        # Convert detected actions to WorkflowAction objects
        workflow_actions = []
        base_time = datetime.now()

        for idx, action_data in enumerate(actions):
            # Parse timestamp
            timestamp_str = action_data.get("approximate_timestamp", f"{idx}s")
            # Extract seconds from string like "2.5s"
            try:
                seconds = float(timestamp_str.replace("s", "").strip())
            except:
                seconds = idx * 2  # Default to 2 seconds per action

            action_time = base_time + timedelta(seconds=seconds)

            # Save screenshot for this action if available
            screenshot_path = None
            if frames:
                # Find closest frame to this timestamp
                target_ms = seconds * 1000
                closest_frame = min(frames, key=lambda f: abs(f.timestamp_ms - target_ms))
                screenshot_dir = Path("screenshots")
                screenshot_dir.mkdir(exist_ok=True)
                screenshot_path = str(
                    screenshot_dir / f"action_{idx + 1}_frame_{closest_frame.frame_number}.png"
                )
                with open(screenshot_path, "wb") as f:
                    f.write(closest_frame.image)

            # Create WorkflowAction
            action_type = action_data.get("action_type", "click")

            workflow_action = WorkflowAction(
                timestamp=action_time.isoformat(),
                action_type=action_type,
                description=action_data.get("description", ""),
                screenshot_url=screenshot_path,
                target_url=action_data.get("target_url"),
                input_text=action_data.get("input_text"),
                expected_outcome=action_data.get("expected_outcome"),
                # Note: DOM element details not available from video
                # Could be enhanced by OCR or additional analysis
                dom_element=None,
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
