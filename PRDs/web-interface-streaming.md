# PRD: Web Interface with Real-Time Agent Streaming

**Date**: 2025-10-25  
**Status**: Design Phase - Awaiting Feedback  
**Author**: AI Assistant

---

## 1. Executive Summary

Add a web interface to Automaton that allows users to:
1. Record screen or upload workflow videos
2. Trigger the agent pipeline on uploaded videos
3. Watch real-time screenshots as the agent executes actions in Playwright
4. No session persistence (ephemeral sessions)

---

## 2. Current Architecture Analysis

### 2.1 Existing Components

**Backend (Python):**
- `src/video_processor.py` - Converts videos to WorkflowInput JSON
- `src/agent.py` - LangGraph agent that executes workflows
- `src/playwright_framework.py` - Browser automation with vision-based labeling
- `src/vision_labeler.py` - Screenshots with element labels
- Screenshots saved to `screenshots/` directory

**Current Flow:**
```
Video → VideoProcessor → WorkflowInput JSON → Agent → Playwright → Test Script
                                                         ↓
                                               Screenshots (local disk)
```

### 2.2 Key Observations

1. **Screenshots are already generated** via `capture_labeled_screenshot()` in `PlaywrightToolkit`
2. Screenshots saved to `screenshots/labeled_{N}.png` (local filesystem)
3. Agent uses LangGraph with async execution
4. No existing API layer - currently CLI-only
5. No real-time communication mechanism

---

## 3. Proposed Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  Upload/     │  │   Agent      │  │  Screenshot        │    │
│  │  Record UI   │→ │   Status     │← │  Stream Display    │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│         ↓                ↑                      ↑                │
└─────────┼────────────────┼──────────────────────┼────────────────┘
          │                │                      │
          │ HTTP POST      │ WebSocket            │ SSE/WebSocket
          │ (video)        │ (status)             │ (images)
          ↓                │                      │
┌─────────────────────────────────────────────────────────────────┐
│                     FASTAPI BACKEND                              │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────┐    │
│  │  Video       │  │   Agent      │  │  Screenshot        │    │
│  │  Upload      │→ │   Runner     │→ │  Stream Manager    │    │
│  │  Handler     │  │              │  │                    │    │
│  └──────────────┘  └──────────────┘  └────────────────────┘    │
│         ↓                ↓                      ↑                │
│  ┌─────────────────────────────────────────────┘                │
│  │          Existing Python Agent Pipeline                      │
│  │  (VideoProcessor → Agent → PlaywrightToolkit)                │
│  └──────────────────────────────────────────────────────────────┘
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Technology Stack

**Frontend:**
- Next.js 14+ (App Router)
- React 18+
- TailwindCSS for styling
- WebSocket client for real-time updates

**Backend:**
- FastAPI (Python 3.11+)
- WebSocket for real-time communication
- Async/await throughout
- No database (ephemeral sessions)

---

## 4. Detailed Design

### 4.1 Frontend (Next.js)

#### 4.1.1 Project Structure
```
frontend/
├── app/
│   ├── layout.tsx              # Root layout
│   ├── page.tsx                # Landing page
│   └── session/
│       └── [sessionId]/
│           └── page.tsx        # Session execution page
├── components/
│   ├── VideoUploader.tsx       # Video upload/record UI
│   ├── AgentProgress.tsx       # Real-time agent status
│   ├── ScreenshotStream.tsx    # Live screenshot display
│   └── StatusIndicator.tsx     # Connection status
├── lib/
│   ├── api.ts                  # API client
│   └── websocket.ts            # WebSocket manager
└── public/
```

#### 4.1.2 Key Components

**1. Landing Page (`app/page.tsx`)**
```typescript
// Two primary actions
<VideoUploader
  onRecord={() => startRecording()}
  onUpload={(file) => uploadVideo(file)}
/>
```

**2. Video Uploader Component**
```typescript
interface VideoUploaderProps {
  onRecord: () => void;
  onUpload: (file: File) => void;
}

// Features:
// - Screen recording via MediaRecorder API
// - Drag & drop file upload
// - Video format validation
// - Upload progress indicator
```

