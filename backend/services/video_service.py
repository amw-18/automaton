import sys
from pathlib import Path

# Add parent directory to path to import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.video_processor import VideoProcessor
from src.workflow_schema import WorkflowInput
from models.session import session_manager
from services.stream_service import stream_manager
import json

class VideoService:
    """Service for processing uploaded videos"""
    
    def __init__(self):
        self.video_processor = VideoProcessor()
    
    async def process_video(
        self, 
        session_id: str,
        starting_url: str,
        workflow_name: str,
        workflow_description: str
    ) -> WorkflowInput:
        """
        Process uploaded video and generate WorkflowInput
        
        Args:
            session_id: Session UUID
            
        Returns:
            WorkflowInput JSON
            
        Raises:
            Exception if video not found or processing fails
        """
        session = session_manager.get_session(session_id)
        if not session or not session.video_path:
            raise ValueError(f"No video found for session {session_id}")
        
        # Update status
        session_manager.update_status(session_id, "processing")
        await stream_manager.broadcast_status(
            session_id, 
            "processing",
            {"message": "Analyzing video..."}
        )
        
        try:
            # Process video using existing VideoProcessor
            print(f"🎬 Processing video: {session.video_path}")
            print(f"   Starting URL: {starting_url}")
            print(f"   Workflow Name: {workflow_name}")
            print(f"   Description: {workflow_description}")
            
            # Save workflow JSON to session directory
            session_dir = Path(session.video_path).parent
            workflow_path = session_dir / "workflow.json"
            
            # Process video with user-provided parameters
            workflow = await self.video_processor.process_video(
                video_path=session.video_path,
                starting_url=starting_url,
                workflow_name=workflow_name,
                workflow_description=workflow_description,
                output_json_path=str(workflow_path)
            )
            
            print(f"✅ Workflow saved to: {workflow_path}")
            
            # Update session
            session.workflow = workflow
            session_manager.update_status(session_id, "processed")
            
            await stream_manager.broadcast_status(
                session_id,
                "processed",
                {
                    "message": "Video processed successfully",
                    "actionCount": len(workflow.actions)
                }
            )
            
            return workflow
            
        except Exception as e:
            session_manager.update_status(session_id, "error")
            await stream_manager.broadcast_status(
                session_id,
                "error",
                {"message": f"Video processing failed: {str(e)}"}
            )
            raise

# Global instance
video_service = VideoService()
