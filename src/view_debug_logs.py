"""
Utility script to view and analyze debug logs from the agent.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any


def format_timestamp(iso_timestamp: str) -> str:
    """Format ISO timestamp to readable format."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        return dt.strftime("%H:%M:%S.%f")[:-3]
    except:
        return iso_timestamp


def print_node_execution(entry: Dict[str, Any], detailed: bool = False):
    """Print a formatted node execution entry."""
    node_type = entry.get("type", "")
    
    if node_type == "node_start":
        node_name = entry.get("node_name", "unknown")
        exec_id = entry.get("execution_id", "?")
        timestamp = format_timestamp(entry.get("timestamp", ""))
        
        print(f"\n{'='*80}")
        print(f"🔍 NODE START [#{exec_id}] - {node_name}")
        print(f"   Time: {timestamp}")
        
        if detailed:
            inputs = entry.get("inputs", {})
            print(f"\n   Inputs:")
            print(f"   {json.dumps(inputs, indent=4)}")
    
    elif node_type == "node_end":
        node_name = entry.get("node_name", "unknown")
        exec_id = entry.get("execution_id", "?")
        duration = entry.get("duration_seconds", 0)
        timestamp = format_timestamp(entry.get("timestamp", ""))
        
        print(f"\n✅ NODE END [#{exec_id}] - {node_name}")
        print(f"   Time: {timestamp}")
        print(f"   Duration: {duration:.2f}s")
        
        if detailed:
            outputs = entry.get("outputs", {})
            print(f"\n   Outputs:")
            print(f"   {json.dumps(outputs, indent=4)}")
    
    elif node_type == "node_error":
        node_name = entry.get("node_name", "unknown")
        exec_id = entry.get("execution_id", "?")
        error = entry.get("error", {})
        timestamp = format_timestamp(entry.get("timestamp", ""))
        
        print(f"\n❌ NODE ERROR [#{exec_id}] - {node_name}")
        print(f"   Time: {timestamp}")
        print(f"   Error Type: {error.get('type', 'unknown')}")
        print(f"   Error Message: {error.get('message', 'unknown')}")
    
    elif node_type == "llm_start":
        timestamp = format_timestamp(entry.get("timestamp", ""))
        model = entry.get("model", "unknown")
        prompt_count = entry.get("prompt_count", 0)
        
        print(f"\n🤖 LLM START - {model}")
        print(f"   Time: {timestamp}")
        print(f"   Prompts: {prompt_count}")
    
    elif node_type == "llm_end":
        timestamp = format_timestamp(entry.get("timestamp", ""))
        gen_count = entry.get("generations_count", 0)
        
        print(f"\n🤖 LLM END")
        print(f"   Time: {timestamp}")
        print(f"   Generations: {gen_count}")
    
    elif node_type == "tool_start":
        tool_name = entry.get("tool_name", "unknown")
        timestamp = format_timestamp(entry.get("timestamp", ""))
        
        print(f"\n🔧 TOOL START - {tool_name}")
        print(f"   Time: {timestamp}")
        
        if detailed:
            tool_input = entry.get("input", "")
            print(f"   Input: {tool_input}")
    
    elif node_type == "tool_end":
        timestamp = format_timestamp(entry.get("timestamp", ""))
        output = entry.get("output", "")
        
        print(f"\n🔧 TOOL END")
        print(f"   Time: {timestamp}")
        
        if detailed:
            print(f"   Output: {output}")


def view_logs(log_file: str = "logs/agent_debug.jsonl", detailed: bool = False, filter_type: str = None):
    """
    View and analyze debug logs.
    
    Args:
        log_file: Path to the log file
        detailed: Show detailed input/output information
        filter_type: Filter by entry type (node_start, node_end, llm_start, etc.)
    """
    log_path = Path(log_file)
    
    if not log_path.exists():
        print(f"❌ Log file not found: {log_file}")
        return
    
    print(f"📋 Reading debug logs from: {log_file}")
    print(f"{'='*80}\n")
    
    entries: List[Dict[str, Any]] = []
    
    with open(log_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                
                # Apply filter if specified
                if filter_type and entry.get("type") != filter_type:
                    continue
                
                entries.append(entry)
                print_node_execution(entry, detailed=detailed)
                
            except json.JSONDecodeError as e:
                print(f"⚠️  Error parsing log line: {e}")
    
    print(f"\n{'='*80}")
    print(f"\n📊 Summary:")
    print(f"   Total entries: {len(entries)}")
    
    # Count by type
    type_counts = {}
    for entry in entries:
        entry_type = entry.get("type", "unknown")
        type_counts[entry_type] = type_counts.get(entry_type, 0) + 1
    
    print(f"\n   Breakdown by type:")
    for entry_type, count in sorted(type_counts.items()):
        print(f"   - {entry_type}: {count}")
    
    # Calculate total node execution time
    node_durations = [
        entry.get("duration_seconds", 0)
        for entry in entries
        if entry.get("type") == "node_end"
    ]
    
    if node_durations:
        total_time = sum(node_durations)
        avg_time = total_time / len(node_durations)
        print(f"\n   Node execution times:")
        print(f"   - Total: {total_time:.2f}s")
        print(f"   - Average: {avg_time:.2f}s")
        print(f"   - Min: {min(node_durations):.2f}s")
        print(f"   - Max: {max(node_durations):.2f}s")


def main():
    """Main entry point for the log viewer."""
    import argparse
    
    parser = argparse.ArgumentParser(description="View LangGraph debug logs")
    parser.add_argument(
        "--log-file",
        default="logs/agent_debug.jsonl",
        help="Path to the log file (default: logs/agent_debug.jsonl)"
    )
    parser.add_argument(
        "--detailed",
        action="store_true",
        help="Show detailed input/output information"
    )
    parser.add_argument(
        "--filter",
        choices=["node_start", "node_end", "node_error", "llm_start", "llm_end", "tool_start", "tool_end"],
        help="Filter by entry type"
    )
    
    args = parser.parse_args()
    
    view_logs(
        log_file=args.log_file,
        detailed=args.detailed,
        filter_type=args.filter
    )


if __name__ == "__main__":
    main()
