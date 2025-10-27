"""
Test Execution Service

Runs generated Playwright test scripts in a Docker container with video recording.
Returns the execution video to the user.
"""

import sys
from pathlib import Path
import asyncio
import shutil
import json
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from models.session import session_manager
from services.stream_service import stream_manager


class TestExecutionService:
    """Service for executing generated Playwright tests in Docker"""
    
    def __init__(self):
        self.docker_image = "playwright-runner:latest"
        self.docker_dir = Path(__file__).parent.parent / "docker"
        
    async def ensure_docker_image(self) -> bool:
        """
        Ensure the Docker image is built and ready
        Returns True if image exists or was built successfully
        """
        try:
            # Check if image exists
            check_cmd = ["docker", "images", "-q", self.docker_image]
            process = await asyncio.create_subprocess_exec(
                *check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()
            
            if stdout.strip():
                print(f"✅ Docker image {self.docker_image} already exists")
                return True
            
            # Build the image
            print(f"🔨 Building Docker image {self.docker_image}...")
            build_cmd = [
                "docker", "build",
                "-f", str(self.docker_dir / "Dockerfile.playwright-runner"),
                "-t", self.docker_image,
                str(self.docker_dir)
            ]
            
            process = await asyncio.create_subprocess_exec(
                *build_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            _, stderr = await process.communicate()
            
            if process.returncode == 0:
                print(f"✅ Successfully built {self.docker_image}")
                return True
            else:
                print(f"❌ Failed to build Docker image: {stderr.decode()}")
                return False
                
        except Exception as e:
            print(f"❌ Error checking/building Docker image: {e}")
            return False
    
    async def run_test(self, session_id: str):
        """
        Execute the generated test script in Docker with video recording
        
        Args:
            session_id: Session UUID
        """
        session = session_manager.get_session(session_id)
        if not session or not session.script_path:
            raise ValueError(f"No generated script found for session {session_id}")
        
        # Update status
        session_manager.update_status(session_id, "testing")
        await stream_manager.broadcast_status(
            session_id,
            "testing",
            {"message": "Preparing test execution environment..."}
        )
        
        # Ensure Docker image is ready
        if not await self.ensure_docker_image():
            error_msg = "Failed to prepare Docker environment"
            session.add_event("test_error", {"error": error_msg})
            session_manager.update_status(session_id, "test_failed")
            session_manager.save_session(session)
            
            await stream_manager.broadcast_status(
                session_id,
                "test_failed",
                {"error": error_msg}
            )
            return
        
        try:
            # Setup paths
            session_dir = Path(session.video_path).parent
            script_path = Path(session.script_path)
            test_output_dir = session_dir / "test_output"
            test_output_dir.mkdir(exist_ok=True)
            
            # Copy the generated callback script to test_output_dir as test_generated.py
            # This allows the wrapper to import it
            callback_script_path = test_output_dir / "test_generated.py"
            callback_script_path.write_text(script_path.read_text())
            
            # Create wrapper script with browser setup and video recording
            wrapper_script = await self._prepare_test_script_with_video(
                script_path,
                test_output_dir
            )
            
            # Save wrapper script
            wrapper_script_path = test_output_dir / "test_with_recording.py"
            wrapper_script_path.write_text(wrapper_script)
            
            await stream_manager.broadcast_status(
                session_id,
                "testing",
                {"message": "Starting test execution in Docker container..."}
            )
            
            # Run test in Docker (mounts the entire test_output_dir so imports work)
            success, video_path, error_msg = await self._run_in_docker(
                session_id,
                wrapper_script_path,
                test_output_dir
            )
            
            # Save video path to session if available (even on failure)
            if video_path:
                session.test_video_path = str(video_path)
            
            if success:
                # Test passed
                session.add_event("test_complete", {
                    "video_path": str(video_path) if video_path else None,
                    "success": True
                })
                session_manager.update_status(session_id, "test_complete")
                
                # Make path relative to uploads for URL
                rel_video_path = Path(video_path).relative_to(Path("uploads")) if video_path else None
                
                await stream_manager.broadcast_status(
                    session_id,
                    "test_complete",
                    {
                        "message": "Test execution completed successfully",
                        "video_path": str(rel_video_path) if rel_video_path else None
                    }
                )
                
                print(f"✅ Test execution completed successfully")
                if video_path:
                    print(f"   Video: {video_path}")
                
            else:
                # Test failed
                event_data = {"error": error_msg or "Unknown error"}
                if video_path:
                    event_data["video_path"] = str(video_path)
                
                session.add_event("test_error", event_data)
                session_manager.update_status(session_id, "test_failed")
                
                # Make path relative to uploads for URL
                rel_video_path = Path(video_path).relative_to(Path("uploads")) if video_path else None
                
                status_data = {"error": error_msg or "Test execution failed"}
                if rel_video_path:
                    status_data["video_path"] = str(rel_video_path)
                
                await stream_manager.broadcast_status(
                    session_id,
                    "test_failed",
                    status_data
                )
                
                print(f"❌ Test execution failed: {error_msg}")
                if video_path:
                    print(f"   Video available: {video_path}")
            
            session_manager.save_session(session)
            
        except Exception as e:
            error_msg = str(e)
            session.add_event("test_error", {"error": error_msg})
            session_manager.update_status(session_id, "test_failed")
            session_manager.save_session(session)
            
            await stream_manager.broadcast_status(
                session_id,
                "test_failed",
                {"error": error_msg}
            )
            
            print(f"❌ Test execution error: {e}")
            raise
    
    async def _prepare_test_script_with_video(
        self,
        original_script_path: Path,
        output_dir: Path
    ) -> str:
        """
        Create a wrapper script that imports and executes the generated callback
        
        Args:
            original_script_path: Path to the generated callback script
            output_dir: Directory where video should be saved
            
        Returns:
            Wrapper script content that sets up browser and calls the callback
        """
        # Get workflow metadata to extract viewport settings
        from models.session import session_manager
        session_id = original_script_path.parts[-3]  # Extract from path
        session = session_manager.get_session(session_id)
        
        # Default viewport
        viewport_width = 1280
        viewport_height = 720
        
        # Get viewport from workflow metadata if available
        if session and session.workflow and session.workflow.metadata:
            viewport = session.workflow.metadata.viewport
            viewport_width = viewport.width
            viewport_height = viewport.height
        
        # Create wrapper script that imports and executes the callback
        wrapper_script = f'''"""
Test execution wrapper - imports and runs the generated test callback
"""
import asyncio
import sys
import os
from pathlib import Path
from playwright.async_api import async_playwright

# Add the script directory to path so we can import the callback
sys.path.insert(0, str(Path(__file__).parent))

# Import the test_actions callback from the generated script
from test_generated import test_actions

VIDEO_OUTPUT_DIR = "/test/videos"
os.makedirs(VIDEO_OUTPUT_DIR, exist_ok=True)

async def run_test():
    """Run the test with proper browser setup and video recording"""
    async with async_playwright() as p:
        # Launch browser (headless for Docker execution)
        browser = await p.chromium.launch(headless=True)
        
        # Create context with video recording and viewport from workflow
        context = await browser.new_context(
            viewport={{"width": {viewport_width}, "height": {viewport_height}}},
            record_video_dir=VIDEO_OUTPUT_DIR,
            record_video_size={{"width": {viewport_width}, "height": {viewport_height}}}
        )
        
        try:
            # Execute the generated test actions - pass context for full control
            # The callback can create pages, open tabs, etc.
            await test_actions(context)
            print("✅ Test completed successfully!")
            
        except Exception as e:
            print(f"❌ Test failed: {{e}}")
            import traceback
            traceback.print_exc()
            raise
            
        finally:
            # CRITICAL: Close context first to save video, then browser
            print("Closing browser and saving video...")
            await context.close()
            await browser.close()
            print("Browser closed, video should be saved")

if __name__ == "__main__":
    asyncio.run(run_test())
'''
        
        return wrapper_script
    
    async def _run_in_docker(
        self,
        session_id: str,
        script_path: Path,
        output_dir: Path
    ) -> tuple[bool, Optional[Path], Optional[str]]:
        """
        Run the test script in Docker container
        
        Args:
            session_id: Session UUID
            script_path: Path to the test script
            output_dir: Directory for test outputs
            
        Returns:
            Tuple of (success, video_path, error_message)
        """
        try:
            # Docker run command with volume mounts
            # Mount entire output_dir to allow imports (test_generated.py + wrapper)
            docker_cmd = [
                "docker", "run",
                "--rm",  # Remove container after execution
                "-v", f"{output_dir.absolute()}:/test:rw",  # Mount entire test directory
                "--network", "host",  # Allow network access for web navigation
                self.docker_image,
                "python", "/test/test_with_recording.py"  # Run the wrapper script
            ]
            
            print(f"🐳 Running Docker command: {' '.join(docker_cmd)}")
            
            # Run the container
            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            # Log output
            if stdout:
                print(f"📄 Docker stdout:\n{stdout.decode()}")
            if stderr:
                print(f"📄 Docker stderr:\n{stderr.decode()}")
            
            # Extract video REGARDLESS of test success/failure
            # Video is saved in /test/videos which maps to output_dir/videos
            video_dir = output_dir / "videos"
            video_files = []
            
            if video_dir.exists():
                video_files = list(video_dir.glob("*.webm")) + list(video_dir.glob("*.mp4"))
            
            if not video_files:
                # Fallback: search entire output directory
                video_files = list(output_dir.rglob("*.webm")) + list(output_dir.rglob("*.mp4"))
            
            final_video_path = None
            if video_files:
                # Use the first video file found
                video_path = video_files[0]
                
                # Copy to a standard location (don't move due to Docker permission issues)
                final_video_path = output_dir / "test_execution.webm"
                if video_path != final_video_path:
                    try:
                        # Try to copy instead of move to avoid permission issues
                        shutil.copy2(str(video_path), str(final_video_path))
                        print(f"📹 Copied video to: {final_video_path}")
                        
                        # Try to remove original, but don't fail if we can't
                        try:
                            video_path.unlink()
                        except PermissionError:
                            print(f"⚠️  Could not remove original video (permission denied), keeping both")
                    except PermissionError as e:
                        # If we can't even copy, just use the original path
                        print(f"⚠️  Permission issue, using original video path: {video_path}")
                        final_video_path = video_path
                else:
                    final_video_path = video_path
                
                print(f"📹 Video available at: {final_video_path}")
            else:
                print("⚠️  No video file found")
            
            # Now check if test succeeded
            if process.returncode != 0:
                error_msg = f"Test execution failed with exit code {process.returncode}"
                if stderr:
                    error_msg += f": {stderr.decode()}"
                # Return video even on failure
                return False, final_video_path, error_msg
            
            # Test succeeded
            if final_video_path:
                return True, final_video_path, None
            else:
                return True, None, "Test completed but no video was recorded"
            
        except Exception as e:
            return False, None, f"Docker execution error: {str(e)}"


# Global instance
test_execution_service = TestExecutionService()
