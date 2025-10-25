import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from models.session import session_manager

router = APIRouter(prefix="/api/videos", tags=["videos"])

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

MAX_VIDEO_SIZE = 100 * 1024 * 1024  # 100MB

@router.post("/upload")
async def upload_video(video: UploadFile = File(...)):
    """Upload a workflow video and create a session"""
    
    # Validate file type
    if not video.content_type.startswith('video/'):
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type: {video.content_type}. Must be a video file."
        )
    
    # Create session
    session = session_manager.create_session()
    session_dir = UPLOAD_DIR / session.id
    session_dir.mkdir(parents=True, exist_ok=True)
    
    # Save video with original extension
    original_filename = video.filename or "video.mp4"
    extension = Path(original_filename).suffix or ".mp4"
    video_path = session_dir / f"video{extension}"
    
    try:
        with open(video_path, "wb") as f:
            # Read in chunks to handle large files
            while chunk := await video.read(1024 * 1024):  # 1MB chunks
                f.write(chunk)
        
        # Update session
        session.video_path = str(video_path)
        session.status = "uploaded"
        
        return JSONResponse(content={
            "sessionId": session.id,
            "status": session.status,
            "videoPath": str(video_path),
            "message": "Video uploaded successfully"
        })
    
    except Exception as e:
        # Cleanup on error
        shutil.rmtree(session_dir, ignore_errors=True)
        session_manager.sessions.pop(session.id, None)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
