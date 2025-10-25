"""
Main agent implementation using LangGraph for workflow test generation.
"""

import asyncio
import json
import logging
import os
import sys
import time
import warnings
from pathlib import Path
from typing import Any

# Add project root to path for direct execution
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    sys.path.insert(0, str(project_root))

from langchain_google_vertexai import ChatVertexAI
from langchain_core.tools import StructuredTool
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field, create_model

from src.agent_state import AgentState, AgentOutput
from src.agent_nodes import (
    parse_workflow_node,
    should_continue_execution,
    create_tool_node,
    create_agent_node,
)
from src.playwright_framework import PlaywrightToolkit, Tool
from src.workflow_schema import WorkflowInput
from src.debug_callback import NodeExecutionLogger
from src.config import (
    GCP_PROJECT_ID,
    GCP_LOCATION,
    MODEL_NAME,
    MODEL_TEMPERATURE,
    MODEL_MAX_OUTPUT_TOKENS,
    MODEL_TOP_P,
    MAX_ITERATIONS,
)


class WorkflowAgent:
    """
    LangGraph-based agent for converting workflows to test scripts.
    """
    
    def __init__(
        self,
        toolkit: PlaywrightToolkit,
        model_name: str = MODEL_NAME,
        project_id: str = GCP_PROJECT_ID,
        location: str = GCP_LOCATION,
        debug_mode: bool = False,
        debug_log_file: str = "logs/agent_debug.jsonl",
    ):
        """
        Initialize the workflow agent.
        
        Args:
            toolkit: PlaywrightToolkit instance with browser control
            model_name: Gemini model to use
            project_id: Google Cloud project ID
            location: Google Cloud region
            debug_mode: Enable debug logging of all node executions
            debug_log_file: Path to the debug log file (JSONL format)
        """
        self.toolkit = toolkit
        self.model_name = model_name
        self.project_id = project_id
        self.location = location
        self.debug_mode = debug_mode
        
        # Initialize debug callback if enabled
        self.debug_callback = None
        if debug_mode:
            self.debug_callback = NodeExecutionLogger(log_file=debug_log_file)
            print(f"🔍 Debug mode enabled. Logging to: {debug_log_file}")
        
        # Initialize Vertex AI model
        self.model = ChatVertexAI(
            model=model_name,
            project=project_id,
            location=location,
            temperature=MODEL_TEMPERATURE,
            max_output_tokens=MODEL_MAX_OUTPUT_TOKENS,
            top_p=MODEL_TOP_P,
        )
        
        # Convert Playwright tools to LangChain format
        self.tools = self._convert_tools_to_langchain()
        
        # Bind tools to model
        self.model_with_tools = self.model.bind_tools(self.tools)
        
        # Build the graph
        self.graph = self._build_graph()
    
    def _convert_tools_to_langchain(self) -> list:
        """Convert PlaywrightToolkit tools to LangChain tool format with proper schemas."""
        langchain_tools = []
        
        for tool_name, playwright_tool in self.toolkit.tools.items():
            # Dynamically create a Pydantic model for this tool's arguments
            fields = {}
            for param in playwright_tool.parameters:
                # Map parameter types to Python types
                type_mapping = {
                    "string": str,
                    "number": float,
                    "boolean": bool,
                    "object": dict,
                    "array": list,
                }
                
                python_type = type_mapping.get(param.type, str)
                
                # Create field with description
                if param.required:
                    fields[param.name] = (python_type, Field(..., description=param.description))
                else:
                    default_val = param.default if param.default is not None else None
                    fields[param.name] = (python_type | None, Field(default=default_val, description=param.description))
            
            # Create Pydantic model for args
            ArgsModel = create_model(
                f"{tool_name}_args",
                **fields
            )
            
            # Create async wrapper for the tool
            async def tool_func(_tool_name=tool_name, **kwargs):
                """Dynamically created tool function."""
                result = await self.toolkit.execute_tool(_tool_name, **kwargs)
                return json.dumps(result)
            
            # Create StructuredTool with explicit args_schema
            lc_tool = StructuredTool(
                name=tool_name,
                description=playwright_tool.description,
                coroutine=tool_func,
                args_schema=ArgsModel
            )
            
            langchain_tools.append(lc_tool)
        
        return langchain_tools
    
    def _build_graph(self) -> Any:
        """Build the LangGraph workflow graph."""
        
        # Create state graph
        workflow = StateGraph(AgentState)
        
        # Add nodes
        workflow.add_node("parse", parse_workflow_node)
        workflow.add_node("agent", create_agent_node(self.model_with_tools))
        workflow.add_node("execute_tools", create_tool_node(self.toolkit))
        
        # Set entry point
        workflow.set_entry_point("parse")
        
        # Add edges
        workflow.add_edge("parse", "agent")
        
        # Add conditional routing from agent
        workflow.add_conditional_edges(
            "agent",
            should_continue_execution,
            {
                "execute_tools": "execute_tools",
                "agent": "agent",
                "end": END,
            }
        )
        
        # Tools flow back to agent
        workflow.add_edge("execute_tools", "agent")
        
        # Compile the graph
        return workflow.compile()
    
    async def generate_test_script(
        self,
        workflow: WorkflowInput | dict,
        output_path: str,
    ) -> AgentOutput:
        """
        Generate a test script from a workflow.
        
        Args:
            workflow: WorkflowInput object or dictionary
            output_path: Path where test script should be saved
            
        Returns:
            AgentOutput with results
        """
        start_time = time.time()
        
        try:
            # Convert to dict if Pydantic model
            if isinstance(workflow, WorkflowInput):
                workflow_data = workflow.model_dump()
            else:
                workflow_data = workflow
            
            # Initialize state with all required fields
            initial_state = {
                "workflow_json": workflow_data,
                "workflow_name": "",
                "starting_url": "",
                "execution_state": {
                    "current_action_index": 0,
                    "total_actions": 0,
                    "actions_executed": [],
                    "actions_failed": [],
                    "observations": [],
                    "script_generated": False,
                    "script_path": None,
                },
                "test_script_content": "",
                "output_file_path": output_path,
                "messages": [],  # Will be populated by parse_workflow_node
                "next_step": None,
                "error": None,
                "retry_count": 0,
            }
            
            # Run the graph
            print("🤖 Starting agent workflow...")
            
            # Build config with callbacks if debug mode is enabled
            config = {"recursion_limit": MAX_ITERATIONS}
            if self.debug_callback:
                config["callbacks"] = [self.debug_callback]
            
            final_state = await self.graph.ainvoke(
                initial_state,
                config=config
            )
            
            execution_time = time.time() - start_time
            
            # Check results
            execution_state = final_state.get("execution_state", {})
            error = final_state.get("error")
            
            if error:
                return AgentOutput(
                    success=False,
                    error=error,
                    execution_time=execution_time,
                )
            
            script_path = execution_state.get("script_path")
            
            if not script_path:
                return AgentOutput(
                    success=False,
                    error="Agent did not generate a test script",
                    actions_count=len(execution_state.get("actions_executed", [])),
                    execution_time=execution_time,
                )
            
            # Count assertions in generated script
            assertions_count = 0
            try:
                with open(script_path, 'r') as f:
                    script_content = f.read()
                    assertions_count = script_content.count("assert ")
            except:
                pass
            
            return AgentOutput(
                success=True,
                file_path=script_path,
                actions_count=len(execution_state.get("actions_executed", [])),
                assertions_count=assertions_count,
                execution_time=execution_time,
            )
            
        except Exception as e:
            execution_time = time.time() - start_time
            return AgentOutput(
                success=False,
                error=f"Agent execution failed: {str(e)}",
                execution_time=execution_time,
            )


