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