**3. Session Page (`app/session/[sessionId]/page.tsx`)**
```typescript
// Shows:
// - Agent execution status
// - Real-time screenshot stream
// - Agent action log
// - Start button (triggers agent)

const SessionPage = ({ params }: { params: { sessionId: string } }) => {
  const [status, setStatus] = useState<'idle' | 'processing' | 'running' | 'complete'>('idle');
  const [screenshots, setScreenshots] = useState<string[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  
  useEffect(() => {
    // Connect WebSocket for real-time updates
    const ws = connectWebSocket(params.sessionId);
    
    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'screenshot') {
        setScreenshots(prev => [...prev, data.imageUrl]);
      } else if (data.type === 'status') {
        setStatus(data.status);
        setLogs(prev => [...prev, data.log]);
      }
    };
  }, [params.sessionId]);
};
```

**4. Screenshot Stream Component**
```typescript
const ScreenshotStream = ({ screenshots }: { screenshots: string[] }) => {
  // Display latest screenshot large
  // Show thumbnail timeline of previous screenshots
  // Auto-scroll to latest
  // Allow clicking thumbnails to view
};
```

#### 4.1.3 WebSocket Protocol

**Client → Server:**
```json
{
  "type": "start_agent",
  "sessionId": "uuid-here"
}
```

**Server → Client:**
```json
// Screenshot update
{
  "type": "screenshot",
  "sessionId": "uuid-here",
  "imageUrl": "/api/screenshots/uuid-here/labeled_1.png",
  "timestamp": "2025-10-25T21:30:00Z"
}

// Status update
{
  "type": "status",
  "sessionId": "uuid-here",
  "status": "running",
  "log": {
    "action": "navigate_to_url",
    "url": "https://example.com",
    "timestamp": "2025-10-25T21:30:00Z"
  }
}

// Completion
{
  "type": "complete",
  "sessionId": "uuid-here",
  "success": true,
  "scriptPath": "/api/scripts/uuid-here/test.py"
}
```

---

### 4.2 Backend (FastAPI)

#### 4.2.1 Project Structure
```
backend/
├── main.py                    # FastAPI app entry point
├── routers/
│   ├── videos.py             # Video upload/processing
│   ├── sessions.py           # Session management
│   ├── websocket.py          # WebSocket connections
│   └── static.py             # Serve screenshots/scripts
├── services/
│   ├── video_service.py      # Video saving logic
│   ├── agent_service.py      # Agent execution wrapper
│   └── stream_service.py     # Screenshot streaming
├── models/
│   └── session.py            # In-memory session models
└── uploads/                  # Temporary video storage
    └── {session_id}/
        ├── video.mp4
        ├── screenshots/
        │   └── labeled_*.png
        └── output/
            └── test_generated.py
```

#### 4.2.2 API Endpoints

**1. Video Upload**
```python
POST /api/videos/upload
Content-Type: multipart/form-data

Request:
- video: File (required)

Response:
{
  "sessionId": "uuid",
  "status": "uploaded",
  "videoPath": "/uploads/{uuid}/video.mp4"
}
```

**2. Start Agent**
```python
POST /api/sessions/{sessionId}/start

Response:
{
  "sessionId": "uuid",
  "status": "processing"
}
```

**3. WebSocket Connection**
```python
WS /ws/{sessionId}

# Bidirectional communication
# Server pushes screenshots + status updates
# Client can send control messages
```

**4. Static Files**
```python
GET /api/screenshots/{sessionId}/{filename}
# Returns PNG image

GET /api/scripts/{sessionId}/test.py
# Returns generated test script
```

#### 4.2.3 Core Services

**1. Video Service (`services/video_service.py`)**
```python
class VideoService:
    async def save_video(self, file: UploadFile, session_id: str) -> str:
        """
        Save uploaded video to uploads/{session_id}/video.mp4
        Returns: path to saved file
        """
        
    async def process_video(self, session_id: str) -> WorkflowInput:
        """
        Use existing VideoProcessor to convert video to WorkflowInput
        Returns: WorkflowInput JSON
        """
```

**2. Agent Service (`services/agent_service.py`)**
```python
class AgentService:
    def __init__(self, stream_manager: StreamManager):
        self.stream_manager = stream_manager
        
    async def run_agent(self, session_id: str, workflow: WorkflowInput):
        """
        Run the agent pipeline with screenshot streaming
        
        Key Changes:
        1. Inject custom screenshot callback into PlaywrightToolkit
        2. After each capture_labeled_screenshot call, emit to stream_manager
        3. Update session status throughout execution
        """
        
        # Initialize toolkit with custom screenshot dir
        toolkit = PlaywrightToolkit(
            headless=False,  # Initially False for development
            screenshot_dir=f"uploads/{session_id}/screenshots"
        )
        
        # Patch the _capture_labeled_screenshot method
        original_capture = toolkit._capture_labeled_screenshot
        
        async def capture_with_streaming():
            result = await original_capture()
            # Emit screenshot to stream
            await self.stream_manager.emit_screenshot(
                session_id, 
                result["screenshot_path"]
            )
            return result
            
        toolkit._capture_labeled_screenshot = capture_with_streaming
        
        # Run agent
        agent = WorkflowAgent(toolkit=toolkit)
        result = await agent.generate_test_script(
            workflow=workflow,
            output_path=f"uploads/{session_id}/output/test_generated.py"
        )
```

