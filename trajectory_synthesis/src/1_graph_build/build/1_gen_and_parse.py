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

import json
import os
import argparse
import traceback
from jinja2 import Environment, FileSystemLoader
from tqdm import tqdm
import sys
from prompts.gen_chains_with_tools import tool_graph_detect_prompt

# Add src directory to system path for importing utils module
# 1_gen_and_parse.py -> build -> 1_graph_build -> src
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, SRC_ROOT)
from utils.utils import run_async_call, multi_process_async_call
from utils.api_config import API_CONFIGS
from data_loader import load_mcp_data


def _parse_tool_graph_detect(response: str):
    """
    Parse the tool graph detect from the response
    """
    answer_content = response.split("</think>")[-1].strip() if "</think>" in response else response
    res = []
    try:
        cleaned_text = answer_content.strip()
        if cleaned_text.startswith("```json"):
            cleaned_text = cleaned_text[7:]
        if cleaned_text.startswith("```"):
            cleaned_text = cleaned_text[3:]
        if cleaned_text.endswith("```"):
            cleaned_text = cleaned_text[:-3]
        cleaned_text = cleaned_text.strip()
        
        relation_json_list = json.loads(cleaned_text)
        for relation_json in relation_json_list:
            if relation_json['tool_graph_detect'] == "yes":
                res.append(relation_json)
    except Exception as e:
        traceback.print_exc()

    return res


def load_data(input_file):
    """
    Load input data, supports cases where chain is empty
    """
    data_list = []
    
    # Determine file format
    if input_file.endswith('.jsonl'):
        # JSONL format: one JSON object per line
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    data_item = json.loads(line)
                    # Use data_loader function to normalize data format
                    normalized_item = _normalize_data_item(data_item)
                    data_list.append(normalized_item)
    elif input_file.endswith('.json'):
        # JSON format: single JSON object or array
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                for data_item in data:
                    normalized_item = _normalize_data_item(data_item)
                    data_list.append(normalized_item)
            else:
                normalized_item = _normalize_data_item(data)
                data_list = [normalized_item]
    else:
        raise ValueError(f"Unsupported file format: {input_file}, only .json and .jsonl are supported")
    
    print(f"Successfully loaded {len(data_list)} records")
    return data_list


def _normalize_data_item(data_item):
    """
    Normalize data item, ensure required fields exist, chain can be empty.
    Use unified MCP data structure.
    """
    try:
        # Use load_mcp_data to extract data
        group_info, tool_list, chains = load_mcp_data(data_item)
        
        # Ensure correct types
        if not isinstance(group_info, dict):
            group_info = {}
        if not isinstance(tool_list, list):
            tool_list = []
        if not isinstance(chains, list):
            chains = []
        
        # Build normalized data structure
        normalized = {
            'group_info': group_info,
            'tool_list': tool_list,
            'graph_detect': chains
        }
        
        # Preserve other fields
        for key, value in data_item.items():
            if key not in normalized:
                normalized[key] = value
        
        return normalized
        
    except (ValueError, KeyError) as e:
        print(f"Warning: Data normalization failed ({e}), using original data")
        traceback.print_exc()
        return {
            'group_info': data_item.get('base_info', {}).get('group_info', {}),
            'tool_list': data_item.get('base_info', {}).get('tool_list', []),
            'graph_detect': data_item.get('graph_detect', []),
            **data_item
        }


def build_prompt(data_item):
    """
    Build prompt for a single data item
    """
    # Load prompt template
    # prompt_dir = os.path.join(os.path.dirname(__file__), 'prompts')
    # env = Environment(loader=FileSystemLoader(prompt_dir))
    # template = env.get_template('gen_chains_with_tools.md').render()
    template = tool_graph_detect_prompt
    # Extract group_info and tool_list
    group_info = data_item.get('group_info', {})
    tool_list = data_item.get('tool_list', [])
    
    # Format group_info and tool_list as JSON strings
    group_info_str = json.dumps(group_info, ensure_ascii=False)
    tool_list_str = "\n".join([json.dumps(tool, ensure_ascii=False) for tool in tool_list])
    
    # Replace placeholders in template
    prompt = template.replace("{group_info}", group_info_str)
    prompt = prompt.replace("{tool_list}", tool_list_str)
    
    return prompt


def prepare_inference_data(data_list):
    """
    Prepare data list for inference
    """
    inference_list = []
    
    for idx, data_item in enumerate(tqdm(data_list, desc="Preparing inference data")):
        prompt = build_prompt(data_item)
        
        inference_item = {
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "metadata": {
                "index": idx,
                "group_id": data_item.get('group_info', {}).get('group_id', ''),
                "tool_name": data_item.get('group_info', {}).get('tool_name', ''),
                "original_data": data_item
            }
        }
        inference_list.append(inference_item)
    
    return inference_list


