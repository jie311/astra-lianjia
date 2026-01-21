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

# Prompt used by vote_verify_chain.py
VERIFY_GRAPH_PROMPT = """Complete the following task as required.
I will provide you with an API Group and a generated sub-chain. Please analyze in detail whether the sub-chain I provide can form a reasonable task.
The return result should be a JSON containing four fields: is_valid, task_description, user_query, task_plan. If is_valid is false (cannot form a reasonable task), the other fields should be empty; if is_valid is true (can form a reasonable task), task_description should be a reasonable task description, user_query should be a user query generated based on task_description, and task_plan should be a reasonable task plan.

Judgment criteria:
1. The sub-chain must be able to complete a reasonable task

Notes:
1. Return format should be a JSON in the following format:
```json
{
    "is_valid": true or false,
    "task_description": "... Return task description if sub-chain is reasonable, otherwise empty",
    "user_query": "... Return user query if sub-chain is reasonable, otherwise empty",
    "task_plan": "... Return task plan if sub-chain is reasonable, otherwise empty"
}
```
2. If is_valid is true, task_description, user_query and task_plan should be described in English
3. If is_valid is true, task_plan should first analyze and reason based on user_query in natural language, then provide a reasonable task plan

API Group:
```
{api_info}
```

Sub-chain:
```
{graph_paths_str}
```
"""


GENERATE_CHAIN_FROM_QUERY_PROMPT = """You are a helpful AI assistant.
You have the following tools:
{TOOLS}

These tools are designed for the following scenery:
{SCENERY}

Given a user query, first analyze how to use the above tools to solve the query. Then, generate a toolchain that calls these tools to address the query.

The output format should be JSON and must include two fields:

plan: a description of the analysis process for solving the query.
chain: a list representing the toolchain, where each element is the name of one of the tools listed above.
Example: 
{{"plan": "your plan", "chain": ["tool1", "tool2"]}}

Input:
<Query>{query}</Query>

Output:
"""


GENERATE_QUERY_FROM_CHAIN_PROMPT = """You are a helpful AI assistant.
You have the following tools:
{TOOLS}

These tools are designed for the following scenery:
{SCENERY}

I will provide you with a tool invocation chain (i.e., the sequence and content of tool calls).
Your task is:

1. Determine whether this tool invocation chain is meaningful and valid (i.e., whether it can accomplish a reasonable task).
2. If it is meaningful, extract the original user intent or query corresponding to this chain.
3. Output the result strictly in the specified JSON format:
Example output: {{"valid": true, "query": "Check the weather in Beijing."}}
Field description:
valid: Boolean value indicating whether the chain is valid (true = valid, false = invalid).
query: String representing the user's instruction or intent; leave it as an empty string if invalid.

Please follow the above format strictly and do not include any extra explanations or text.

Input:
<ToolInvocationChain>{chain}</ToolInvocationChain>

Output:
"""
