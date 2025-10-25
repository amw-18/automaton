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
