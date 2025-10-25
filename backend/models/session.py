from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import uuid
import sys
from pathlib import Path

# Add parent directory to import from src/
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.workflow_schema import WorkflowInput

@dataclass
class Session:
    id: str
    video_path: Optional[str] = None
    workflow: Optional[WorkflowInput] = None
    status: str = "created"  # created, uploaded, processing, processed, running, complete, error
    created_at: datetime = None
    script_path: Optional[str] = None
    
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