**3. Stream Manager (`services/stream_service.py`)**
```python
class StreamManager:
    def __init__(self):
        self.active_connections: Dict[str, List[WebSocket]] = {}
        
    async def connect(self, session_id: str, websocket: WebSocket):
        """Add websocket connection for session"""
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)
        
    async def disconnect(self, session_id: str, websocket: WebSocket):
        """Remove websocket connection"""
        self.active_connections[session_id].remove(websocket)
        
    async def emit_screenshot(self, session_id: str, screenshot_path: str):
        """Broadcast screenshot to all connected clients"""
        if session_id not in self.active_connections:
            return
            
        message = {
            "type": "screenshot",
            "sessionId": session_id,
            "imageUrl": f"/api/screenshots/{session_id}/{Path(screenshot_path).name}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        for connection in self.active_connections[session_id]:
            await connection.send_json(message)
            
    async def emit_status(self, session_id: str, status: str, log: dict):
        """Broadcast status update"""
        # Similar to emit_screenshot
```

#### 4.2.4 Session Management

**In-Memory Session Store:**
```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class Session:
    id: str
    video_path: Optional[str] = None
    workflow: Optional[WorkflowInput] = None
    status: str = "uploaded"  # uploaded, processing, running, complete, error
    script_path: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    
class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, Session] = {}
        
    def create_session(self) -> str:
        session_id = str(uuid.uuid4())
        self.sessions[session_id] = Session(id=session_id)
        return session_id
        
    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)
        
    def update_status(self, session_id: str, status: str):
        if session := self.sessions.get(session_id):
            session.status = status
```

---

## 5. Implementation Changes to Existing Code

### 5.1 PlaywrightToolkit Modifications

**File**: `src/playwright_framework.py`

**Change 1: Configurable screenshot directory**
```python
class PlaywrightToolkit:
    def __init__(
        self, 
        headless: bool = False, 
        browser_type: str = "chromium", 
        use_vision: bool = True,
        screenshot_dir: str = "screenshots"  # NEW PARAMETER
    ):
        # ...
        self.screenshot_dir = screenshot_dir
        os.makedirs(self.screenshot_dir, exist_ok=True)
```

**Change 2: Update screenshot path generation**
```python
async def _capture_labeled_screenshot(self) -> dict:
    # ...
    if not output_path:
        self.screenshot_counter += 1
        # OLD: output_path = f"screenshots/labeled_{self.screenshot_counter}.png"
        # NEW:
        output_path = f"{self.screenshot_dir}/labeled_{self.screenshot_counter}.png"
```

**Change 3: Add screenshot callback hook**
```python
class PlaywrightToolkit:
    def __init__(self, ...):
        # ...
        self.screenshot_callback: Optional[Callable[[str], Awaitable[None]]] = None
        
    def set_screenshot_callback(self, callback: Callable[[str], Awaitable[None]]):
        """Set callback to be called after each screenshot"""
        self.screenshot_callback = callback
        
    async def _capture_labeled_screenshot(self) -> dict:
        # ... existing code ...
        
        # NEW: Call callback if set
        if self.screenshot_callback:
            await self.screenshot_callback(screenshot_path)
            
        return {
            "screenshot_path": screenshot_path,
            # ...
        }
```

### 5.2 Agent Modifications

**File**: `src/agent.py`

**No changes required** - Agent can be wrapped by AgentService

### 5.3 Directory Structure Changes

**Current:**
```
automaton/
├── screenshots/          # Global screenshots
├── gen_tests/           # Global generated tests
└── workflows/           # Global workflows
```

**New:**
```
automaton/
├── screenshots/          # Development-only
├── gen_tests/           # Development-only
├── workflows/           # Development-only
└── uploads/             # NEW - Per-session data
    └── {session-id}/
        ├── video.mp4
        ├── workflow.json
        ├── screenshots/
        │   └── labeled_*.png
        └── output/
            └── test_generated.py
```

---

## 6. Implementation Phases

