# Task 05: Agent Execution with Screenshot Streaming

**Goal**: Execute the agent pipeline with real-time screenshot streaming to frontend

**Depends On**: Task 04  
**Status**: Not Started  
**Estimated Time**: 4-5 hours

---

## Backend Changes

### 1. Modify PlaywrightToolkit for Custom Screenshot Directory
**File**: `src/playwright_framework.py`

Add screenshot directory parameter and callback:

```python
class PlaywrightToolkit:
    def __init__(
        self, 
        headless: bool = False, 
        browser_type: str = "chromium", 
        use_vision: bool = True,
        screenshot_dir: str = "screenshots"  # NEW
    ):
        self.headless = headless
        self.browser_type = browser_type
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        # Test script being generated
        self.test_script_content: str = ""
        self.script_file_path: Optional[str] = None
        
        # Vision-based element labeling
        self.use_vision = use_vision
        self.vision_labeler = VisionLabeler() if use_vision else None
        self.current_elements: list[ElementInfo] = []
        self.last_screenshot_path: Optional[str] = None
        
        # Screenshot directory and callback (NEW)
        self.screenshot_dir = screenshot_dir
        self.screenshot_callback: Optional[Callable[[str], Awaitable[None]]] = None
        
        # Create screenshots directory
        if self.use_vision:
            os.makedirs(self.screenshot_dir, exist_ok=True)
        
        # Tool registry
        self.tools: dict[str, Tool] = {}
        self._register_tools()
    
    def set_screenshot_callback(self, callback: Callable[[str], Awaitable[None]]):
        """Set callback to be called after each screenshot"""
        self.screenshot_callback = callback
```

Update screenshot path generation in `_capture_labeled_screenshot`:

```python
async def _capture_labeled_screenshot(self) -> dict:
    """Capture screenshot with labeled interactive elements."""
    if not self.page:
        raise RuntimeError("Browser not initialized. Call initialize() first.")
    
    if not self.vision_labeler:
        raise RuntimeError("Vision labeling is not enabled.")
    
    # Ensure screenshots directory exists
    os.makedirs(self.screenshot_dir, exist_ok=True)
    print(f"📸 Capturing labeled screenshot...")
    
    try:
        # Capture and label
        screenshot_path, elements, image_bytes = await self.vision_labeler.capture_and_label_page(
            self.page,
            output_path=None  # Will auto-generate path
        )
        
        # Move screenshot to custom directory if needed
        if self.screenshot_dir != "screenshots":
            from pathlib import Path
            import shutil
            screenshot_filename = Path(screenshot_path).name
            new_path = f"{self.screenshot_dir}/{screenshot_filename}"
            shutil.move(screenshot_path, new_path)
            screenshot_path = new_path
        
        print(f"📸 Screenshot saved to: {screenshot_path}")
        print(f"📸 Found {len(elements)} interactive elements")
        
        # Store current elements
        self.current_elements = elements
        self.last_screenshot_path = screenshot_path
        
        # Call callback if set (NEW)
        if self.screenshot_callback:
            await self.screenshot_callback(screenshot_path)
        
        # ... rest of the method remains the same
```

