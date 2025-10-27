from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

router = APIRouter(prefix="/api", tags=["static"])

UPLOADS_DIR = Path("uploads")

@router.get("/screenshots/{session_id}/{filename}")
async def get_screenshot(session_id: str, filename: str):
    """Serve screenshot files"""
    file_path = UPLOADS_DIR / session_id / "screenshots" / filename
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Screenshot not found")
    
    return FileResponse(file_path, media_type="image/png")

@router.get("/scripts/{session_id}/test.py")
async def get_script(session_id: str):
    """Serve generated test script"""
    file_path = UPLOADS_DIR / session_id / "output" / "test_generated.py"
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Script not found")
    
    return FileResponse(
        file_path,
        media_type="text/plain",
        filename=f"test_{session_id}.py"
    )

@router.get("/test-videos/{session_id}/execution.webm")
async def get_test_video(session_id: str):
    """Serve test execution video"""
    test_output_dir = UPLOADS_DIR / session_id / "test_output"
    
    # Try standard location first
    file_path = test_output_dir / "test_execution.webm"
    
    # If not found, search for any video file in test_output directory
    if not file_path.exists():
        video_files = list(test_output_dir.glob("*.webm")) + list(test_output_dir.glob("*.mp4"))
        
        # Also check videos subdirectory (Docker creates it there)
        video_subdir = test_output_dir / "videos"
        if video_subdir.exists():
            video_files.extend(list(video_subdir.glob("*.webm")) + list(video_subdir.glob("*.mp4")))
        
        if video_files:
            file_path = video_files[0]  # Use first found video
        else:
            raise HTTPException(status_code=404, detail="Test video not found")
    
    return FileResponse(
        file_path,
        media_type="video/webm" if file_path.suffix == ".webm" else "video/mp4",
        filename=f"test_execution_{session_id}{file_path.suffix}"
    )
