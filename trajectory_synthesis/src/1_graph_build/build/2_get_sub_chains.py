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
from typing import Dict, List
from data_loader import load_data_and_build_graph, Node, Graph
import sys
import os

# Add src directory to system path for importing utils module
# 2_get_sub_chains.py -> build -> 1_graph_build -> src
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, SRC_ROOT)
from utils.utils import sub_chain_extract_report


def get_chain(node: Node, length: int):
    """
    Get chains starting from node with specified length
    """
    chains = []
    chain = [node]

    def dfs(node, length):
        """
        Depth-first search to get chains
        """
        if length == 0:
            if chain:
                chains.append(chain[:])
            return

        for next in node.nexts:
            chain.append(next)
            dfs(next, length - 1)
            chain.pop(-1)

    dfs(node, length - 1)
    return chains


def get_chins_from_graph(graph: Graph, length: int):
    """
    Walk through graph to get chains of specified length
    """
    chains = []
    for node in graph.nodes:
        chains.extend(get_chain(node, length))
    return chains


def main(input_file: str, output_file: str, min_length: int, max_length: int):
    """
    Read data from input file, extract sub-chains, and save to output file
    """
    # Read input data
    with open(input_file, encoding="utf-8") as fin:
        data = [json.loads(line) for line in fin.readlines()]
    
    ret = []
    for jd in data:
        # Adapt to new data format: separate mcp_info and graph
        mcp_info = jd.get("mcp_info", {})
        base_info = mcp_info.get("base_info", {})
        group_info = base_info.get("group_info", {})
        
        # Get display name
        display_name = group_info.get("server_name") or group_info.get("server_title") or group_info.get("group_id", "Unknown")
        print(f"Processing: {display_name}")
        
        # Use unified data loading interface, pass complete raw data
        graph = load_data_and_build_graph(jd)
        print(f"  Graph nodes: {len(graph.nodes)}")
        
        # Extract sub-chains
        sub_chains = []
        for length in range(min_length, max_length + 1):
            plans = get_chins_from_graph(graph, length)
            for plan in plans:
                plan_names = [node.name for node in plan]
                sub_chains.append(plan_names)
        
        print(f"  Extracted {len(sub_chains)} sub-chains")
        
        # Build output item: keep mcp_info unchanged, add sub_chains to graph
        item = {
            "mcp_info": mcp_info,
            "graph": {
                **jd.get("graph", {}),  # Preserve original graph content
                "sub_chains": sub_chains  # Add sub-chains
            }
        }
        
        ret.append(item)
    
    # Write output file
    with open(output_file, "w", encoding="utf-8") as fout:
        for item in ret:
            fout.write(json.dumps(item, ensure_ascii=False) + "\n")
    
    print(f"Done! Processed {len(ret)} items and saved to {output_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract sub-chains of specified length from graph")
    parser.add_argument(
        "--input_file", 
        type=str, 
        required=True,
        help="Input JSONL file path"
    )
    parser.add_argument(
        "--output_file", 
        type=str, 
        required=True,
        help="Output JSONL file path"
    )
    parser.add_argument(
        "--min_length", 
        type=int, 
        default=2,
        help="Minimum chain length (default: 2)"
    )
    parser.add_argument(
        "--max_length", 
        type=int, 
        default=5,
        help="Maximum chain length (default: 5)"
    )
    
    args = parser.parse_args()
    main(args.input_file, args.output_file, args.min_length, args.max_length)

    sub_chain_extract_report(args.output_file)
