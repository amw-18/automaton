# Task 02: Video Upload Flow

**Goal**: Implement video upload with file storage and session creation

**Depends On**: Task 01  
**Status**: Not Started  
**Estimated Time**: 3-4 hours

---

## Backend Changes

### 1. Create Session Model (`backend/models/session.py`)
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid

@dataclass
class Session:
    id: str
    video_path: Optional[str] = None
    status: str = "created"  # created, uploaded, processing, running, complete, error
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()

class SessionManager:
    def __init__(self):
        self.sessions: dict[str, Session] = {}
    
    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(id=session_id)
        self.sessions[session_id] = session
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)
    
    def update_status(self, session_id: str, status: str):
        if session := self.sessions.get(session_id):
            session.status = status

# Global instance
session_manager = SessionManager()
```

### 2. Create Video Upload Router (`backend/routers/videos.py`)
```python
import shutil
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

from backend.models.session import session_manager

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
    
    # Save video
    video_path = session_dir / "video.mp4"
    
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
```

### 3. Create Sessions Router (`backend/routers/sessions.py`)
```python
from fastapi import APIRouter, HTTPException
from backend.models.session import session_manager

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

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
        "createdAt": session.created_at.isoformat()
    }
```

### 4. Update Main App (`backend/main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Import routers
from backend.routers import videos, sessions

load_dotenv()

app = FastAPI(title="Automaton API", version="1.0.0")

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(videos.router)
app.include_router(sessions.router)

@app.get("/")
async def root():
    return {"message": "Automaton API", "status": "running"}

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 5. Create Router Init File (`backend/routers/__init__.py`)
```python
from . import videos, sessions

__all__ = ["videos", "sessions"]
```

---

## Frontend Changes

### 1. Regenerate API Client
After adding backend endpoints, regenerate the TypeScript client:

```bash
cd frontend
npm run generate-client
```

This will automatically create:
- `uploadVideo()` function from `/api/videos/upload` endpoint
- `getSession()` function from `/api/sessions/{sessionId}` endpoint
- Proper TypeScript types for request/response

