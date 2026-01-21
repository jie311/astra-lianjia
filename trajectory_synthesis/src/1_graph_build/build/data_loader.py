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
from typing import Dict, List


class Tool:
    def __init__(self, jd: Dict):
        self.name = jd["name"]
        self.jd = jd


class Node:
    def __init__(self, tool: Tool, nexts: List['Node'] = None):
        self.tool = tool
        self.nexts = nexts or []
        self.next_map = {next.name: next for next in self.nexts}

    @property
    def name(self):
        return self.tool.name

    def add_next(self, node: 'Node'):
        if node.name not in self.next_map:
            self.nexts.append(node)
            self.next_map[node.name] = node


class Graph:
    def __init__(
        self,
        group_name: str,
        tool_name: str,
        nodes: List[Node] = None,
        group_info: Dict = None,
        tool_list: List[Dict] = None
    ):
        self.group_name = group_name
        self.tool_name = tool_name
        self.nodes = nodes or []
        self.group_info = group_info or {}
        self.tool_list = tool_list or []


def build_graph(group_info: Dict, tool_list: List[Dict], chains: List[str]):
    """
    Build graph from group_info, tool_list and chains
    """
    nodes = {}
    for tool_jd in tool_list:
        tool = Tool(jd=tool_jd)
        nodes[tool.name] = Node(tool=tool)
    for chain in chains:
        last_node = None
        for tool_name in chain["tool_graph_detect_chain"]:
            cur_node = nodes.get(tool_name, None)
            if cur_node is None:
                print(f"Tool {tool_name} not found in nodes")
                print(nodes.keys())
                continue
            if last_node:
                last_node.add_next(cur_node)
            last_node = cur_node

    group_name = (
        group_info.get("name")
        or group_info.get("server_title")
        or group_info.get("server_name")
        or group_info.get("group_id")
        or "Unknown"
    )
    tool_name = (
        group_info.get("tool_name")
        or group_info.get("server_name")
        or group_info.get("server_title")
        or group_name
    )

    graph = Graph(
        group_name,
        tool_name,
        list(nodes.values()),
        group_info=group_info,
        tool_list=tool_list
    )
    return graph


def load_mcp_data(data: Dict) -> tuple[Dict, List[Dict], List[Dict]]:
    """
    Extract group_info, tool_list and chains from MCP format data
    """
    # Support both new and old formats
    # New format: mcp_info.base_info and graph.graph_detect
    # Old format: base_info and graph_detect directly at top level
    
    if "mcp_info" in data:
        # New format
        mcp_info = data.get("mcp_info", {})
        base_info = mcp_info.get("base_info", {})
        group_info = base_info.get("group_info", {})
        tool_list = base_info.get("tool_list", [])
        graph_data = data.get("graph", {})
        graph_detect = graph_data.get("graph_detect", [])
    else:
        # Old format (backward compatible)
        base_info = data.get("base_info", {})
        group_info = base_info.get("group_info", {})
        tool_list = base_info.get("tool_list", [])
        graph_detect = data.get("graph_detect", [])
    
    # Extract chains (keep complete chain object)
    chains = []
    for item in graph_detect:
        if not isinstance(item, dict):
            continue
        if "new_chain" in item:
            # If has new_chain, wrap into standard format
            chains.append({"tool_graph_detect_chain": item["new_chain"]})
        elif "error_info" in item and item["error_info"] != "1":
            continue
        elif "tool_graph_detect_chain" in item:
            # Keep complete chain object
            chains.append(item)
    
    return group_info, tool_list, chains


def load_data_and_build_graph(data: Dict) -> Graph:
    """
    Load data from MCP format and build Graph
    """
    group_info, tool_list, chains = load_mcp_data(data)
    graph = build_graph(group_info, tool_list, chains)
    return graph


