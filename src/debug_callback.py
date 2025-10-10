"""
Debug callback handler for LangGraph node execution logging.
Captures input, output, and metadata for every node execution.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult


class NodeExecutionLogger(BaseCallbackHandler):
    """
    Callback handler that logs all LangGraph node executions to a file.
    Captures input state, output state, timestamps, and metadata.
    """
    
    def __init__(self, log_file: str = "logs/agent_debug.jsonl"):
        """
        Initialize the logger.
        
        Args:
            log_file: Path to the log file (JSONL format)
        """
        self.log_file = Path(log_file)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize log file with header
        if not self.log_file.exists():
            self._write_header()
        
        self.current_node = None
        self.node_start_time = None
        self.execution_count = 0
        
    def _write_header(self):
        """Write header information to log file."""
        header = {
            "type": "session_start",
            "timestamp": datetime.now().isoformat(),
            "description": "LangGraph Agent Debug Log"
        }
        with open(self.log_file, 'w') as f:
            f.write(json.dumps(header) + '\n')
    
    def _write_log(self, log_entry: Dict[str, Any]):
        """Write a log entry to the file."""
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(log_entry, default=str) + '\n')
        except Exception as e:
            print(f"⚠️  Error writing to log file: {e}")
    
    def _sanitize_for_logging(self, obj: Any, max_depth: int = 5, current_depth: int = 0) -> Any:
        """
        Sanitize objects for JSON serialization.
        Handles complex objects and prevents infinite recursion.
        """
        if current_depth > max_depth:
            return "<max_depth_reached>"
        
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        
        if isinstance(obj, dict):
            return {
                k: self._sanitize_for_logging(v, max_depth, current_depth + 1)
                for k, v in obj.items()
            }
        
        if isinstance(obj, (list, tuple)):
            return [
                self._sanitize_for_logging(item, max_depth, current_depth + 1)
                for item in obj
            ]
        
        # Handle objects with __dict__
        if hasattr(obj, '__dict__'):
            return {
                'type': type(obj).__name__,
                'data': self._sanitize_for_logging(obj.__dict__, max_depth, current_depth + 1)
            }
        
        # Fallback to string representation
        return str(obj)
    
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Called when a chain (node) starts execution."""
        try:
            self.execution_count += 1
            self.node_start_time = datetime.now()
            
            # Extract node name with better error handling
            # Try multiple sources for the node name
            node_name = "unknown"
            
            # Try kwargs first (often has metadata)
            if "metadata" in kwargs and isinstance(kwargs["metadata"], dict):
                node_name = kwargs["metadata"].get("langgraph_node", node_name)
            
            # Try serialized dict
            if serialized is not None:
                if "name" in serialized and serialized["name"]:
                    node_name = serialized["name"]
                if "id" in serialized:
                    node_parts = serialized["id"]
                    if isinstance(node_parts, list) and len(node_parts) > 0:
                        # Get the last part which is usually the node name
                        node_name = node_parts[-1]
            
            # Try tags (sometimes node name is in tags)
            if "tags" in kwargs and isinstance(kwargs["tags"], list):
                for tag in kwargs["tags"]:
                    if tag.startswith("seq:step:"):
                        # Extract step number
                        node_name = tag.replace("seq:step:", "step_")
                        break
            
            self.current_node = node_name
        
            log_entry = {
                "type": "node_start",
                "execution_id": self.execution_count,
                "node_name": node_name,
                "timestamp": self.node_start_time.isoformat(),
                "inputs": self._sanitize_for_logging(inputs),
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                    "parent_run_id": str(kwargs.get("parent_run_id", "")),
                    "tags": kwargs.get("tags", []),
                }
            }
            
            self._write_log(log_entry)
            print(f"🔍 [DEBUG] Node '{node_name}' started (execution #{self.execution_count})")
        except Exception as e:
            print(f"⚠️  Error in on_chain_start callback: {e}")
    
    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        **kwargs: Any,
    ) -> None:
        """Called when a chain (node) ends execution."""
        try:
            end_time = datetime.now()
            duration = (end_time - self.node_start_time).total_seconds() if self.node_start_time else 0
            
            log_entry = {
                "type": "node_end",
                "execution_id": self.execution_count,
                "node_name": self.current_node if self.current_node else "unknown",
                "timestamp": end_time.isoformat(),
                "duration_seconds": duration,
                "outputs": self._sanitize_for_logging(outputs),
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"✅ [DEBUG] Node '{self.current_node}' completed in {duration:.2f}s")
        except Exception as e:
            print(f"⚠️  Error in on_chain_end callback: {e}")
    
    def on_chain_error(
        self,
        error: Exception,
        **kwargs: Any,
    ) -> None:
        """Called when a chain (node) encounters an error."""
        try:
            end_time = datetime.now()
            duration = (end_time - self.node_start_time).total_seconds() if self.node_start_time else 0
            
            log_entry = {
                "type": "node_error",
                "execution_id": self.execution_count,
                "node_name": self.current_node if self.current_node else "unknown",
                "timestamp": end_time.isoformat(),
                "duration_seconds": duration,
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"❌ [DEBUG] Node '{self.current_node}' failed: {error}")
        except Exception as e:
            print(f"⚠️  Error in on_chain_error callback: {e}")
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any,
    ) -> None:
        """Called when LLM starts generating."""
        try:
            log_entry = {
                "type": "llm_start",
                "timestamp": datetime.now().isoformat(),
                "model": serialized.get("name", "unknown") if serialized else "unknown",
                "prompt_count": len(prompts),
                "prompts": prompts if len(prompts) <= 3 else prompts[:3] + ["...truncated"],
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                    "invocation_params": kwargs.get("invocation_params", {}),
                }
            }
            
            self._write_log(log_entry)
            print(f"🤖 [DEBUG] LLM call started")
        except Exception as e:
            print(f"⚠️  Error in on_llm_start callback: {e}")
    
    def on_llm_end(
        self,
        response: LLMResult,
        **kwargs: Any,
    ) -> None:
        """Called when LLM finishes generating."""
        try:
            log_entry = {
                "type": "llm_end",
                "timestamp": datetime.now().isoformat(),
                "generations_count": len(response.generations) if response and response.generations else 0,
                "llm_output": self._sanitize_for_logging(response.llm_output) if response and response.llm_output else None,
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"🤖 [DEBUG] LLM call completed")
        except Exception as e:
            print(f"⚠️  Error in on_llm_end callback: {e}")
    
    def on_llm_error(
        self,
        error: Exception,
        **kwargs: Any,
    ) -> None:
        """Called when LLM encounters an error."""
        try:
            log_entry = {
                "type": "llm_error",
                "timestamp": datetime.now().isoformat(),
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"❌ [DEBUG] LLM call failed: {error}")
        except Exception as e:
            print(f"⚠️  Error in on_llm_error callback: {e}")
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any,
    ) -> None:
        """Called when a tool starts execution."""
        try:
            tool_name = serialized.get("name", "unknown") if serialized else "unknown"
            
            log_entry = {
                "type": "tool_start",
                "timestamp": datetime.now().isoformat(),
                "tool_name": tool_name,
                "input": input_str,
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"🔧 [DEBUG] Tool '{tool_name}' started")
        except Exception as e:
            print(f"⚠️  Error in on_tool_start callback: {e}")
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any,
    ) -> None:
        """Called when a tool finishes execution."""
        try:
            log_entry = {
                "type": "tool_end",
                "timestamp": datetime.now().isoformat(),
                "output": output[:500] if len(output) > 500 else output,  # Truncate long outputs
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"🔧 [DEBUG] Tool completed")
        except Exception as e:
            print(f"⚠️  Error in on_tool_end callback: {e}")
    
    def on_tool_error(
        self,
        error: Exception,
        **kwargs: Any,
    ) -> None:
        """Called when a tool encounters an error."""
        try:
            log_entry = {
                "type": "tool_error",
                "timestamp": datetime.now().isoformat(),
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
                "metadata": {
                    "run_id": str(kwargs.get("run_id", "")),
                }
            }
            
            self._write_log(log_entry)
            print(f"❌ [DEBUG] Tool failed: {error}")
        except Exception as e:
            print(f"⚠️  Error in on_tool_error callback: {e}")