### 2. Create Video Uploader Component (`frontend/components/VideoUploader.tsx`)
```typescript
'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { uploadVideo } from '@/lib/api-client';

export default function VideoUploader() {
  const router = useRouter();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  const handleFile = async (file: File) => {
    if (!file.type.startsWith('video/')) {
      setError('Please upload a video file');
      return;
    }

    if (file.size > 100 * 1024 * 1024) {
      setError('File size must be less than 100MB');
      return;
    }

    setUploading(true);
    setError(null);

    try {
      // uploadVideo is auto-generated from OpenAPI spec
      const result = await uploadVideo({
        body: { video: file },
        bodySerializer: (body) => {
          const formData = new FormData();
          formData.append('video', body.video);
          return formData;
        },
      });
      
      // Redirect to session page
      if (result.data) {
        router.push(`/session/${result.data.sessionId}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    
    const file = e.dataTransfer.files[0];
    if (file) {
      handleFile(file);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFile(file);
    }
  };

  return (
    <div className="w-full max-w-md">
      <div
        className={`border-2 border-dashed rounded-lg p-12 text-center transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
        } ${uploading ? 'opacity-50 pointer-events-none' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
        onDragLeave={() => setDragActive(false)}
        onDrop={handleDrop}
      >
        <input
          type="file"
          accept="video/*"
          onChange={handleChange}
          className="hidden"
          id="video-upload"
          disabled={uploading}
        />
        
        <label htmlFor="video-upload" className="cursor-pointer">
          <div className="text-6xl mb-4">📹</div>
          <p className="text-lg font-medium mb-2">
            {uploading ? 'Uploading...' : 'Upload Workflow Video'}
          </p>
          <p className="text-sm text-gray-500">
            Drag & drop or click to select
          </p>
          <p className="text-xs text-gray-400 mt-2">
            Max 100MB • MP4, MOV, WebM
          </p>
        </label>
      </div>

      {error && (
        <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
```

### 3. Update Landing Page (`frontend/app/page.tsx`)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { client } from '@/lib/api-client';
import VideoUploader from '@/components/VideoUploader';

export default function Home() {
  const [apiStatus, setApiStatus] = useState<string>('checking...');

  useEffect(() => {
    // Configure client
    client.setConfig({
      baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    });
    
    // Test connection
    fetch(`${client.getConfig().baseUrl}/api/health`)
      .then(() => setApiStatus('connected ✅'))
      .catch(() => setApiStatus('disconnected ❌'));
  }, []);

  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold mb-4">Automaton</h1>
        <p className="text-xl text-gray-600 mb-2">
          AI-Powered Test Automation
        </p>
        <div className="text-xs text-gray-400">
          API Status: {apiStatus}
        </div>
      </div>

      <VideoUploader />

      <div className="mt-12 text-center text-sm text-gray-500">
        <p>Upload a video of your workflow</p>
        <p>We'll generate a Playwright test script for you</p>
      </div>
    </main>
  );
}
```

### 4. Create Basic Session Page (`frontend/app/session/[sessionId]/page.tsx`)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { getSession } from '@/lib/api-client';

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSession({ path: { session_id: sessionId } })
      .then(result => {
        if (result.data) setSession(result.data);
      })
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-xl">Loading session...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-red-500">Error: {error}</div>
      </div>
    );
  }

  return (
    <main className="min-h-screen p-24">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-8">Session: {sessionId}</h1>
        
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Session Details</h2>
          <div className="space-y-2 text-sm">
            <div className="flex">
              <span className="font-medium w-32">Status:</span>
              <span className="text-gray-600">{session?.status}</span>
            </div>
            <div className="flex">
              <span className="font-medium w-32">Created:</span>
              <span className="text-gray-600">
                {new Date(session?.createdAt).toLocaleString()}
              </span>
            </div>
            <div className="flex">
              <span className="font-medium w-32">Video:</span>
              <span className="text-gray-600">{session?.videoPath ? '✅ Uploaded' : '❌ Missing'}</span>
            </div>
          </div>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-6">
          <p className="text-blue-800">
            Video uploaded successfully! Next steps will be implemented in upcoming tasks.
          </p>
        </div>
      </div>
    </main>
  );
}
```

---

## Testing

### 1. Start Backend
```bash
cd backend
source venv/bin/activate
python main.py
```

### 2. Start Frontend
```bash
cd frontend
npm run dev
```

### 3. Test Upload Flow
1. Visit http://localhost:3000
2. Drag & drop a video file or click to select
3. Should redirect to `/session/{uuid}` after upload
4. Session page should show "uploaded" status

### 4. Verify Backend
- Check `uploads/{uuid}/video.mp4` exists
- Visit http://localhost:8000/docs and test endpoints

---

## Success Criteria

- ✅ User can upload video via drag & drop
- ✅ User can upload video via file input
- ✅ File validation works (type & size)
- ✅ Session is created with UUID
- ✅ Video is saved to `uploads/{uuid}/video.mp4`
- ✅ User is redirected to session page
- ✅ Session page displays session details

---

## Files Created/Modified

**Created:**
- `backend/models/session.py`
- `backend/routers/__init__.py`
- `backend/routers/videos.py`
- `backend/routers/sessions.py`
- `frontend/components/VideoUploader.tsx`
- `frontend/app/session/[sessionId]/page.tsx`

**Modified:**
- `backend/main.py`
- `frontend/app/page.tsx`

**Auto-Generated (via `npm run generate-client`):**
- `frontend/lib/api-client/types.gen.ts` - Contains `Session`, response types
- `frontend/lib/api-client/services.gen.ts` - Contains `uploadVideo()`, `getSession()` functions

**Note:** Always run `npm run generate-client` after adding/modifying backend endpoints!

---

## Next Task
**Task 03**: WebSocket Infrastructure (connection manager + basic messaging)
