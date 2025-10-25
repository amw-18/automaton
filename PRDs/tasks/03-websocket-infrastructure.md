# Task 03: WebSocket Infrastructure

**Goal**: Set up WebSocket connections for real-time communication between frontend and backend

**Depends On**: Task 02  
**Status**: Not Started  
**Estimated Time**: 2-3 hours

---

## Backend Changes

### 1. Install WebSocket Dependencies
Add to `backend/requirements.txt`:
```
websockets==12.0
```

### 2. Create Stream Manager (`backend/services/stream_service.py`)
```python
from typing import Dict, List
from fastapi import WebSocket
from datetime import datetime
import json

class StreamManager:
    """Manages WebSocket connections and message broadcasting"""
    
    def __init__(self):
        # Map: session_id -> list of WebSocket connections
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, session_id: str, websocket: WebSocket):
        """Register a new WebSocket connection for a session"""
        await websocket.accept()
        
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        
        self.active_connections[session_id].append(websocket)
        print(f"✓ WebSocket connected for session: {session_id}")
    
    async def disconnect(self, session_id: str, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if session_id in self.active_connections:
            if websocket in self.active_connections[session_id]:
                self.active_connections[session_id].remove(websocket)
            
            # Clean up empty lists
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]
        
        print(f"✗ WebSocket disconnected for session: {session_id}")
    
    async def send_message(self, session_id: str, message: dict):
        """Send a message to all connections for a session"""
        if session_id not in self.active_connections:
            return
        
        # Remove disconnected clients
        dead_connections = []
        
        for connection in self.active_connections[session_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                print(f"Error sending to connection: {e}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        for connection in dead_connections:
            await self.disconnect(session_id, connection)
    
    async def broadcast_status(self, session_id: str, status: str, log: dict = None):
        """Broadcast status update to all clients"""
        message = {
            "type": "status",
            "sessionId": session_id,
            "status": status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if log:
            message["log"] = log
        
        await self.send_message(session_id, message)
    
    async def broadcast_screenshot(self, session_id: str, screenshot_path: str):
        """Broadcast new screenshot to all clients"""
        from pathlib import Path
        
        message = {
            "type": "screenshot",
            "sessionId": session_id,
            "imageUrl": f"/api/screenshots/{session_id}/{Path(screenshot_path).name}",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        await self.send_message(session_id, message)
    
    async def broadcast_complete(self, session_id: str, success: bool, script_path: str = None, error: str = None):
        """Broadcast completion message"""
        message = {
            "type": "complete",
            "sessionId": session_id,
            "success": success,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if script_path:
            message["scriptPath"] = f"/api/scripts/{session_id}/test.py"
        
        if error:
            message["error"] = error
        
        await self.send_message(session_id, message)

# Global instance
stream_manager = StreamManager()
```

### 3. Create WebSocket Router (`backend/routers/websocket.py`)
```python
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from backend.services.stream_service import stream_manager
from backend.models.session import session_manager

router = APIRouter()

@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """WebSocket endpoint for real-time updates"""
    
    # Verify session exists
    session = session_manager.get_session(session_id)
    if not session:
        await websocket.close(code=4004, reason="Session not found")
        return
    
    # Connect
    await stream_manager.connect(session_id, websocket)
    
    try:
        # Send initial connection confirmation
        await websocket.send_json({
            "type": "connected",
            "sessionId": session_id,
            "status": session.status
        })
        
        # Keep connection alive and listen for messages
        while True:
            data = await websocket.receive_text()
            
            # Parse client message
            try:
                message = eval(data) if isinstance(data, str) else data
                
                # Handle ping/pong for keep-alive
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                
            except Exception as e:
                print(f"Error processing message: {e}")
    
    except WebSocketDisconnect:
        await stream_manager.disconnect(session_id, websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        await stream_manager.disconnect(session_id, websocket)
```

### 4. Update Main App (`backend/main.py`)
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv

# Import routers
from backend.routers import videos, sessions, websocket

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
app.include_router(websocket.router)  # NEW

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

### 5. Update Router Init (`backend/routers/__init__.py`)
```python
from . import videos, sessions, websocket

__all__ = ["videos", "sessions", "websocket"]
```

---

## Frontend Changes

