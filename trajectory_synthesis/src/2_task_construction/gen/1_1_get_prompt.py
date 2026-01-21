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

import argparse
import json
import os
from jinja2 import Environment, FileSystemLoader

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROMPTS_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), 'prompts')


def get_args():
    parser = argparse.ArgumentParser(description="Tool Use Question Generation Manager.")
    parser.add_argument('--have_plan', action='store_true', help="Whether to use plan for question generation.")
    parser.add_argument('--num_tools', default=-1, type=int, help="Number of tools to use for question generation.")
    parser.add_argument('--mode', default="single_server", type=str, choices=["single_server", "multi_server"], help="Mode for question generation: single_server (tools from one server) or multi_server (tools from multiple servers).")
    parser.add_argument("--input_file", type=str, required=True, help="Input file containing MCP servers.")
    parser.add_argument("--output_file", type=str, required=True, help="Output file for generated prompts.")
    return parser.parse_args()


def load_mcp(inp_file):
    """
    Load MCP data from input file
    """
    res = []
    with open(inp_file, "r") as f:
        for line in f:
            data = json.loads(line)
            data_for_save = {
                "mcp_info": data.get("mcp_info", {}),
                "graph": data.get("graph", {}),
                "chain_info": data.get("chain_info", {})
            }
            res.append(data_for_save)
    return res


def get_seed_prompt(input, num_tools, mode="single_server", have_plan=False):
    """
    Generate prompt from unified format input
    """
    env = Environment(loader=FileSystemLoader(PROMPTS_DIR))
    
    if mode == "single_server":
        if have_plan:
            template = env.get_template('genq_by_plan.md').render()
        else:
            template = env.get_template('genq_from_tools_single_server_multi_tools.md').render()
    
        mcp_data = input
        
        # Extract info from mcp_info
        mcp_info = mcp_data.get('mcp_info', {})
        base_info = mcp_info.get('base_info', {})
        server_info = base_info.get('group_info', {})
            
        # Replace template placeholders
        server_name = server_info.get('server_title', 'Unknown Server')
        server_desc = server_info.get('server_description', 'No description available')
        template = template.replace("{MCP_SERVER_NAME}", server_name)
        template = template.replace("{MCP_SERVER_DESCRIPTION}", server_desc)
        
        # Get tool list from mcp_info
        tool_list_data = base_info.get('tool_list', [])
        
        # Get plan from chain_info.sub_chain
        plan = mcp_data.get('chain_info', {}).get('sub_chain', [])
        
        if have_plan and plan:
            template = template.replace("{NUM_TOOLS}", str(len(tool_list_data)))
            template = template.replace("{PLAN_LENGTH}", str(len(plan)))
            template = template.replace("{TOOL_CHAIN}", json.dumps(plan, ensure_ascii=False))
        else:
            template = template.replace("{NUM_TOOLS}", str(num_tools))
        
        # Build tool list
        tool_list = ""
        for i, tool in enumerate(tool_list_data, 1):
            tool_name = tool.get('name', 'Unknown Tool')
            tool_desc = tool.get('description', 'No description available')
            tool_list += f"{i}. **{tool_name}**: {tool_desc}\n"
        template = template.replace("{TOOL_LIST}", tool_list)
    return template


def get_prompts(args):
    """
    Unified processing for all input formats
    """
    mcps = load_mcp(args.input_file)
    
    with open(args.output_file, "w") as f:
        for i, mcp in enumerate(mcps):
            seed_prompt = get_seed_prompt(mcp, args.num_tools, args.mode, args.have_plan)
            
            # Build query related info
            plan = mcp.get('chain_info', {}).get('sub_chain', [])
            query_info = {
                "have_plan": args.have_plan,
                "max_tool_use": args.num_tools if not args.have_plan else -1,
                "mode": args.mode
            }
            
            # Save output according to input data format
            result = {
                "messages": [
                    {
                        "role": "user",
                        "content": seed_prompt
                    }
                ],
                "query_info": query_info,
                "mcp_info": mcp.get('mcp_info', {}),
                "graph": mcp.get('graph', {}),
                "chain_info": mcp.get('chain_info', {})
            }
            f.write(json.dumps(result, ensure_ascii=False) + "\n")
    
    print(f"Generated {len(mcps)} prompts")


if __name__ == "__main__":
    args = get_args()
    get_prompts(args)