# Example usage
async def main():
    """Example of using the WorkflowAgent."""
    from src.workflow_schema import WorkflowInput
    
    # Auto-detect and set credentials
    creds_file = Path("vertex-ai-credentials.json")
    if creds_file.exists() and not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print(f"📍 Found {creds_file}")
        print("   Setting GOOGLE_APPLICATION_CREDENTIALS...")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(creds_file.absolute())
    elif not os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        print("❌ Google Cloud credentials not found!")
        print("   Please set GOOGLE_APPLICATION_CREDENTIALS or add vertex-ai-credentials.json")
        return
    
    # Load example workflow
    with open("workflows/mando_test1_workflow.json", "r") as f:
        workflow_data = json.load(f)
    
    workflow = WorkflowInput.model_validate(workflow_data)
    
    # Initialize toolkit
    toolkit = PlaywrightToolkit(headless=False)
    await toolkit.initialize()
    
    try:
        # Create agent with debug mode enabled
        agent = WorkflowAgent(
            toolkit=toolkit,
            debug_mode=True,  # Enable debug logging
            debug_log_file="logs/agent_debug.jsonl"
        )
        
        # Generate test script
        result = await agent.generate_test_script(
            workflow=workflow,
            output_path="gen_tests/mando_test1_generated.py"
        )
        
        if result.success:
            print(f"\n✅ Test script generated successfully!")
            print(f"   File: {result.file_path}")
            print(f"   Actions executed: {result.actions_count}")
            print(f"   Assertions added: {result.assertions_count}")
            print(f"   Execution time: {result.execution_time:.2f}s")
        else:
            print(f"\n❌ Failed to generate test script")
            print(f"   Error: {result.error}")
            
    finally:
        await toolkit.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
