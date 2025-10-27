from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from models.session import session_manager
from services.video_service import video_service
from services.agent_service import agent_service
from services.cleanup_service import cleanup_service
from services.test_execution_service import test_execution_service

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

class ProcessVideoRequest(BaseModel):
    starting_url: str
    workflow_name: Optional[str] = None
    workflow_description: Optional[str] = None

@router.get("")
async def get_all_sessions():
    """Get all sessions (for sidebar)"""
    sessions = session_manager.get_all_sessions()
    return {
        "sessions": [
            {
                "id": s.id,
                "status": s.status,
                "workflowActions": len(s.workflow.actions) if s.workflow else 0,
                "createdAt": s.created_at.isoformat(),
            }
            for s in sessions
        ]
    }

@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get session details"""
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "sessionId": session.id,
        "status": session.status,
        "videoPath": session.video_path,
        "workflowActions": len(session.workflow.actions) if session.workflow else 0,
        "scriptPath": session.script_path,
        "testVideoPath": session.test_video_path,
        "createdAt": session.created_at.isoformat()
    }

@router.get("/{session_id}/events")
async def get_session_events(session_id: str):
    """Get session event history"""
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "sessionId": session.id,
        "events": [e.model_dump() for e in session.events]
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
    
    This runs in the background and updates status via WebSocket.
    Can be retried if video is uploaded or if previous attempt failed.
    """
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Allow processing from uploaded or error states (for retry)
    if session.status not in ["uploaded", "error"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot process video. Current status: {session.status}. Video must be uploaded first."
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
    """
    Start agent execution to generate test script
    
    Can be retried if workflow is processed or if previous attempt failed.
    """
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Allow starting from processed, complete (retry), or error states
    if session.status not in ["processed", "complete", "error"]:
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

@router.post("/{session_id}/test")
async def test_script(session_id: str, background_tasks: BackgroundTasks):
    """
    Execute the generated test script in Docker with video recording
    
    This endpoint runs the generated Playwright script in a minimal Docker container
    and returns a video recording of the test execution.
    Can be retried if previous test failed.
    """
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Allow testing from complete, test_complete (rerun), test_failed (retry), or error states
    if not session.script_path:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot test script. No script has been generated yet."
        )
    
    if session.status not in ["complete", "test_complete", "test_failed", "error"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot test script. Current status: {session.status}. Script must be generated first."
        )
    
    # Run test in background
    background_tasks.add_task(test_execution_service.run_test, session_id)
    
    return {
        "sessionId": session_id,
        "status": "testing",
        "message": "Test execution started"
    }

@router.post("/cleanup")
async def manual_cleanup():
    """Manually trigger session cleanup"""
    deleted_count = await cleanup_service.cleanup_old_sessions()
    return {
        "message": f"Cleanup complete. Deleted {deleted_count} session(s)",
        "deletedCount": deleted_count
    }

@router.get("/stats")
async def get_stats():
    """Get system statistics"""
    total_sessions = len(session_manager.sessions)
    uploads_dir = Path("uploads")
    
    # Calculate total disk usage
    total_size = 0
    if uploads_dir.exists():
        for session_dir in uploads_dir.iterdir():
            if session_dir.is_dir():
                for file in session_dir.rglob('*'):
                    if file.is_file():
                        total_size += file.stat().st_size
    
    # Count by status
    status_counts = {}
    for session in session_manager.sessions.values():
        status_counts[session.status] = status_counts.get(session.status, 0) + 1
    
    return {
        "totalSessions": total_sessions,
        "diskUsageMB": round(total_size / (1024 * 1024), 2),
        "statusCounts": status_counts
    }
