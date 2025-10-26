import sys
from pathlib import Path
import asyncio

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.playwright_framework import PlaywrightToolkit
from src.agent import WorkflowAgent
from src.workflow_schema import WorkflowInput
from models.session import session_manager
from services.stream_service import stream_manager

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
        
        # Setup paths - ALL outputs go to session directory
        session_dir = Path(session.video_path).parent
        screenshot_dir = session_dir / "screenshots"
        output_dir = session_dir / "output"
        logs_dir = session_dir / "logs"
        output_dir.mkdir(exist_ok=True)
        screenshot_dir.mkdir(exist_ok=True)
        logs_dir.mkdir(exist_ok=True)
        
        script_path = output_dir / "test_generated.py"
        debug_log_path = logs_dir / f"agent_{session_id}.jsonl"
        
        toolkit = None
        
        try:
            # Initialize Playwright toolkit with custom screenshot directory and target output path
            toolkit = PlaywrightToolkit(
                headless=False,  # Set to True for production
                screenshot_dir=str(screenshot_dir),
                target_output_path=str(script_path)
            )
            
            # Set screenshot callback for streaming
            async def screenshot_callback(path: str):
                """Called after each screenshot is captured"""
                print(f"🔄 Streaming screenshot: {path}")
                # Make path relative to uploads directory for URL construction
                rel_path = Path(path).relative_to(Path("uploads"))
                
                # Add event to session
                session.add_event("screenshot", {"path": str(rel_path)})
                session_manager.save_session(session)
                
                await stream_manager.broadcast_screenshot(session_id, str(rel_path))
            
            toolkit.set_screenshot_callback(screenshot_callback)
            
            # Initialize browser
            await toolkit.initialize()
            
            # Create agent
            agent = WorkflowAgent(
                toolkit=toolkit,
                debug_mode=True,
                debug_log_file=str(debug_log_path)
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
                session.add_event("script_generated", {
                    "script_path": str(script_path),
                    "actions_count": result.actions_count
                })
                session_manager.update_status(session_id, "complete")
                session_manager.save_session(session)
                
                await stream_manager.broadcast_complete(
                    session_id,
                    success=True,
                    script_path=str(script_path)
                )
                
                print(f"✅ Agent completed successfully")
                print(f"   Script: {script_path}")
                print(f"   Actions: {result.actions_count}")
                
            else:
                session.add_event("error", {"error": result.error})
                session_manager.update_status(session_id, "error")
                session_manager.save_session(session)
                
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