def parse_results(raw_output_file, parsed_output_file):
    """
    Parse generation results
    """
    print(f"Starting to parse results file: {raw_output_file}")
    
    parsed_results = []
    total_chains = 0
    
    # Read all lines first to get total count
    with open(raw_output_file, 'r', encoding='utf-8') as f:
        lines = [line.strip() for line in f if line.strip()]
    
    # Use tqdm to show completed sample count
    for line in tqdm(lines, desc="Completed samples"):
        data = json.loads(line)
        
        # Get model response
        response = data.get('answer', data.get('response', ''))
        
        # Parse using _parse_tool_graph_detect
        detected_chains = _parse_tool_graph_detect(response)
        
        # Get original data
        original_data = data.get('metadata', {}).get('original_data', {})
        
        # Build result - new format: separate mcp_info and graph
        # mcp_info contains all MCP-related information
        mcp_info = {}
        
        # Add MCP-related fields (if exist)
        if 'base_info' in original_data:
            mcp_info['base_info'] = original_data['base_info']
        if 'call_info' in original_data:
            mcp_info['call_info'] = original_data['call_info']
        if 'features' in original_data:
            mcp_info['features'] = original_data['features']
        
        result = {
            "mcp_info": mcp_info,
            "graph": {
                "graph_detect": detected_chains,
                "num_chains": len(detected_chains),
                "raw_response": response
            }
        }
        
        parsed_results.append(result)
        total_chains += len(detected_chains)
    
    # Save parsed results
    with open(parsed_output_file, 'w', encoding='utf-8') as f:
        for result in parsed_results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    
    print(f"Parsing complete! Parsed {len(parsed_results)} records, detected {total_chains} tool chains")
    print(f"Results saved to: {parsed_output_file}")


def main():
    """
    Main function: Complete data loading, generation and parsing workflow
    """
    parser = argparse.ArgumentParser(description="Tool Graph Detection: Generate and Parse")
    parser.add_argument('--input_file', type=str, required=True, 
                        help='Input data file path (json or jsonl format)')
    parser.add_argument('--raw_output_file', type=str, required=True,
                        help='Raw generation results output file path')
    parser.add_argument('--parsed_output_file', type=str, required=True,
                        help='Parsed results output file path')
    parser.add_argument('--max_concurrent', type=int, default=32,
                        help='Maximum concurrency (default 32)')
    parser.add_argument('--num_processes', type=int, default=None,
                        help='Number of processes (default: CPU core count)')
    parser.add_argument('--model_name', type=str, default="Qwen3-32B",
                        help=f'Model name (options: {", ".join(API_CONFIGS.keys())})')
    
    args = parser.parse_args()
    
    # Validate model name exists
    if args.model_name not in API_CONFIGS:
        print(f"Error: Model '{args.model_name}' not found in configuration")
        print(f"Available models: {', '.join(API_CONFIGS.keys())}")
        return
    
    # Get API configuration from config file
    api_config = API_CONFIGS[args.model_name]
    print(f"Using model: {args.model_name}")
    print(f"API URL: {api_config['base_url']}")
    
    # 1. Load data
    print("\n" + "=" * 50)
    print("Step 1: Load data")
    print("=" * 50)
    data_list = load_data(args.input_file)
    
    # 2. Prepare inference data (build prompts)
    print("\n" + "=" * 50)
    print("Step 2: Build prompts")
    print("=" * 50)
    inference_list = prepare_inference_data(data_list)
    
    # Print first example data to verify prompt construction
    if inference_list:
        print("\n" + "=" * 50)
        print("Example data (first entry):")
        print("=" * 50)
        example = inference_list[0]
        print(f"Group ID: {example['metadata'].get('group_id', 'N/A')}")
        print(f"Tool Name: {example['metadata'].get('tool_name', 'N/A')}")
        print(f"\nPrompt content:\n")
        print(example['messages'][0]['content'])
        print("=" * 50 + "\n")
    
    # 3. Call API for generation
    print("\n" + "=" * 50)
    print("Step 3: Call API for generation")
    print("=" * 50)
    if os.path.exists(args.raw_output_file):
        print(f"Raw generation results file exists: {args.raw_output_file}")
        print("Skipping generation step")
    else:
        multi_process_async_call(
            inference_list, 
            args.raw_output_file, 
            api_config,
            num_processes=args.num_processes,
            max_concurrent_per_process=args.max_concurrent
        )
    
    # 4. Parse results
    print("\n" + "=" * 50)
    print("Step 4: Parse generation results")
    print("=" * 50)
    parse_results(args.raw_output_file, args.parsed_output_file)
    
    print("\n" + "=" * 50)
    print("All steps complete!")
    print("=" * 50)


if __name__ == "__main__":
    main()