### 2. Create Agent Service (`backend/services/agent_service.py`)
```python
import sys
from pathlib import Path
import asyncio

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.playwright_framework import PlaywrightToolkit
from src.agent import WorkflowAgent
from src.workflow_schema import WorkflowInput
from backend.models.session import session_manager
from backend.services.stream_service import stream_manager

class AgentExecutionService:
    """Service for running the agent with screenshot streaming"""
    
    async def run_agent(self, session_id: str):
        """
        Execute the agent pipeline with real-time screenshot streaming
        
        Args:
            session_id: Session UUID
        """
        session = session_manager.get_session(session_id)
        if not session or not session.workflow:
            raise ValueError(f"No workflow found for session {session_id}")
        
        # Update status
        session_manager.update_status(session_id, "running")
        await stream_manager.broadcast_status(
            session_id,
            "running",
            {"message": "Starting agent execution..."}
        )
        
        # Setup paths
        session_dir = Path(session.video_path).parent
        screenshot_dir = session_dir / "screenshots"
        output_dir = session_dir / "output"
        output_dir.mkdir(exist_ok=True)
        screenshot_dir.mkdir(exist_ok=True)
        
        script_path = output_dir / "test_generated.py"
        
        toolkit = None
        
        try:
            # Initialize Playwright toolkit with custom screenshot directory
            toolkit = PlaywrightToolkit(
                headless=False,  # Set to True for production
                screenshot_dir=str(screenshot_dir)
            )
            
            # Set screenshot callback for streaming
            async def screenshot_callback(path: str):
                """Called after each screenshot is captured"""
                print(f"🔄 Streaming screenshot: {path}")
                await stream_manager.broadcast_screenshot(session_id, path)
            
            toolkit.set_screenshot_callback(screenshot_callback)
            
            # Initialize browser
            await toolkit.initialize()
            
            # Create agent
            agent = WorkflowAgent(
                toolkit=toolkit,
                debug_mode=True,
                debug_log_file=f"logs/agent_{session_id}.jsonl"
            )
            
            # Send status update
            await stream_manager.broadcast_status(
                session_id,
                "running",
                {"message": "Agent initialized, starting workflow execution..."}
            )
            
            # Run agent
            result = await agent.generate_test_script(
                workflow=session.workflow,
                output_path=str(script_path)
            )
            
            if result.success:
                session.script_path = str(script_path)
                session_manager.update_status(session_id, "complete")
                
                await stream_manager.broadcast_complete(
                    session_id,
                    success=True,
                    script_path=str(script_path)
                )
                
                print(f"✅ Agent completed successfully")
                print(f"   Script: {script_path}")
                print(f"   Actions: {result.actions_count}")
                
            else:
                session_manager.update_status(session_id, "error")
                await stream_manager.broadcast_complete(
                    session_id,
                    success=False,
                    error=result.error
                )
                print(f"❌ Agent failed: {result.error}")
            
        except Exception as e:
            session_manager.update_status(session_id, "error")
            await stream_manager.broadcast_complete(
                session_id,
                success=False,
                error=str(e)
            )
            print(f"❌ Agent execution error: {e}")
            raise
            
        finally:
            if toolkit:
                await toolkit.cleanup()

# Global instance
agent_service = AgentExecutionService()
```

### 3. Add Agent Endpoint to Sessions Router (`backend/routers/sessions.py`)
```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.session import session_manager
from backend.services.video_service import video_service
from backend.services.agent_service import agent_service  # NEW

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
        "scriptPath": session.script_path,
        "createdAt": session.created_at.isoformat()
    }

@router.post("/{session_id}/process")
async def process_video(session_id: str, background_tasks: BackgroundTasks):
    """Process the uploaded video to extract workflow"""
    session = session_manager.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if session.status != "uploaded":
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot process video. Current status: {session.status}"
        )
    
    background_tasks.add_task(video_service.process_video, session_id)
    
    return {
        "sessionId": session_id,
        "status": "processing",
        "message": "Video processing started"
    }

@router.post("/{session_id}/start")  # NEW
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
```

### 4. Add Static File Serving (`backend/routers/static.py`)
```python
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
```

### 5. Update Main App (`backend/main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Import routers
from backend.routers import videos, sessions, websocket, static

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
app.include_router(websocket.router)
app.include_router(static.router)  # NEW

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

### 6. Update Router Init (`backend/routers/__init__.py`)
```python
from . import videos, sessions, websocket, static

__all__ = ["videos", "sessions", "websocket", "static"]
```

---

## Frontend Changes

### 1. Update API Client (`frontend/lib/api.ts`)
```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// ... existing functions ...

export async function startAgent(sessionId: string) {
  const response = await fetch(`${API_URL}/api/sessions/${sessionId}/start`, {
    method: 'POST',
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.detail || 'Failed to start agent');
  }

  return response.json();
}

export const api = {
  healthCheck,
  uploadVideo,
  getSession,
  processVideo,
  startAgent,  // NEW
};
```

