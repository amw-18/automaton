"""
State definition for the workflow automation agent.
"""

from typing import Annotated, Literal
from typing_extensions import TypedDict
from langgraph.graph import MessagesState
from pydantic import BaseModel, Field


class WorkflowExecutionState(TypedDict):
    """State tracked during workflow execution."""
    current_action_index: int
    total_actions: int
    actions_executed: list[str]
    actions_failed: list[str]
    observations: list[str]
    script_generated: bool
    script_path: str | None


class AgentState(MessagesState):
    """
    Main state for the agent graph.
    Extends MessagesState to include conversation history plus custom fields.
    """
    # Workflow data
    workflow_json: dict
    workflow_name: str
    starting_url: str
    
    # Execution tracking
    execution_state: WorkflowExecutionState
    
    # Script generation
    test_script_content: str
    output_file_path: str
    
    # Control flow
    next_step: Literal["execute", "generate", "refine", "save", "end"] | None
    error: str | None
    retry_count: int


class AgentOutput(BaseModel):
    """Output from the agent after processing a workflow."""
    success: bool = Field(..., description="Whether the agent completed successfully")
    file_path: str | None = Field(None, description="Path to generated test script")
    actions_count: int = Field(0, description="Number of actions executed")
    assertions_count: int = Field(0, description="Number of assertions added")
    error: str | None = Field(None, description="Error message if failed")
    execution_time: float = Field(0.0, description="Total execution time in seconds")
