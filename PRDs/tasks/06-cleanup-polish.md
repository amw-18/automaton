# Task 06: Session Cleanup & Polish

**Goal**: Add automated session cleanup, improve error handling, and polish the UI

**Depends On**: Task 05  
**Status**: Not Started  
**Estimated Time**: 2-3 hours

---

## Backend Changes

### 1. Session Cleanup Service (`backend/services/cleanup_service.py`)
```python
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from backend.models.session import session_manager
import asyncio

class CleanupService:
    """Automated cleanup of old sessions"""
    
    def __init__(self, max_age_hours: int = 1):
        self.max_age_hours = max_age_hours
        self.uploads_dir = Path("uploads")
    
    async def cleanup_old_sessions(self):
        """Delete sessions older than max_age_hours"""
        cutoff_time = datetime.utcnow() - timedelta(hours=self.max_age_hours)
        deleted_count = 0
        
        print(f"🧹 Running session cleanup (cutoff: {cutoff_time.isoformat()})")
        
        # Cleanup from memory
        sessions_to_delete = []
        for session_id, session in session_manager.sessions.items():
            if session.created_at < cutoff_time:
                sessions_to_delete.append(session_id)
        
        for session_id in sessions_to_delete:
            # Delete files
            session_dir = self.uploads_dir / session_id
            if session_dir.exists():
                try:
                    shutil.rmtree(session_dir)
                    print(f"  ✓ Deleted session files: {session_id}")
                except Exception as e:
                    print(f"  ✗ Error deleting {session_id}: {e}")
            
            # Remove from memory
            session_manager.sessions.pop(session_id, None)
            deleted_count += 1
        
        print(f"🧹 Cleanup complete. Deleted {deleted_count} session(s)")
        return deleted_count
    
    async def start_periodic_cleanup(self, interval_minutes: int = 30):
        """Run cleanup periodically"""
        print(f"🧹 Starting periodic cleanup (every {interval_minutes} minutes)")
        
        while True:
            await asyncio.sleep(interval_minutes * 60)
            await self.cleanup_old_sessions()

# Global instance
cleanup_service = CleanupService(max_age_hours=1)
```

### 2. Update Main App with Cleanup Task (`backend/main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import asyncio

# Import routers
from backend.routers import videos, sessions, websocket, static
from backend.services.cleanup_service import cleanup_service

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
app.include_router(static.router)

@app.get("/")
async def root():
    return {"message": "Automaton API", "status": "running"}

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

@app.on_event("startup")
async def startup_event():
    """Start background tasks on startup"""
    # Start periodic cleanup (every 30 minutes)
    asyncio.create_task(cleanup_service.start_periodic_cleanup(interval_minutes=30))
    print("✅ Background tasks started")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 3. Add Manual Cleanup Endpoint (`backend/routers/sessions.py`)
```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from backend.models.session import session_manager
from backend.services.video_service import video_service
from backend.services.agent_service import agent_service
from backend.services.cleanup_service import cleanup_service  # NEW

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# ... existing endpoints ...

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
    from pathlib import Path
    
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
```

### 4. Enhanced Error Handling (`backend/services/agent_service.py`)
Add better error handling and logging:

```python
# In run_agent method, add more detailed error catching
try:
    # ... existing code ...
    
except FileNotFoundError as e:
    error_msg = f"File not found: {str(e)}"
    print(f"❌ {error_msg}")
    session_manager.update_status(session_id, "error")
    await stream_manager.broadcast_complete(session_id, success=False, error=error_msg)
    
except PermissionError as e:
    error_msg = f"Permission denied: {str(e)}"
    print(f"❌ {error_msg}")
    session_manager.update_status(session_id, "error")
    await stream_manager.broadcast_complete(session_id, success=False, error=error_msg)
    
except asyncio.TimeoutError:
    error_msg = "Agent execution timed out"
    print(f"❌ {error_msg}")
    session_manager.update_status(session_id, "error")
    await stream_manager.broadcast_complete(session_id, success=False, error=error_msg)
    
except Exception as e:
    error_msg = f"Unexpected error: {str(e)}"
    print(f"❌ {error_msg}")
    import traceback
    traceback.print_exc()
    session_manager.update_status(session_id, "error")
    await stream_manager.broadcast_complete(session_id, success=False, error=error_msg)
    raise
```