### Phase 1: Backend Foundation (Current Scope)
**Deliverables:**
1. ✅ FastAPI app structure
2. ✅ Video upload endpoint (save with UUID)
3. ✅ Session management (in-memory)
4. ✅ WebSocket setup
5. ✅ Agent execution with streaming
6. ✅ Static file serving

**Estimated Effort:** 2-3 days

### Phase 2: Frontend Foundation (Current Scope)
**Deliverables:**
1. ✅ Next.js app setup
2. ✅ Landing page with upload/record UI
3. ✅ Session page with screenshot stream
4. ✅ WebSocket integration
5. ✅ Basic styling (TailwindCSS)

**Estimated Effort:** 2-3 days

### Phase 3: Future Enhancements (Out of Scope)
- User authentication
- Session persistence (database)
- Video trimming/editing
- Multi-browser support toggle
- Headless mode toggle
- Script download/copy
- Session history
- Collaboration features

---

## 7. Technical Considerations

### 7.1 Screenshot Streaming Performance

**Challenge:** High-frequency screenshot generation
**Solution:** 
- Screenshots are triggered by agent actions (not continuous)
- Typically 10-50 screenshots per workflow
- WebSocket can handle this load easily

### 7.2 Session Cleanup

**Challenge:** Orphaned session data filling disk
**Solution:**
- Implement background cleanup task
- Delete sessions older than 1 hour
- Add cleanup endpoint for manual trigger

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def cleanup_old_sessions():
    """Delete sessions older than 1 hour"""
    cutoff = datetime.utcnow() - timedelta(hours=1)
    for session_id, session in list(session_manager.sessions.items()):
        if session.created_at < cutoff:
            # Delete files
            shutil.rmtree(f"uploads/{session_id}", ignore_errors=True)
            # Remove from memory
            del session_manager.sessions[session_id]

# Schedule every 30 minutes
scheduler = AsyncIOScheduler()
scheduler.add_job(cleanup_old_sessions, 'interval', minutes=30)
```

### 7.3 Concurrent Agent Execution

**Challenge:** Multiple users running agents simultaneously
**Solution:**
- Each agent gets its own browser instance (already isolated)
- Sessions are independent (UUID-based)
- Consider queue system if resource constraints exist

### 7.4 WebSocket Connection Management

**Challenge:** Connection drops during long agent runs
**Solution:**
- Implement reconnection logic in frontend
- Store screenshots on disk (can recover missed updates)
- Add endpoint to fetch missed screenshots

### 7.5 Video Processing

**Challenge:** Video processing can take 1-2 minutes for long recordings
**Solution:**
- Show progress indicator during processing
- Process in background task
- Emit status updates via WebSocket

---

## 8. API Contract Summary

### REST Endpoints

```typescript
// Upload video
POST /api/videos/upload
Request: multipart/form-data { video: File }
Response: { sessionId: string, status: string }

// Start agent execution
POST /api/sessions/{sessionId}/start
Response: { sessionId: string, status: string }

// Get session status
GET /api/sessions/{sessionId}
Response: Session object

// Get screenshot
GET /api/screenshots/{sessionId}/{filename}
Response: PNG image

// Get generated script
GET /api/scripts/{sessionId}/test.py
Response: Python file
```

### WebSocket Messages

```typescript
// Client → Server
type ClientMessage = 
  | { type: "start_agent", sessionId: string }
  | { type: "ping" }

// Server → Client
type ServerMessage = 
  | { type: "screenshot", sessionId: string, imageUrl: string, timestamp: string }
  | { type: "status", sessionId: string, status: string, log: LogEntry }
  | { type: "complete", sessionId: string, success: boolean, scriptPath?: string }
  | { type: "error", sessionId: string, error: string }
  | { type: "pong" }
