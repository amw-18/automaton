# Task 04: Video Processing Integration

**Goal**: Integrate existing VideoProcessor to convert uploaded videos into WorkflowInput JSON

**Depends On**: Task 03  
**Status**: Not Started  
**Estimated Time**: 2-3 hours

---

## Backend Changes

### 1. Create Video Service (`backend/services/video_service.py`)
```python
import sys
from pathlib import Path

# Add parent directory to path to import from src/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.video_processor import VideoProcessor
from src.workflow_schema import WorkflowInput
from backend.models.session import session_manager
from backend.services.stream_service import stream_manager
import json

class VideoService:
    """Service for processing uploaded videos"""
    
    def __init__(self):
        self.video_processor = VideoProcessor()
    
    async def process_video(self, session_id: str) -> WorkflowInput:
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
            workflow = await self.video_processor.process_video(session.video_path)
            
            # Save workflow JSON to session directory
            session_dir = Path(session.video_path).parent
            workflow_path = session_dir / "workflow.json"
            
            with open(workflow_path, 'w') as f:
                json.dump(workflow.model_dump(), f, indent=2)
            
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
```

### 2. Update Session Model (`backend/models/session.py`)
```python
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid
import sys
from pathlib import Path

# Add parent directory to import from src/
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.workflow_schema import WorkflowInput

@dataclass
class Session:
    id: str
    video_path: Optional[str] = None
    workflow: Optional[WorkflowInput] = None  # NEW
    status: str = "created"  # created, uploaded, processing, processed, running, complete, error
    created_at: datetime = None
    script_path: Optional[str] = None  # NEW
    
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

### 3. Add Process Endpoint to Sessions Router (`backend/routers/sessions.py`)
```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.session import session_manager
from backend.services.video_service import video_service

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
        "workflowActions": len(session.workflow.actions) if session.workflow else 0,
        "createdAt": session.created_at.isoformat()
    }

@router.post("/{session_id}/process")
async def process_video(session_id: str, background_tasks: BackgroundTasks):
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
    
    # Process in background
    background_tasks.add_task(video_service.process_video, session_id)
    
    return {
        "sessionId": session_id,
        "status": "processing",
        "message": "Video processing started"
    }
```

---

## Frontend Changes

### 1. Update API Client (`frontend/lib/api.ts`)
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export async function healthCheck() {
  const response = await fetch(`${API_URL}/api/health`);
  if (!response.ok) {
    throw new Error('API health check failed');
  }
  return response.json();
}

export async function uploadVideo(file: File): Promise<{ sessionId: string; status: string }> {
  const formData = new FormData();
  formData.append('video', file);

  const response = await fetch(`${API_URL}/api/videos/upload`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Upload failed');
  }

  return response.json();
}

export async function getSession(sessionId: string) {
  const response = await fetch(`${API_URL}/api/sessions/${sessionId}`);
  if (!response.ok) {
    throw new Error('Failed to get session');
  }
  return response.json();
}

export async function processVideo(sessionId: string) {
  const response = await fetch(`${API_URL}/api/sessions/${sessionId}/process`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Processing failed');
  }

  return response.json();
}

export const api = {
  healthCheck,
  uploadVideo,
  getSession,
  processVideo,
};
```

### 2. Update Session Page (`frontend/app/session/[sessionId]/page.tsx`)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { useWebSocket, WebSocketMessage } from '@/lib/useWebSocket';

