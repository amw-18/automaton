"""
Node functions for the LangGraph agent.
Each node represents a step in the workflow processing pipeline.
"""

import json
from typing import Any
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.agent_state import AgentState
from src.workflow_schema import WorkflowInput
from src.config import SYSTEM_PROMPT


def parse_workflow_node(state: AgentState) -> dict:
    """
    Parse and validate the workflow JSON.
    First node in the graph.
    """
    print("📋 Parsing workflow...")
    
    workflow_data = state["workflow_json"]
    
    try:
        # Validate using Pydantic
        workflow = WorkflowInput.model_validate(workflow_data)
        
        # Extract key information
        workflow_name = workflow.metadata.name
        starting_url = workflow.starting_url
        total_actions = len(workflow.actions)
        
        # Initialize execution state
        execution_state = {
            "current_action_index": 0,
            "total_actions": total_actions,
            "actions_executed": [],
            "actions_failed": [],
            "observations": [],
            "script_generated": False,
            "script_path": None,
        }
        
        # Get output file path from state
        output_file_path = state.get("output_file_path", "tests/test_generated.py")
        
        # Create initial message for the agent
        initial_message = HumanMessage(
            content=f"""I have a workflow to convert into a Playwright test script.

Workflow: {workflow_name}
Starting URL: {starting_url}
Total Actions: {total_actions}
Output File: {output_file_path}

Actions overview:
{chr(10).join(f"{i+1}. {action.action_type}: {action.description}" for i, action in enumerate(workflow.actions))}

Your task:
1. Execute each action in the browser to observe behavior
2. Generate a complete Playwright test script
3. Save it to: {output_file_path} using save_test_script_to_file

Let's begin!"""
        )
        
        messages_to_return = [SystemMessage(content=SYSTEM_PROMPT), initial_message]
        print(f"📋 Parse complete. Returning {len(messages_to_return)} messages")
        
        return {
            "workflow_name": workflow_name,
            "starting_url": starting_url,
            "execution_state": execution_state,
            "messages": messages_to_return,
            "next_step": "execute",
            "error": None,
        }
        
    except Exception as e:
        return {
            "error": f"Failed to parse workflow: {str(e)}",
            "next_step": "end",
        }


def should_continue_execution(state: AgentState) -> str:
    """
    Routing function to determine next step after each iteration.
    """
    # Check for errors
    if state.get("error"):
        return "end"
    
    # Check next_step directive
    next_step = state.get("next_step")
    if next_step == "end":
        return "end"
    
    # Check if we have a script saved
    execution_state = state.get("execution_state", {})
    if execution_state.get("script_path"):
        return "end"
    
    # Check if all actions executed and script generated
    if execution_state.get("script_generated"):
        return "end"
    
    # Check last message for tool calls
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if isinstance(last_message, AIMessage) and last_message.tool_calls:
            return "execute_tools"
    
    # Check if we've executed a reasonable number of actions without generating script
    # This helps detect when agent is stuck in execution loop
    actions_executed = len(execution_state.get("actions_executed", []))
    total_actions = execution_state.get("total_actions", 0)
    
    # If we've executed at least as many actions as in the workflow, remind agent to generate script
    if actions_executed >= total_actions and total_actions > 0:
        print(f"⚠️  All {total_actions} workflow actions executed. Agent should now generate test script.")
    
    # Continue agent reasoning
    return "agent"


