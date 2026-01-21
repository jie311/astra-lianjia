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

tool_graph_detect_prompt = """
You are a helpful assistant that can detect dependency relationships between tools.
You wiil be given a group json document with group description.
You will be given a tool list json document with tool description and parameter decription.
You need to detect dependency relationships between tools and output a chain of tools and possible task or scenario can solve by the chain of tools.
- If you must call tool1 before call tool2, for example: tool1 to get data, and then you can call tool2 to process the data, they are dependency related.
- If you can call tool1 and tool2 directly, they are not related.
- If you are not sure about the relationship, do not output anything.
- Some Group may have multiple tasks, you can output multiple chains for each task.

if multiple chains are detected, output a list of chains.
each chain must in json format with tool_graph_detect field, only "yes" or "no" or "not sure" is allowed.

OutputExample:
[{"tool_graph_detect": "yes", "tool_graph_detect_chain": ["login_account", "check_balance", "buy_stock"], "tool_graph_detect_task": "buy 1000 shares of nvda stock"},...]
[{"tool_graph_detect": "no", "tool_graph_detect_chain": [], "tool_graph_detect_task": ""},...]
[{"tool_graph_detect": "not sure", "tool_graph_detect_chain": [], "tool_graph_detect_task": ""},...]

Output the result in json format with tool_graph_detect field, only "yes" or "no" or "not sure" is allowed.
tool_graph_detect_chain is a list of tool names.
tool_graph_detect_task is a string of the task or scenario can solve by the chain of tools.


Input:
<GroupInfo>{group_info}</GroupInfo>
<ToolList>{tool_list}</ToolList>

Output:
"""