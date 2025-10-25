from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from models.session import session_manager
from services.video_service import video_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

class ProcessVideoRequest(BaseModel):
    starting_url: str
    workflow_name: str
    workflow_description: str

@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session information"""
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Debug logging
    print(f"DEBUG: Session {session_id}")
    print(f"  Status: {session.status}")
    print(f"  Workflow: {session.workflow}")
    if session.workflow:
        print(f"  Actions count: {len(session.workflow.actions)}")
    
    return {
        "sessionId": session.id,
        "status": session.status,
        "videoPath": session.video_path,
        "workflowActions": len(session.workflow.actions) if session.workflow else 0,
        "createdAt": session.created_at.isoformat()
    }

@router.post("/{session_id}/process")
async def process_video(
    session_id: str, 
    request: ProcessVideoRequest,
    background_tasks: BackgroundTasks
):
    """
    Process the uploaded video to extract workflow
    
    This runs in the background and updates status via WebSocket
    """
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.status != "uploaded":
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot process video. Current status: {session.status}"
        )
    
    # Process in background with user-provided metadata
    background_tasks.add_task(
        video_service.process_video, 
        session_id,
        request.starting_url,
        request.workflow_name,
        request.workflow_description
    )
    
    return {
        "sessionId": session_id,
        "status": "processing",
        "message": "Video processing started"
    }