def create_tool_node(toolkit):
    """
    Factory function to create a tool execution node.
    This is called during graph construction.
    """
    
    async def execute_tools_node(state: AgentState) -> dict:
        """Execute tool calls from the agent."""
        messages = state["messages"]
        last_message = messages[-1]
        
        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return {"messages": []}
        
        tool_messages = []
        
        for tool_call in last_message.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_call_id = tool_call["id"]
            
            print(f"🔧 Executing tool: {tool_name}")
            
            # Execute the tool
            result = await toolkit.execute_tool(tool_name, **tool_args)
            
            # Handle screenshot tool specially - include image for vision models
            if tool_name == "capture_labeled_screenshot" and result.get("success"):
                tool_result = result.get("result", {})
                
                # Check if we have image data
                if isinstance(tool_result, dict) and "image_base64" in tool_result:
                    # ToolMessage with text description
                    tool_message = ToolMessage(
                        content=tool_result.get("text_description", "Screenshot captured"),
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                    tool_messages.append(tool_message)
                    
                    # Add HumanMessage with the image for vision context
                    image_message = HumanMessage(
                        content=[
                            {
                                "type": "text",
                                "text": f"Here is the labeled screenshot (saved to {tool_result.get('screenshot_path', 'screenshot')}):"
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{tool_result['image_base64']}"
                                }
                            }
                        ]
                    )
                    tool_messages.append(image_message)
                else:
                    # Fallback to JSON
                    content = json.dumps(result)
                    tool_message = ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id,
                        name=tool_name,
                    )
                    tool_messages.append(tool_message)
            else:
                # Regular tool result - just JSON
                content = json.dumps(result) if result else json.dumps({"success": False, "error": "No result"})
                tool_message = ToolMessage(
                    content=content,
                    tool_call_id=tool_call_id,
                    name=tool_name,
                )
                tool_messages.append(tool_message)
            
            # Track execution state
            execution_state = state.get("execution_state", {})
            
            # Track browser action execution (don't count screenshot or wait tools)
            browser_action_tools = [
                "navigate_to_url", "click_element", "type_text", "select_option",
                "press_key", "hover_element", "scroll_page"
            ]
            
            if tool_name in browser_action_tools:
                if result.get("success"):
                    execution_state["actions_executed"].append(tool_name)
                    print(f"✓ Action executed: {tool_name} ({len(execution_state['actions_executed'])}/{execution_state.get('total_actions', '?')})")
                else:
                    execution_state["actions_failed"].append(tool_name)
                    print(f"✗ Action failed: {tool_name}")
            
            # Check if script was saved
            if tool_name == "save_test_script_to_file" and result.get("success"):
                execution_state["script_generated"] = True
                execution_state["script_path"] = tool_args.get("file_path")
        
        return {
            "messages": tool_messages,
            "execution_state": execution_state,
        }
    
    return execute_tools_node


def create_agent_node(model_with_tools):
    """
    Factory function to create the agent reasoning node.
    """
    
    def agent_node(state: AgentState) -> dict:
        """Agent reasoning and decision making."""
        messages = state.get("messages", [])
        execution_state = state.get("execution_state", {})
        
        print(f"🤖 Agent node received {len(messages)} messages")
        
        # Validate messages list
        if not messages:
            print("⚠️  Warning: Empty messages list in agent_node")
            print(f"   State keys: {list(state.keys())}")
            return {"messages": [], "error": "Empty messages list"}
        
        # Filter out any None or empty messages
        messages = [msg for msg in messages if msg and hasattr(msg, 'content')]
        
        # Check if all actions are executed but script not yet generated
        actions_executed = len(execution_state.get("actions_executed", []))
        total_actions = execution_state.get("total_actions", 0)
        script_generated = execution_state.get("script_generated", False)
        
        # Inject a reminder if all actions executed but no script yet
        if actions_executed >= total_actions and total_actions > 0 and not script_generated:
            # Check if we haven't already added this reminder
            last_message = messages[-1] if messages else None
            if not (isinstance(last_message, SystemMessage) and "now generate the test script" in last_message.content.lower()):
                print(f"📝 Injecting reminder: All {total_actions} actions executed, time to generate script")
                reminder = SystemMessage(
                    content=f"""REMINDER: You have successfully executed all {total_actions} workflow actions. 

Now you MUST:
1. Use write_test_script to create the complete Playwright test script
2. Use save_test_script_to_file to save it to the specified output path

The task is NOT complete until you call save_test_script_to_file."""
                )
                messages = messages + [reminder]
        
        # Final validation before invoking model
        if not messages:
            print("⚠️  Error: Messages list is empty after processing")
            return {"messages": [], "error": "No valid messages to send to model"}
        
        try:
            # Invoke the model with tools
            response = model_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            print(f"⚠️  Model invocation error: {e}")
            print(f"   Messages count: {len(messages)}")
            print(f"   Last message type: {type(messages[-1]).__name__ if messages else 'None'}")
            raise
    
    return agent_node
