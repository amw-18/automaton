from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from models.session import session_manager
from services.video_service import video_service
from services.agent_service import agent_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

class ProcessVideoRequest(BaseModel):
    starting_url: str
    workflow_name: Optional[str] = None
    workflow_description: Optional[str] = None

@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session information"""
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "sessionId": session.id,
        "status": session.status,
        "videoPath": session.video_path,
        "workflowActions": len(session.workflow.actions) if session.workflow else 0,
        "scriptPath": session.script_path,
        "createdAt": session.created_at.isoformat()
    }

@router.get("/{session_id}/workflow")
async def get_workflow(session_id: str):
    """
    Get the processed workflow JSON for a session
    """
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.workflow:
        raise HTTPException(status_code=404, detail="Workflow not yet processed")
    
    # Return the workflow as JSON
    return session.workflow.model_dump()

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

@router.post("/{session_id}/start")
async def start_agent(session_id: str, background_tasks: BackgroundTasks):
    """Start agent execution to generate test script"""
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.status != "processed":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start agent. Current status: {session.status}. Video must be processed first."
        )
    
    # Run agent in background
    background_tasks.add_task(agent_service.run_agent, session_id)
    
    return {
        "sessionId": session_id,
        "status": "running",
        "message": "Agent execution started"
    }
