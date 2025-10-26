import shutil
from pathlib import Path
from datetime import datetime, timedelta
from models.session import session_manager
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
            # Delete uploaded files (videos, screenshots, scripts)
            session_dir = self.uploads_dir / session_id
            if session_dir.exists():
                try:
                    shutil.rmtree(session_dir)
                    print(f"  ✓ Deleted session files: {session_id}")
                except Exception as e:
                    print(f"  ✗ Error deleting {session_id}: {e}")
            
            # Delete session JSON file
            session_file = Path("sessions") / f"{session_id}.json"
            if session_file.exists():
                try:
                    session_file.unlink()
                    print(f"  ✓ Deleted session record: {session_id}")
                except Exception as e:
                    print(f"  ✗ Error deleting session record: {e}")
            
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
