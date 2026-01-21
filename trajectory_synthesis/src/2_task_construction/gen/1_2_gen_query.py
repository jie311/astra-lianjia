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
import argparse
import re
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '../..'))
sys.path.insert(0, SRC_ROOT)
from utils.utils import multi_call


def clean_html_comments(text):
    """
    Remove HTML comment markers (compatible with unpaired occurrences)
    """
    if not text:
        return text
    # First remove complete HTML comment blocks <!-- ... -->
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # Then clean up remaining individual symbols
    text = re.sub(r'<!--', '', text)
    text = re.sub(r'-->', '', text)
    return text.strip()


def extract_xml_content(text, tag):
    """
    Extract XML tag content
    """
    pattern = f'<{tag}>\\s*<!\\[CDATA\\[(.*?)\\]\\]>\\s*</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return clean_html_comments(match.group(1))
    pattern = f'<{tag}>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return clean_html_comments(match.group(1))
    return ""


def parse_target_tools(tools_str):
    """
    Parse tool string into list
    """
    if not tools_str:
        return []
    tools_str = tools_str.strip()
    tools_str = re.sub(r'<[^>]*>', '', tools_str)
    if ',' in tools_str:
        tools = [t.strip() for t in tools_str.split(',') if t.strip()]
    else:
        tools = [t.strip() for t in re.split(r'[\n\r]+', tools_str) if t.strip()]
    if len(tools) == 1 and ' ' not in tools[0]:
        return tools
    return [t for t in tools if t]


def parse_xml_response(response_content):
    """
    Parse XML format response content
    """
    try:
        response_match = re.search(r'<response>(.*?)</response>', response_content, re.DOTALL)
        response_xml = response_match.group(1) if response_match else response_content
        
        server_analysis = extract_xml_content(response_xml, 'server_analysis')
        target_tools_str = extract_xml_content(response_xml, 'target_tools')
        if not target_tools_str:
            target_tools_str = extract_xml_content(response_xml, 'target_tool')
        question = extract_xml_content(response_xml, 'question')
        
        if not all([server_analysis, target_tools_str, question]):
            return None
        
        target_tools = parse_target_tools(target_tools_str)
        if not target_tools:
            return None
            
        return {
            "server_analysis": server_analysis.strip(),
            "target_tools": target_tools,
            "question": question.strip()
        }
    except Exception as e:
        return None


def process_raw_output(response):
    """
    Process raw response output format
    """
    raw_output = {
        "query_info": response.get("query_info", {}),
        "mcp_info": response.get("mcp_info", {}),
        "graph": response.get("graph", {}),
        "chain_info": response.get("chain_info", {}),
        "response": response.get("response", "")
    }
    # Also save reasoning if available
    if "reasoning" in response:
        raw_output["reasoning"] = response.get("reasoning", "")
    return raw_output


def parse_response_to_result(response):
    """
    Parse response and return result
    """
    response_content = response.get("response", "")
    query_info = response.get("query_info", {})
    parsed = parse_xml_response(response_content)
    
    if not parsed:
        return None
    
    # Keep original data structure, add generated info to query_info
    updated_query_info = query_info.copy()
    updated_query_info.update({
        "server_analysis": parsed["server_analysis"],
        "target_tools": parsed["target_tools"],
        "generated_question": parsed["question"]
    })
    
    return {
        "query_info": updated_query_info,
        "mcp_info": response.get("mcp_info", {}),
        "graph": response.get("graph", {}),
        "chain_info": response.get("chain_info", {})
    }


def gen(inp_file, out_file_raw, out_file_parsed, n_sample, pool_size, model):
    """
    Generate and parse query
    """
    inp_list = []
    with open(inp_file, 'r') as f:
        for line in f:
            data = json.loads(line)
            for i in range(n_sample):
                inp_list.append(data.copy())
    
    multi_call(
        inp_list=inp_list,
        out_file_raw=out_file_raw,
        out_file_parsed=out_file_parsed,
        pool_size=pool_size,
        model=model,
        parse_func=parse_response_to_result,
        process_raw_func=process_raw_output
    )

def main():
    parser = argparse.ArgumentParser(description='Generate and parse query')
    parser.add_argument('--model', required=True, help='Model name (configured in api_config.py)')
    parser.add_argument('--inp_file', required=True, help='Input file path')
    parser.add_argument('--out_file', required=True, help='Output file path (without extension)')
    parser.add_argument('--pool_size', type=int, default=128, help='Parallelism')
    parser.add_argument('--n_sample', type=int, default=20, help='Number of samples per prompt')
    
    args = parser.parse_args()
    
    out_file_raw = f"{args.out_file}_raw.jsonl"
    out_file_parsed = f"{args.out_file}_parsed.jsonl"
    
    gen(args.inp_file, out_file_raw, out_file_parsed, args.n_sample, args.pool_size, args.model)

if __name__ == '__main__':
    main()