---

## Frontend Changes

### 1. Add Loading States Component (`frontend/components/LoadingSpinner.tsx`)
```typescript
export default function LoadingSpinner({ size = 'md' }: { size?: 'sm' | 'md' | 'lg' }) {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12'
  };

  return (
    <div className="flex items-center justify-center">
      <div className={`${sizeClasses[size]} border-4 border-gray-200 border-t-blue-600 rounded-full animate-spin`} />
    </div>
  );
}
```

### 2. Add Error Boundary (`frontend/components/ErrorBoundary.tsx`)
```typescript
'use client';

import { Component, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export default class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback || (
          <div className="min-h-screen flex items-center justify-center p-4">
            <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
              <h2 className="text-red-800 font-bold text-lg mb-2">
                Something went wrong
              </h2>
              <p className="text-red-700 text-sm mb-4">
                {this.state.error?.message || 'An unexpected error occurred'}
              </p>
              <button
                onClick={() => window.location.reload()}
                className="bg-red-600 hover:bg-red-700 text-white px-4 py-2 rounded text-sm"
              >
                Reload Page
              </button>
            </div>
          </div>
        )
      );
    }

    return this.props.children;
  }
}
```

### 3. Add Status Badge Component (`frontend/components/StatusBadge.tsx`)
```typescript
interface StatusBadgeProps {
  status: string;
}

export default function StatusBadge({ status }: StatusBadgeProps) {
  const statusConfig: Record<string, { label: string; className: string }> = {
    created: { label: 'Created', className: 'bg-gray-100 text-gray-800' },
    uploaded: { label: 'Uploaded', className: 'bg-blue-100 text-blue-800' },
    processing: { label: 'Processing', className: 'bg-yellow-100 text-yellow-800' },
    processed: { label: 'Ready', className: 'bg-green-100 text-green-800' },
    running: { label: 'Running', className: 'bg-purple-100 text-purple-800' },
    complete: { label: 'Complete', className: 'bg-green-100 text-green-800' },
    error: { label: 'Error', className: 'bg-red-100 text-red-800' },
  };

  const config = statusConfig[status] || statusConfig.created;

  return (
    <span className={`px-2 py-1 rounded text-xs font-medium ${config.className}`}>
      {config.label}
    </span>
  );
}
```

### 4. Polish Session Page UI (`frontend/app/session/[sessionId]/page.tsx`)
Add imports:
```typescript
import ErrorBoundary from '@/components/ErrorBoundary';
import LoadingSpinner from '@/components/LoadingSpinner';
import StatusBadge from '@/components/StatusBadge';
```

Update loading state:
```typescript
if (loading) {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="text-center">
        <LoadingSpinner size="lg" />
        <p className="mt-4 text-gray-600">Loading session...</p>
      </div>
    </div>
  );
}
```

Update status display to use StatusBadge:
```typescript
<div>
  <div className="text-gray-500 text-xs mb-1">Status</div>
  <StatusBadge status={session?.status || 'created'} />
</div>
```

Add progress indicator when agent is running:
```typescript
{running && (
  <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
    <div className="flex items-center gap-3">
      <LoadingSpinner size="sm" />
      <div>
        <div className="font-medium text-blue-800">Agent Running</div>
        <div className="text-sm text-blue-600">
          Generating test script... {screenshots.length} screenshots captured
        </div>
      </div>
    </div>
  </div>
)}
```

