# Copyright 2025-2026 Beike Language and Intelligence (BLI).
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
import base64
import json
import re
import signal
import atexit
import concurrent.futures
import argparse
import traceback
import sys
from pathlib import Path
from typing import List, Dict, Any
import nest_asyncio
from wrapt_timeout_decorator import timeout
from qwen_agent.tools.mcp_manager import MCPManager
from qwen_agent.agents import Assistant
import os

SRC_ROOT = Path(__file__).resolve().parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
from utils.api_config import API_CONFIGS

nest_asyncio.apply()


def cleanup_mcp_resources():
    """
    Clean up MCP resources
    """
    try:
        if MCPManager._instance is not None:
            MCPManager().shutdown()
    except Exception:
        pass


def signal_handler(signum, frame):
    """
    Signal handler
    """
    cleanup_mcp_resources()
    exit(0)


atexit.register(cleanup_mcp_resources)
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, required=True, help="Input file")
    parser.add_argument("--output_file", type=str, required=True, help="Output file")
    parser.add_argument("--model_name", type=str, required=True, help="Model name")
    parser.add_argument("--smithery_api_key", type=str, default="", help="Smithery API key")
    parser.add_argument("--smithery_profile", type=str, default="", help="Smithery Profile")
    parser.add_argument("--max_workers", type=int, default=4, help="Number of parallel workers")
    parser.add_argument("--timeout", type=int, default=90, help="Single task timeout (seconds)")
    parser.add_argument("--system_prompt", type=str, default="", help="System prompt")
    return parser.parse_args()


args = get_args()

if args.model_name not in API_CONFIGS:
    raise ValueError(f"Configuration for model '{args.model_name}' not found. Available models: {list(API_CONFIGS.keys())}")
model_config = API_CONFIGS[args.model_name]


def extract_query(query_info: Dict) -> str:
    """
    Extract query from query_info
    """
    augmented_query_info = query_info.get("augmented_query_info", {})
    
    # If augmented_query_info is empty or doesn't exist, get from generated_question
    if not augmented_query_info or not augmented_query_info.get("augmented_question"):
        query = query_info.get("generated_question", "")
    else:
        # Otherwise get from augmented_question
        query = augmented_query_info.get("augmented_question", "")
    
    # Remove leading and trailing <xxx></xxx> tags
    query = query.strip()
    match = re.match(r'^<(\w+)>(.*)</\1>$', query, re.DOTALL)
    if match:
        query = match.group(2).strip()
    
    return query


def is_aistudio_mcp(call_info: Dict) -> bool:
    """
    Check if MCP is from aistudio (by headers field)
    """
    return "headers" in call_info


def build_smithery_mcp_url(call_info: Dict, api_key: str, profile: str) -> str:
    """
    Build Smithery MCP server URL
    """
    url = call_info.get('python_sdk_url', '')
    if not url:
        return None
    
    config = call_info.get('python_sdk_config', '')
    if isinstance(config, str):
        config = json.loads(config) if config else {}
    elif not isinstance(config, dict):
        config = {}
    
    config_b64 = base64.b64encode(json.dumps(config).encode()).decode()
    
    url = url.replace("{config_b64}", config_b64)
    url = url.replace("{smithery_api_key}", api_key)
    url = url.replace("{smithery_profile}", profile)
    
    if profile and "profile=" not in url:
        url += f"&profile={profile}"
    
    return url


def create_agent(mcp_info: Dict, model_cfg: Dict, args: argparse.Namespace) -> Assistant:
    """
    Create Qwen Agent
    """
    llm_cfg = {
        'model': model_cfg['model'],
        'model_server': model_cfg['base_url'],
        'api_key': model_cfg['api_key'],
        "model_type": model_cfg.get('model_type', ''),
        "stream": model_cfg.get('stream', True),
        'generate_cfg': {
            'max_retries': model_cfg.get('max_retries', 2),
            'fncall_prompt_type': model_cfg.get('fncall_prompt_type', 'nous'),
            'parallel_function_calls': model_cfg.get('parallel_function_calls', False),
            'extra_body': model_cfg.get('extra_body', {}),
        }
    }
    base_info = mcp_info.get("base_info", {})
    call_info = mcp_info.get("call_info", {})
    group_info = base_info.get("group_info", {})
    server_name = group_info.get("server_name", "unknown")
    safe_server_name = server_name.replace(' ', '-').lower()
    tool_list = base_info.get("tool_list",[])

    if "mock_tool" not in call_info:
        if is_aistudio_mcp(call_info):
            mcp_config = {
                safe_server_name: {
                    "url": call_info.get("url", ""),
                    "headers": call_info.get("headers", {}),
                    "type": "streamable-http",
                    "sse_read_timeout": 30
                }
            }
        else:
            url = build_smithery_mcp_url(call_info, args.smithery_api_key, args.smithery_profile)
            
            if not url:
                return None
            
            mcp_config = {
                safe_server_name: {
                    "url": url,
                    "type": "streamable-http",
                    "sse_read_timeout": 300
                }
            }
        tools = [{"mcpServers": mcp_config, "tool_list": tool_list}]    
    else:
        server_description = base_info.get("group_info", {}).get("server_description", "")
        tools = [{"mock_tool": True, "tool_list": tool_list, "server_description": server_description}]

    
    assistant = Assistant(llm=llm_cfg, function_list=tools)  
    return assistant