### 1. Create WebSocket Hook (`frontend/lib/useWebSocket.ts`)
```typescript
import { useEffect, useRef, useState } from 'react';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export interface WebSocketMessage {
  type: 'connected' | 'status' | 'screenshot' | 'complete' | 'pong';
  sessionId: string;
  status?: string;
  imageUrl?: string;
  timestamp?: string;
  log?: any;
  success?: boolean;
  scriptPath?: string;
  error?: string;
}

export function useWebSocket(sessionId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!sessionId) return;

    // Create WebSocket connection
    const ws = new WebSocket(`${WS_URL}/ws/${sessionId}`);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      
      // Start ping interval for keep-alive
      const pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 30000); // Every 30 seconds

      ws.addEventListener('close', () => {
        clearInterval(pingInterval);
      });
    };

    ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        console.log('WebSocket message:', message);
        setLastMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      setIsConnected(false);
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);
    };

    wsRef.current = ws;

    // Cleanup on unmount
    return () => {
      ws.close();
    };
  }, [sessionId]);

  const sendMessage = (message: any) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  };

  return {
    isConnected,
    lastMessage,
    sendMessage,
  };
}
```

### 2. Update Session Page with WebSocket (`frontend/app/session/[sessionId]/page.tsx`)
```typescript
'use client';

import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { api } from '@/lib/api';
import { useWebSocket, WebSocketMessage } from '@/lib/useWebSocket';

export default function SessionPage() {
  const params = useParams();
  const sessionId = params.sessionId as string;
  const [session, setSession] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);

  // WebSocket connection
  const { isConnected, lastMessage } = useWebSocket(sessionId);

  // Load initial session data
  useEffect(() => {
    api.getSession(sessionId)
      .then(setSession)
      .catch(err => setError(err.message))
      .finally(() => setLoading(false));
  }, [sessionId]);

  // Handle WebSocket messages
  useEffect(() => {
    if (lastMessage) {
      setMessages(prev => [...prev, lastMessage]);
      
      // Update session status if status message received
      if (lastMessage.type === 'status' && lastMessage.status) {
        setSession((prev: any) => prev ? { ...prev, status: lastMessage.status } : null);
      }
    }
  }, [lastMessage]);

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

        {/* WebSocket Messages Log */}
        <div className="bg-white shadow rounded-lg p-6">
          <h2 className="text-xl font-semibold mb-4">Real-Time Updates</h2>
          <div className="space-y-2 max-h-96 overflow-y-auto">
            {messages.length === 0 ? (
              <p className="text-gray-500 text-sm">Waiting for updates...</p>
            ) : (
              messages.map((msg, idx) => (
                <div key={idx} className="text-sm border-l-2 border-blue-500 pl-3 py-1">
                  <span className="font-medium">{msg.type}</span>
                  {msg.status && <span className="text-gray-600"> - {msg.status}</span>}
                  {msg.timestamp && (
                    <span className="text-xs text-gray-400 ml-2">
                      {new Date(msg.timestamp).toLocaleTimeString()}
                    </span>
                  )}
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

### 3. Update Environment File (`frontend/.env.local`)
```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

---

## Testing

### 1. Start Backend
```bash
cd backend
pip install -r requirements.txt  # Install websockets
python main.py
```

### 2. Start Frontend
```bash
cd frontend
npm run dev
```

### 3. Test WebSocket Connection
1. Upload a video at http://localhost:3000
2. On session page, verify "Connected" indicator shows green dot
3. Open browser dev tools → Network → WS tab
4. Should see WebSocket connection to `ws://localhost:8000/ws/{sessionId}`
5. Should receive "connected" message with session status

### 4. Test in Python (optional)
```python
import asyncio
import websockets
import json

async def test_websocket():
    uri = "ws://localhost:8000/ws/test-session-id"
    async with websockets.connect(uri) as websocket:
        # Receive connection confirmation
        response = await websocket.recv()
        print(f"Received: {response}")
        
        # Send ping
        await websocket.send(json.dumps({"type": "ping"}))
        
        # Receive pong
        response = await websocket.recv()
        print(f"Received: {response}")

asyncio.run(test_websocket())
```

---

## Success Criteria

- ✅ WebSocket endpoint accepts connections at `/ws/{sessionId}`
- ✅ Frontend establishes WebSocket connection automatically
- ✅ Connection status indicator works (green/red dot)
- ✅ "Connected" message received on initial connection
- ✅ Ping/pong keep-alive works
- ✅ Messages are logged in real-time on frontend
- ✅ Multiple tabs can connect to same session
- ✅ Disconnection is handled gracefully

---

## Files Created

**Backend:**
- `backend/services/stream_service.py`
- `backend/routers/websocket.py`

**Frontend:**
- `frontend/lib/useWebSocket.ts`

**Modified:**
- `backend/main.py`
- `backend/routers/__init__.py`
- `backend/requirements.txt`
- `frontend/app/session/[sessionId]/page.tsx`
- `frontend/.env.local`

---

## Next Task
**Task 04**: Video Processing Integration (convert video to WorkflowInput)
