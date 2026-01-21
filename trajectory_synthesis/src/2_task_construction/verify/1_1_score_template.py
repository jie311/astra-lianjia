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

import os
import sys
import argparse
import json
from tqdm import tqdm
from jinja2 import Environment, FileSystemLoader, exceptions


def get_args():
    parser = argparse.ArgumentParser(description="Tool Use Question Quality Assessment Manager.")
    parser.add_argument("--input_file", type=str, required=True, help="Input JSONL file to evaluate.")
    parser.add_argument("--output_file", type=str, required=True, help="Output JSONL file for saving evaluation results.")
    # Debug Settings
    parser.add_argument('--debug', action='store_true', help="Enable debug mode: process only first few entries.")
    parser.add_argument('--debug_entries', type=int, default=10, help="Number of entries to process in debug mode.")

    return parser.parse_args()


def get_quality_check_prompt(question_data):
    """
    Generate quality assessment prompt for a given question
    """
    # Load prompt template from markdown file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    prompts_dir = os.path.join(os.path.dirname(script_dir), 'prompts')
    env = Environment(loader=FileSystemLoader(prompts_dir))
    
    template_name = 'question_quality_check.md'
    try:
        template = env.get_template(template_name).render()
    except exceptions.TemplateNotFound:
        raise FileNotFoundError(f"{template_name} template not found in prompts folder")
    
    # Extract query_info
    query_info = question_data.get('query_info', {})
    
    # Extract question content: if augmented_query_info is not empty, get query from it, otherwise get from query_info's generated_question
    augmented_query_info = query_info.get('augmented_query_info', {})
    if augmented_query_info and 'augmented_question' in augmented_query_info:
        question_content = augmented_query_info.get('augmented_question', '')
    else:
        question_content = query_info.get('generated_question', '')
    
    if not question_content:
        raise ValueError(f"No valid question content found in query_info: {question_data}")
    
    # Generate ALL_SERVER_AND_TOOL_INFORMATION from mcp_info
    all_server_tool_info = ""
    mcp_info = question_data.get('mcp_info', {})
    base_info = mcp_info.get('base_info', {})
    
    if base_info:
        group_info = base_info.get('group_info', {})
        server_name = group_info.get('server_title', 'Unknown')
        server_description = group_info.get('server_description', 'No description')
        
        # Get available tools
        tool_list = base_info.get('tool_list', [])
        tools_list = []
        for tool in tool_list:
            tool_name = tool.get('name', 'Unknown')
            tool_description = tool.get('description', '')
            if tool_description:
                tools_list.append(f"  - {tool_name}: {tool_description}")
            else:
                tools_list.append(f"  - {tool_name}")
        
        all_server_tool_info = f"Server Name: {server_name}\nDescription: {server_description}\nAll Available Tools:\n" + "\n".join(tools_list)
    else:
        all_server_tool_info = "(No MCP server information available)"
    
    # Generate INTENDED_TOOL (target tools as bullet points)
    # Get target_tools from query_info
    target_tools_raw = query_info.get('target_tools', [])
    
    # Handle different formats of target_tools
    if isinstance(target_tools_raw, list):
        target_tools = target_tools_raw
    elif isinstance(target_tools_raw, str):
        if ',' in target_tools_raw:
            target_tools = [tool.strip() for tool in target_tools_raw.split(',') if tool.strip()]
        else:
            target_tools = [target_tools_raw] if target_tools_raw.strip() else []
    else:
        target_tools = []
    
    # Format target tools as bullet points
    intended_tool_info = ""
    if target_tools:
        for target_tool in target_tools:
            intended_tool_info += f"- {target_tool}\n"
    else:
        raise ValueError(f"No target tools specified for question: {question_data}")
    
    # Replace placeholders in template
    template = template.replace("{QUESTION_CONTENT}", question_content)
    template = template.replace("{ALL_SERVER_AND_TOOL_INFORMATION}", all_server_tool_info)
    template = template.replace("{INTENDED_TOOL}", intended_tool_info.strip())
    
    return template


def main():
    args = get_args()
    print(f"Tool Use Question Quality Assessment Manager.\nArguments:\n{args}") # For logging


    if not os.path.exists(args.input_file):
        raise FileNotFoundError(f"Input file not found: {args.input_file}")

    # Create output directory if not exists
    output_dir = os.path.dirname(args.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"Processing: {os.path.basename(args.input_file)}")
    print(f"{'='*60}")

  
    input_data = []

    try:
        with open(args.input_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                try:
                    entry = json.loads(line.strip())
                    if entry:
                        input_data.append(entry)
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON on line {line_num}: {e}")
                    continue
    except Exception as e:
        print(f"Error reading input file {args.input_file}: {e}")
        raise

    print(f"Loaded {len(input_data)} entries from file")

    if len(input_data) == 0:
        print(f"Warning: No valid entries found in {args.input_file}")
        exit(0)


    if args.debug:
        # Limit to debug_entries in debug mode
        entries_to_process = min(args.debug_entries, len(input_data))
        input_data = input_data[:entries_to_process]
        print(f"Debug mode: processing only {entries_to_process} entries")

    print(f"Output will be saved to: {args.output_file}")


    results = []
    total_iterations = len(input_data)

    print(f"Generating quality assessment prompts for {total_iterations} entries...")

    for i, entry in enumerate(tqdm(input_data, desc=f"Processing {os.path.basename(args.input_file)}")):
        try:
            # Generate quality check prompt
            quality_prompt = get_quality_check_prompt(entry)
            
            # Create result entry with messages for API call
            result = {
                "messages": [
                    {
                        "role": "user",
                        "content": quality_prompt
                    }
                ]
            }
            
            # Keep all original fields (explicitly keep important fields)
            if 'query_info' in entry:
                result['query_info'] = entry['query_info']
            if 'mcp_info' in entry:
                result['mcp_info'] = entry['mcp_info']
            if 'graph' in entry:
                result['graph'] = entry['graph']
            if 'chain_info' in entry:
                result['chain_info'] = entry['chain_info']
            
            # Keep other original fields
            for key in entry.keys():
                if key not in result:  # Avoid overwriting already set fields
                    result[key] = entry[key]
            
            # Add metadata
            result['metadata'] = {
                "prompt_id": f"{i:08d}",
                "row_id": i,
                "task_type": "question_quality_assessment",
                "source_file": args.input_file
            }
            
            results.append(result)
            
        except Exception as e:
            print(f"Error processing entry {i}: {e}")
            continue

    # Save the final results
    print(f"Saving results to: {args.output_file}")
    with open(args.output_file, "w", encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"\n{'='*60}")
    print(f"✓ Saved {len(results)} entries to {args.output_file}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()