async def process_item_async(query: str, mcp_info: Dict, model_cfg: Dict, args: argparse.Namespace, system_prompt: str = "") -> List[Dict]:
    """
    Async process single task
    """
    agent = create_agent(mcp_info, model_cfg, args)
    if not agent:
        raise ValueError("Failed to create agent")
    
    # Build messages
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": query})
    
    # Run agent
    try:
        responses = None
        for responses in agent.run(messages=messages):
            pass
        
        if not responses:
            raise ValueError("Agent returned empty response")
    except Exception as e:
        print("Agent run failed: ", e)
        traceback.print_exc()
    
    return messages + responses


@timeout(args.timeout, use_signals=False)
def process_item(item: Dict, model_cfg: Dict, args: argparse.Namespace) -> Dict:
    """
    Process single task with timeout
    """
    trajectory = []
    try:
        # Extract query
        query_info = item.get("query_info", {})
        query = extract_query(query_info)
        
        # Extract mcp_info
        mcp_info = item.get("mcp_info", {})
        
        # Async execution
        trajectory = asyncio.run(process_item_async(query, mcp_info, model_cfg, args, args.system_prompt))
        
        # Save output to trajectory field, keep other data
        item["trajectory"] = trajectory
        
        return item
    except Exception as e:
        # Add error info to trajectory on failure
        error_message = {
            "role": "assistant",
            "content": f"[ERROR: {str(e)}]"
        }
        trajectory.append(error_message)
        item["trajectory"] = trajectory
        return item


def process_items_parallel(items: List[Dict], model_cfg: Dict, args: argparse.Namespace, output_file) -> List[Dict]:
    """
    Process multiple tasks in parallel and write results in real-time
    """
    results = [None] * len(items)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_to_idx = {
            executor.submit(process_item, item, model_cfg, args): idx 
            for idx, item in enumerate(items)
        }

        for future in concurrent.futures.as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
                print(f"✅ Task {idx} completed")
            except Exception as e:
                print(f"❌ Task {idx} failed: {e}")
                results[idx] = items[idx]
                results[idx]["trajectory"] = [{"role": "assistant", "content": f"[ERROR: {str(e)}]"}]
            
            output_file.write(json.dumps(results[idx], ensure_ascii=False) + "\n")
            output_file.flush()
    

def load_data(args: argparse.Namespace) -> List[Dict]:
    """
    Load input data
    """
    items = []
    query_set = set()
    cnt_processed = 0
    if os.path.exists(args.output_file):
        with open(args.output_file, "r") as f:
            for line in f:
                data_line = json.loads(line)
                query = extract_query(data_line.get("query_info", {}))
                query_set.add(query)
                cnt_processed += 1
    cnt = 0
    with open(args.input_file, "r") as f:
        for line in f:
            data_line = json.loads(line)
            query = extract_query(data_line.get("query_info", {}))
            if query not in query_set:
                items.append(data_line)
            cnt += 1
    print("Original data count: ", cnt)
    print("Unprocessed data count: ", len(items))
    print("Processed data count: ", cnt_processed)
    return items


def main():
    items = load_data(args)
    try:
        total_items = len(items)
        print(f"🚀 Starting to process {total_items} tasks")
        print(f"⚙️  Model: {model_config['model']}")
        print(f"⚙️  Workers: {args.max_workers}, Timeout: {args.timeout}")
        
        with open(args.output_file, "a") as output_f:
            process_items_parallel(items, model_config, args, output_f)
                
        print(f"💾 Results saved to {args.output_file}")
        
    finally:
        cleanup_mcp_resources()


if __name__ == "__main__":
    main()
