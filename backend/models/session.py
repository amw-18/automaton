from datetime import datetime
from typing import Optional, List, Dict
import uuid
import sys
from pathlib import Path
import json
from pydantic import BaseModel, Field

# Add parent directory to import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.workflow_schema import WorkflowInput


class SessionEvent(BaseModel):
    """Event in session history"""
    timestamp: str
    event_type: str  # status_change, screenshot, error, log
    data: Dict
    
    model_config = {"extra": "forbid"}


class Session(BaseModel):
    id: str
    video_path: str
    status: str  # created, uploaded, processing, processed, running, complete, testing, test_complete, test_failed, error
    workflow: Optional[WorkflowInput] = None
    script_path: Optional[str] = None
    test_video_path: Optional[str] = None  # Path to test execution video
    created_at: datetime = Field(default_factory=datetime.utcnow)
    events: List[SessionEvent] = Field(default_factory=list)
    
    model_config = {"extra": "forbid"}
    
    def add_event(self, event_type: str, data: Dict):
        """Add an event to session history"""
        event = SessionEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type=event_type,
            data=data
        )
        self.events.append(event)
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "video_path": self.video_path,
            "status": self.status,
            "workflow": self.workflow.model_dump() if self.workflow else None,
            "script_path": self.script_path,
            "test_video_path": self.test_video_path,
            "created_at": self.created_at.isoformat(),
            "events": [e.model_dump() for e in self.events]
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Session':
        """Load from dictionary"""
        workflow = None
        if data.get("workflow"):
            workflow = WorkflowInput.model_validate(data["workflow"])
        
        events = []
        for e in data.get("events", []):
            events.append(SessionEvent(**e))
        
        return cls(
            id=data["id"],
            video_path=data["video_path"],
            status=data["status"],
            workflow=workflow,
            script_path=data.get("script_path"),
            test_video_path=data.get("test_video_path"),
            created_at=datetime.fromisoformat(data["created_at"]),
            events=events
        )

class SessionManager:
    def __init__(self, persist_dir: str = "sessions"):
        self.sessions: dict[str, Session] = {}
        self.persist_dir = Path(persist_dir)
        self.persist_dir.mkdir(exist_ok=True)
        self.load_all_sessions()
    
    def _get_session_file(self, session_id: str) -> Path:
        """Get the file path for a session"""
        return self.persist_dir / f"{session_id}.json"
    
    def save_session(self, session: Session):
        """Save session to disk"""
        try:
            file_path = self._get_session_file(session.id)
            with open(file_path, 'w') as f:
                json.dump(session.to_dict(), f, indent=2)
        except Exception as e:
            print(f"Error saving session {session.id}: {e}")
    
    def load_session(self, session_id: str) -> Optional[Session]:
        """Load a single session from disk"""
        try:
            file_path = self._get_session_file(session_id)
            if not file_path.exists():
                return None
            
            with open(file_path, 'r') as f:
                data = json.load(f)
                return Session.from_dict(data)
        except Exception as e:
            print(f"Error loading session {session_id}: {e}")
            return None
    
    def load_all_sessions(self):
        """Load all sessions from disk on startup"""
        if not self.persist_dir.exists():
            return
        
        for file_path in self.persist_dir.glob("*.json"):
            try:
                with open(file_path, 'r') as f:
                    data = json.load(f)
                    session = Session.from_dict(data)
                    self.sessions[session.id] = session
            except Exception as e:
                print(f"Error loading session from {file_path}: {e}")
        
        print(f"✅ Loaded {len(self.sessions)} sessions from disk")
    
    def create_session(self) -> Session:
        session_id = str(uuid.uuid4())
        session = Session(id=session_id, video_path="", status="created")
        self.sessions[session_id] = session
        session.add_event("status_change", {"status": "created"})
        self.save_session(session)
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        return self.sessions.get(session_id)
    
    def get_all_sessions(self) -> List[Session]:
        """Get all sessions sorted by created date (newest first)"""
        return sorted(self.sessions.values(), key=lambda s: s.created_at, reverse=True)
    
    def update_status(self, session_id: str, status: str):
        if session := self.sessions.get(session_id):
            old_status = session.status
            session.status = status
            session.add_event("status_change", {"from": old_status, "to": status})
            self.save_session(session)

# Global instance
session_manager = SessionManager()