### 5. Wrap Root Layout with Error Boundary (`frontend/app/layout.tsx`)
```typescript
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import ErrorBoundary from '@/components/ErrorBoundary';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'Automaton - AI Test Automation',
  description: 'Generate Playwright test scripts from workflow videos',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <ErrorBoundary>
          {children}
        </ErrorBoundary>
      </body>
    </html>
  );
}
```

### 6. Add Home Link to Session Page
```typescript
// Add at top of session page
<div className="mb-8">
  <a href="/" className="text-blue-600 hover:text-blue-700 text-sm flex items-center gap-1">
    ← Back to Home
  </a>
  <h1 className="text-3xl font-bold mt-2">Session</h1>
  <p className="text-sm text-gray-500 font-mono">{sessionId}</p>
</div>
```

---

## Testing

### 1. Test Cleanup Service
```bash
# Start backend
cd backend
python main.py

# Wait 30 minutes or trigger manually:
curl -X POST http://localhost:8000/api/sessions/cleanup
```

### 2. Test Stats Endpoint
```bash
curl http://localhost:8000/api/sessions/stats
```

### 3. Test Error Handling
- Try uploading invalid file
- Try starting agent without processing
- Check error messages display properly

### 4. Test UI Polish
- Check loading spinners appear
- Verify status badges show correct colors
- Test "Back to Home" link
- Verify error boundary catches errors

---

## Success Criteria

- ✅ Old sessions automatically deleted after 1 hour
- ✅ Manual cleanup endpoint works
- ✅ Stats endpoint shows session counts and disk usage
- ✅ Loading spinners appear during async operations
- ✅ Status badges show colored indicators
- ✅ Error boundary catches and displays errors gracefully
- ✅ "Back to Home" navigation works
- ✅ Progress indicator shows during agent execution
- ✅ UI is polished and professional-looking

---

## Files Created

**Backend:**
- `backend/services/cleanup_service.py`

**Frontend:**
- `frontend/components/LoadingSpinner.tsx`
- `frontend/components/ErrorBoundary.tsx`
- `frontend/components/StatusBadge.tsx`

**Modified:**
- `backend/main.py` (added startup event)
- `backend/routers/sessions.py` (added cleanup & stats endpoints)
- `backend/services/agent_service.py` (enhanced error handling)
- `frontend/app/session/[sessionId]/page.tsx` (UI polish)
- `frontend/app/layout.tsx` (error boundary)

---

## Configuration

Add to `backend/.env`:
```bash
SESSION_MAX_AGE_HOURS=1
CLEANUP_INTERVAL_MINUTES=30
```

---

## Final System Overview

```
User Flow:
1. Upload video → Session created (status: uploaded)
2. Process video → VideoProcessor extracts actions (status: processing → processed)
3. Start agent → Agent generates script with live screenshots (status: running → complete)
4. Download script → Playwright test ready to use

Background:
- Cleanup task runs every 30 minutes
- Sessions older than 1 hour are deleted
- Disk space is monitored

Frontend Features:
- Real-time WebSocket updates
- Live screenshot streaming
- Activity log
- Error handling with boundaries
- Loading states
- Professional UI
```

---

## Next Steps (Optional Future Enhancements)

**Phase 3 - Future Features:**
1. User authentication & authorization
2. Session persistence (PostgreSQL/MongoDB)
3. Session history and replay
4. Video trimming/editing before processing
5. Multi-browser support (Chrome, Firefox, Safari)
6. Headless mode toggle
7. Script editing in browser
8. Test execution directly from UI
9. Collaboration features (share sessions)
10. Usage analytics dashboard

---

## Project Complete! 🎉

All core functionality implemented:
- ✅ Video upload
- ✅ Video processing
- ✅ Agent execution
- ✅ Real-time screenshot streaming
- ✅ Test script generation
- ✅ Session cleanup
- ✅ Error handling
- ✅ Polished UI

The system is ready for testing and demo!