### 2. Create Screenshot Stream Component (`frontend/components/ScreenshotStream.tsx`)
```typescript
'use client';

import { useState, useEffect } from 'react';
import Image from 'next/image';

interface Screenshot {
  url: string;
  timestamp: string;
}

interface ScreenshotStreamProps {
  screenshots: Screenshot[];
}

export default function ScreenshotStream({ screenshots }: ScreenshotStreamProps) {
  const [selectedIndex, setSelectedIndex] = useState<number>(-1);

  // Auto-select latest screenshot
  useEffect(() => {
    if (screenshots.length > 0) {
      setSelectedIndex(screenshots.length - 1);
    }
  }, [screenshots.length]);

  if (screenshots.length === 0) {
    return (
      <div className="bg-gray-100 rounded-lg p-12 text-center">
        <div className="text-gray-400 text-lg">
          📸 No screenshots yet
        </div>
        <p className="text-gray-500 text-sm mt-2">
          Screenshots will appear here as the agent executes
        </p>
      </div>
    );
  }

  const selectedScreenshot = screenshots[selectedIndex];

  return (
    <div className="space-y-4">
      {/* Main Screenshot Display */}
      <div className="bg-white rounded-lg shadow-lg overflow-hidden">
        <div className="bg-gray-800 text-white px-4 py-2 text-sm flex items-center justify-between">
          <span>Screenshot {selectedIndex + 1} of {screenshots.length}</span>
          <span className="text-xs text-gray-400">
            {new Date(selectedScreenshot.timestamp).toLocaleTimeString()}
          </span>
        </div>
        <div className="relative w-full" style={{ minHeight: '400px' }}>
          <img
            src={selectedScreenshot.url}
            alt={`Screenshot ${selectedIndex + 1}`}
            className="w-full h-auto"
          />
        </div>
      </div>

      {/* Thumbnail Timeline */}
      <div className="bg-white rounded-lg shadow p-4">
        <h3 className="text-sm font-medium mb-3">Timeline</h3>
        <div className="flex gap-2 overflow-x-auto pb-2">
          {screenshots.map((screenshot, idx) => (
            <button
              key={idx}
              onClick={() => setSelectedIndex(idx)}
              className={`flex-shrink-0 w-32 h-20 rounded border-2 overflow-hidden transition-all ${
                idx === selectedIndex
                  ? 'border-blue-500 ring-2 ring-blue-200'
                  : 'border-gray-200 hover:border-gray-400'
              }`}
            >
              <img
                src={screenshot.url}
                alt={`Thumbnail ${idx + 1}`}
                className="w-full h-full object-cover"
              />
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

### 3. Update Session Page with Agent Execution (`frontend/app/session/[sessionId]/page.tsx`)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { useWebSocket, WebSocketMessage } from '@/lib/useWebSocket';
import ScreenshotStream from '@/components/ScreenshotStream';

interface Session {
  sessionId: string;
  status: string;
  videoPath: string;
  workflowActions: number;
  scriptPath?: string;
  createdAt: string;
}

interface Screenshot {
  url: string;
  timestamp: string;
}

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [screenshots, setScreenshots] = useState<Screenshot[]>([]);
  const [processing, setProcessing] = useState(false);
  const [running, setRunning] = useState(false);

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
        
        if (lastMessage.status === 'processed' || lastMessage.status === 'error') {
          setProcessing(false);
        }
        if (lastMessage.status === 'complete' || lastMessage.status === 'error') {
          setRunning(false);
        }
      }
      
      // Handle screenshot messages
      if (lastMessage.type === 'screenshot' && lastMessage.imageUrl) {
        setScreenshots(prev => [
          ...prev,
          {
            url: lastMessage.imageUrl!,
            timestamp: lastMessage.timestamp || new Date().toISOString()
          }
        ]);
      }
      
      // Handle completion
      if (lastMessage.type === 'complete') {
        if (lastMessage.success && lastMessage.scriptPath) {
          setSession(prev => prev ? { ...prev, scriptPath: lastMessage.scriptPath, status: 'complete' } : null);
        }
        setRunning(false);
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

  const handleStartAgent = async () => {
    try {
      setRunning(true);
      setError(null);
      await api.startAgent(sessionId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start agent');
      setRunning(false);
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
  const canStartAgent = session?.status === 'processed';
  const isComplete = session?.status === 'complete';

  return (
    <main className="min-h-screen p-8 md:p-24 bg-gray-50">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-bold mb-2">Session</h1>
          <p className="text-sm text-gray-500 font-mono">{sessionId}</p>
        </div>
        
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left Column - Session Info & Controls */}
          <div className="lg:col-span-1 space-y-6">
            {/* Connection Status */}
            <div className="bg-white rounded-lg shadow p-4">
              <div className="flex items-center gap-2">
                <div className={`w-3 h-3 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
                <span className="text-sm text-gray-600">
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
            </div>
            
            {/* Session Details */}
            <div className="bg-white shadow rounded-lg p-6">
              <h2 className="text-lg font-semibold mb-4">Details</h2>
              <div className="space-y-3 text-sm">
                <div>
                  <div className="text-gray-500 text-xs mb-1">Status</div>
                  <span className={`px-2 py-1 rounded text-xs font-medium ${
                    session?.status === 'uploaded' ? 'bg-blue-100 text-blue-800' :
                    session?.status === 'processing' || session?.status === 'running' ? 'bg-yellow-100 text-yellow-800' :
                    session?.status === 'processed' ? 'bg-green-100 text-green-800' :
                    session?.status === 'complete' ? 'bg-green-100 text-green-800' :
                    session?.status === 'error' ? 'bg-red-100 text-red-800' :
                    'bg-gray-100 text-gray-800'
                  }`}>
                    {session?.status}
                  </span>
                </div>
                
                {canStartAgent && (
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Actions Detected</div>
                    <div className="font-medium">{session?.workflowActions}</div>
                  </div>
                )}
                
                {screenshots.length > 0 && (
                  <div>
                    <div className="text-gray-500 text-xs mb-1">Screenshots</div>
                    <div className="font-medium">{screenshots.length}</div>
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="space-y-3">
              {canProcess && (
                <button
                  onClick={handleProcessVideo}
                  disabled={processing}
                  className="w-full bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400 text-white px-4 py-3 rounded-lg font-medium transition-colors"
                >
                  {processing ? 'Processing...' : 'Process Video'}
                </button>
              )}

              {canStartAgent && (
                <button
                  onClick={handleStartAgent}
                  disabled={running}
                  className="w-full bg-green-600 hover:bg-green-700 disabled:bg-gray-400 text-white px-4 py-3 rounded-lg font-medium transition-colors"
                >
                  {running ? 'Running Agent...' : 'Start Agent'}
                </button>
              )}

              {isComplete && session.scriptPath && (
                <a
                  href={session.scriptPath}
                  download
                  className="block w-full bg-purple-600 hover:bg-purple-700 text-white px-4 py-3 rounded-lg font-medium transition-colors text-center"
                >
                  Download Test Script
                </a>
              )}
            </div>

            {/* Error Display */}
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <p className="text-red-800 text-sm">{error}</p>
              </div>
            )}

            {/* Activity Log */}
            <div className="bg-white shadow rounded-lg p-4">
              <h2 className="text-lg font-semibold mb-3">Activity</h2>
              <div className="space-y-2 max-h-64 overflow-y-auto text-xs">
                {messages.length === 0 ? (
                  <p className="text-gray-500">No activity yet...</p>
                ) : (
                  messages.slice(-10).map((msg, idx) => (
                    <div key={idx} className="border-l-2 border-gray-300 pl-2 py-1">
                      <div className="font-medium">{msg.type}</div>
                      {msg.log?.message && (
                        <div className="text-gray-500">{msg.log.message}</div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Right Column - Screenshot Stream */}
          <div className="lg:col-span-2">
            <div className="bg-white rounded-lg shadow p-6">
              <h2 className="text-lg font-semibold mb-4">Agent Progress</h2>
              <ScreenshotStream screenshots={screenshots} />
            </div>
          </div>
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

### 3. Complete End-to-End Test
1. Upload a workflow video
2. Click "Process Video" and wait
3. Once processed, click "Start Agent"
4. Watch screenshots stream in real-time!
5. Monitor activity log for progress
6. When complete, download generated script

### 4. Verify Files
```bash
# Check screenshot directory
ls uploads/{session-id}/screenshots/

# Check generated script
cat uploads/{session-id}/output/test_generated.py
```

---

## Success Criteria

- ✅ "Start Agent" button appears after video processing
- ✅ Agent runs in background without blocking
- ✅ Screenshots stream to frontend in real-time
- ✅ Screenshot timeline shows all captured images
- ✅ Can click thumbnails to view specific screenshots
- ✅ Latest screenshot auto-selects and displays
- ✅ Activity log updates with agent actions
- ✅ Test script is generated successfully
- ✅ "Download Test Script" button appears when complete
- ✅ Downloaded script is valid Playwright Python code

---

## Files Created

**Backend:**
- `backend/services/agent_service.py`
- `backend/routers/static.py`

**Frontend:**
- `frontend/components/ScreenshotStream.tsx`

**Modified:**
- `src/playwright_framework.py` (screenshot dir + callback)
- `backend/routers/sessions.py` (added /start endpoint)
- `backend/routers/__init__.py`
- `backend/main.py`
- `frontend/lib/api.ts`
- `frontend/app/session/[sessionId]/page.tsx`

---

## Next Task
**Task 06**: Session Cleanup & Polish (background cleanup, error handling, UI improvements)