interface Session {
  sessionId: string;
  status: string;
  videoPath: string;
  workflowActions: number;
  createdAt: string;
}

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [processing, setProcessing] = useState(false);

  // WebSocket connection
  const { isConnected, lastMessage } = useWebSocket(sessionId);

  // Load initial session data
  useEffect(() => {
    loadSession();
  }, [sessionId]);

  const loadSession = async () => {
    try {
      const data = await api.getSession(sessionId);
      setSession(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load session');
    } finally {
      setLoading(false);
    }
  };

  // Handle WebSocket messages
  useEffect(() => {
    if (lastMessage) {
      setMessages(prev => [...prev, lastMessage]);
      
      // Update session status
      if (lastMessage.type === 'status' && lastMessage.status) {
        setSession(prev => prev ? { ...prev, status: lastMessage.status } : null);
        
        // Stop processing indicator when done
        if (lastMessage.status === 'processed' || lastMessage.status === 'error') {
          setProcessing(false);
        }
      }
    }
  }, [lastMessage]);

  const handleProcessVideo = async () => {
    try {
      setProcessing(true);
      setError(null);
      await api.processVideo(sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Processing failed');
      setProcessing(false);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-xl">Loading session...</div>
      </div>
    );
  }

  if (error && !session) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="text-red-500">Error: {error}</div>
      </div>
    );
  }

  const canProcess = session?.status === 'uploaded';
  const isProcessed = session?.status === 'processed';

  return (
    <main className="min-h-screen p-8 md:p-24">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-bold mb-2">Session</h1>
        <p className="text-sm text-gray-500 mb-8 font-mono">{sessionId}</p>
        
        {/* Connection Status */}
        <div className="mb-6 flex items-center gap-2">
          <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
          <span className="text-sm text-gray-600">
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
        </div>
        
        {/* Session Details */}
        <div className="bg-white shadow rounded-lg p-6 mb-6">
          <h2 className="text-xl font-semibold mb-4">Session Details</h2>
          <div className="space-y-2 text-sm">
            <div className="flex">
              <span className="font-medium w-32">Status:</span>
              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                session?.status === 'uploaded' ? 'bg-blue-100 text-blue-800' :
                session?.status === 'processing' ? 'bg-yellow-100 text-yellow-800' :
                session?.status === 'processed' ? 'bg-green-100 text-green-800' :
                session?.status === 'error' ? 'bg-red-100 text-red-800' :
                'bg-gray-100 text-gray-800'
              }`}>
                {session?.status}
              </span>
            </div>
            <div className="flex">
              <span className="font-medium w-32">Created:</span>
              <span className="text-gray-600">
                {session?.createdAt ? new Date(session.createdAt).toLocaleString() : 'N/A'}
              </span>
            </div>
            <div className="flex">
              <span className="font-medium w-32">Video:</span>
              <span className="text-gray-600">{session?.videoPath ? '✅ Uploaded' : '❌ Missing'}</span>
            </div>
            {isProcessed && (
              <div className="flex">
                <span className="font-medium w-32">Actions:</span>
                <span className="text-gray-600">{session?.workflowActions} detected</span>
              </div>
            )}
          </div>
        </div>

        {/* Action Buttons */}
        {canProcess && (
          <div className="mb-6">
            <button
              onClick={handleProcessVideo}
              disabled={processing}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              {processing ? 'Processing Video...' : 'Process Video'}
            </button>
            <p className="text-sm text-gray-500 mt-2">
              Click to analyze the video and extract workflow actions
            </p>
          </div>
        )}

        {isProcessed && (
          <div className="bg-green-50 border border-green-200 rounded-lg p-6 mb-6">
            <h3 className="font-semibold text-green-800 mb-2">✅ Video Processed</h3>
            <p className="text-green-700 text-sm">
              Detected {session?.workflowActions} actions. Ready to generate test script.
            </p>
            <p className="text-xs text-green-600 mt-2">
              (Test script generation will be implemented in the next task)
            </p>
          </div>
        )}

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6">
            <p className="text-red-800 text-sm">{error}</p>
          </div>
        )}

        {/* WebSocket Messages Log */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Activity Log</h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {messages.length === 0 ? (
              <p className="text-gray-500 text-sm">No activity yet...</p>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className="text-sm border-l-2 border-blue-500 pl-3 py-1">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium">{msg.type}</span>
                      {msg.status && <span className="text-gray-600"> - {msg.status}</span>}
                      {msg.log?.message && (
                        <div className="text-gray-500 text-xs mt-1">{msg.log.message}</div>
                      )}
                    </div>
                    {msg.timestamp && (
                      <span className="text-xs text-gray-400">
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
```

---

## Testing

### 1. Ensure Google Cloud Credentials
```bash
# Make sure vertex-ai-credentials.json is in the project root
ls ../vertex-ai-credentials.json
```

### 2. Start Backend
```bash
cd backend
source venv/bin/activate
python main.py
```

### 3. Start Frontend
```bash
cd frontend
npm run dev
```

### 4. Test Video Processing
1. Upload a video at http://localhost:3000
2. Click "Process Video" button on session page
3. Watch real-time status updates via WebSocket
4. Should see "processing" → "processed" status
5. Activity log should show progress messages
6. Verify `uploads/{uuid}/workflow.json` file created

### 5. Check Workflow JSON
```bash
cat uploads/{session-id}/workflow.json
# Should contain actions array with detected user interactions
```

---

## Success Criteria

- ✅ "Process Video" button appears when video is uploaded
- ✅ Processing runs in background (no page freeze)
- ✅ Status updates stream via WebSocket ("processing" → "processed")
- ✅ Activity log shows processing messages
- ✅ Workflow JSON file created in session directory
- ✅ Session displays action count after processing
- ✅ Error handling works (shows error in UI if processing fails)

---

## Files Created

**Backend:**
- `backend/services/video_service.py`

**Modified:**
- `backend/models/session.py` (added workflow field)
- `backend/routers/sessions.py` (added /process endpoint)
- `frontend/lib/api.ts` (added processVideo function)
- `frontend/app/session/[sessionId]/page.tsx` (added process button & state)

---

## Next Task
**Task 05**: Agent Execution with Screenshot Streaming