```

---

## 9. File Structure (Complete)

```
automaton/
├── backend/                    # NEW - FastAPI backend
│   ├── main.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── videos.py
│   │   ├── sessions.py
│   │   ├── websocket.py
│   │   └── static.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── video_service.py
│   │   ├── agent_service.py
│   │   └── stream_service.py
│   ├── models/
│   │   ├── __init__.py
│   │   └── session.py
│   └── requirements.txt        # FastAPI dependencies
│
├── frontend/                   # NEW - Next.js frontend
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx
│   │   └── session/
│   │       └── [sessionId]/
│   │           └── page.tsx
│   ├── components/
│   │   ├── VideoUploader.tsx
│   │   ├── ScreenRecorder.tsx
│   │   ├── AgentProgress.tsx
│   │   ├── ScreenshotStream.tsx
│   │   └── StatusIndicator.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   └── websocket.ts
│   ├── package.json
│   └── tsconfig.json
│
├── src/                        # EXISTING - Python agent code
│   ├── agent.py               # Minor modifications
│   ├── playwright_framework.py # Add screenshot callback
│   └── ... (rest unchanged)
│
├── uploads/                    # NEW - Session data
│   └── {session-id}/
│       ├── video.mp4
│       ├── workflow.json
│       ├── screenshots/
│       └── output/
│
├── PRDs/                       # EXISTING
│   ├── init.md
│   └── web-interface-streaming.md  # THIS DOCUMENT
│
└── README.md                   # UPDATE with new instructions
```

---

## 10. Open Questions / Decisions Needed

1. **Video Recording**: Use browser MediaRecorder API or integrate external tool?
   - Recommendation: MediaRecorder API (built-in, no deps)

2. **Screenshot Format**: PNG or WebP for better compression?
   - Recommendation: Keep PNG (already used, compatible)

3. **Headless Mode**: Should agent run in headless mode for production?
   - Recommendation: Add toggle, default to headless=True for backend

4. **Max Video Size**: Limit upload size?
   - Recommendation: 100MB limit (10-minute recording at ~10MB/min)

5. **CORS**: Need CORS configuration for local development?
   - Recommendation: Yes, configure for localhost:3000

6. **Rate Limiting**: Limit concurrent agent executions per client?
   - Recommendation: Defer to Phase 3 (not critical for MVP)

---

## 11. Success Metrics

**Phase 1 & 2 Completion:**
- ✅ User can upload video via web UI
- ✅ Video is saved with UUID
- ✅ User can click "Start" to trigger agent
- ✅ User sees real-time screenshots as agent executes
- ✅ User can download generated test script
- ✅ No crashes during concurrent sessions (basic testing)

---

## 12. Next Steps

**Upon Approval:**
1. Create `backend/` directory structure
2. Create `frontend/` directory structure  
3. Implement video upload endpoint
4. Implement WebSocket streaming
5. Modify PlaywrightToolkit for custom screenshot dir + callbacks
6. Integrate agent execution with streaming
7. Build Next.js UI components
8. End-to-end testing

**Estimated Total Time:** 4-6 days

---

## 13. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| WebSocket connection drops during long runs | Medium | Implement reconnection + screenshot recovery endpoint |
| Multiple users overwhelming server resources | High | Add queue system, limit concurrent executions |
| Video processing timeout | Medium | Show progress, allow up to 5 minutes |
| Screenshot streaming lag | Low | Compress images if needed, current format should be fine |
| Session data filling disk | Medium | Implement cleanup task, monitor disk usage |

---

## Appendix A: Example Workflow (End-to-End)

```
1. User lands on homepage
   → Sees "Upload Video" and "Record Screen" buttons

2. User uploads workflow.mp4 (30 seconds, 3 actions)
   → POST /api/videos/upload
   → Returns sessionId: "abc-123"
   → Redirects to /session/abc-123

3. Session page loads
   → Shows video preview (optional)
   → Shows "Process Video" button
   → WebSocket connects: WS /ws/abc-123

4. User clicks "Process Video"
   → POST /api/sessions/abc-123/process
   → Backend runs VideoProcessor
   → Status updates via WebSocket
   → When complete: "Start Agent" button appears

5. User clicks "Start Agent"
   → POST /api/sessions/abc-123/start
   → Backend runs agent pipeline
   → Screenshots streamed via WebSocket every time capture_labeled_screenshot is called
   → Frontend displays latest screenshot + timeline

6. Agent completes (after ~30-60 seconds)
   → WebSocket sends "complete" message
   → Frontend shows "Download Script" button
   → User downloads test_generated.py

7. Session expires after 1 hour
   → Background task deletes /uploads/abc-123/
```

---

## Appendix B: Development Setup Instructions

```bash
# Backend setup
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# Frontend setup
cd frontend
npm install
npm run dev  # Runs on localhost:3000

# Access
http://localhost:3000  # Frontend
http://localhost:8000/docs  # Backend API docs
```

---

## Appendix C: Environment Variables

```bash
# Backend (.env)
GOOGLE_APPLICATION_CREDENTIALS=/path/to/vertex-ai-credentials.json
GCP_PROJECT_ID=your-project-id
GCP_LOCATION=us-central1
MAX_VIDEO_SIZE_MB=100
SESSION_CLEANUP_HOURS=1

# Frontend (.env.local)
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

**END OF DOCUMENT**

**Status:** Ready for review and feedback
**Next:** Await approval to begin implementation
