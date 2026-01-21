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
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from collections import Counter

# Add src directory to path for importing utils module
# vote_verify_chain.py -> operators -> verify -> 1_graph_build -> src
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, SRC_ROOT)
from utils.api_client import get_model_ans as _get_model_ans

from .prompts import VERIFY_GRAPH_PROMPT
# from prompts import VERIFY_GRAPH_PROMPT


def get_model_ans(text: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call model API to get answer (wrapper for api_client.get_model_ans)
    """
    try:
        n_samples = config.get('n_samples', 1)
        ans_list = []
        
        for _ in range(n_samples):
            response, _ = _get_model_ans(
                q=text,
                base_url=config["base_url"],
                api_key=config.get("api_key", ""),
                model=config["model"],
                temperature=config.get("temperature", 0.6),
                max_tokens=config.get("max_tokens", 16384),
                stream=config.get("stream", True),
                extra_body=config.get("extra_body", {})
            )
            content = response.get('content', '') if isinstance(response, dict) else str(response)
            ans_list.append([content, {"message": {"content": content}}])
        
        return {
            "answers": ans_list,
            "usage": {}
        }
        
    except Exception as e:
        print(f"API call error: {e}")
        return {
            "answers": [],
            "usage": {},
            "error": str(e)
        }


def generate_prompt(api_dict: Dict, graph_dict: Dict) -> str:
    """
    Generate prompt based on api and graph information
    """
    api_info = json.dumps(api_dict, ensure_ascii=False)
    graph_paths_str = json.dumps(graph_dict, ensure_ascii=False)
    return VERIFY_GRAPH_PROMPT.replace('{api_info}', api_info).replace('{graph_paths_str}', graph_paths_str)


def vote_answers(answers: List) -> Dict[str, Any]:
    """
    Vote on multiple model answers
    """
    # Initialize vote counts
    vote_true_count = 0
    vote_false_count = 0
    parse_error_count = 0
    
    # Store successfully parsed answers
    valid_true_answers: List[tuple] = []  # (index, parsed_json)
    valid_false_answers: List[tuple] = []  # (index, parsed_json)
    
    # Iterate through all answers for voting
    for idx, answer_item in enumerate(answers):
        answer_text = answer_item[0] if isinstance(answer_item, list) and len(answer_item) > 0 else ""
        print(answer_text)
        if "<think>" in answer_text or "</think>" in answer_text:
            answer_text = answer_text.split("</think>")[1]
        try:
            # Try to parse JSON, clean possible markdown markers
            cleaned_text = answer_text.strip()
            if cleaned_text.startswith("```json"):
                cleaned_text = cleaned_text[7:]
            if cleaned_text.startswith("```"):
                cleaned_text = cleaned_text[3:]
            if cleaned_text.endswith("```"):
                cleaned_text = cleaned_text[:-3]
            cleaned_text = cleaned_text.strip()
            
            parsed = json.loads(cleaned_text)
            
            # Extract is_valid field
            is_valid = parsed.get("is_valid", False)
            
            if is_valid:
                vote_true_count += 1
                valid_true_answers.append((idx, parsed))
            else:
                vote_false_count += 1
                valid_false_answers.append((idx, parsed))
                
        except (json.JSONDecodeError, AttributeError, TypeError) as e:
            # Parse failed
            parse_error_count += 1
            continue
    
    # Determine final answer based on voting results
    final_is_valid = vote_true_count > vote_false_count
    
    # Build voting result
    vote_result = {
        "is_valid": final_is_valid,
        "task_description": "",
        "user_query": "",
        "task_plan": "",
        "vote_count": {
            "true": vote_true_count,
            "false": vote_false_count,
            "parse_error": parse_error_count
        },
        "selected_answer_index": None
    }
    
    # If voting result is true, select an answer with is_valid=true
    if final_is_valid and len(valid_true_answers) > 0:
        # Select the first answer with is_valid=true
        selected_idx, selected_answer = valid_true_answers[0]
        vote_result["task_description"] = selected_answer.get("task_description", "")
        vote_result["user_query"] = selected_answer.get("user_query", "")
        vote_result["task_plan"] = selected_answer.get("task_plan", "")
        vote_result["selected_answer_index"] = selected_idx
    
    return vote_result


def get_vote_score(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Complete workflow for processing single data: generate prompt -> call model -> vote summary
    """
    # 1. Extract information from new data format
    group_info = data.get("mcp_info", {}).get("base_info", {}).get("group_info", {})
    tool_list = data.get("mcp_info", {}).get("base_info", {}).get("tool_list", [])
    sub_chain = data.get("chain_info", {}).get("sub_chain", [])
    
    # 2. Generate prompt
    api = {"group_info": group_info, "tool_list": tool_list}
    prompt = generate_prompt(api, sub_chain)
    
    # If preview mode, print prompt and return empty result
    if config.get("preview_prompt", False):
        print(f"Operator: vote_verify_chain")
        print(f"Sub-chain: {sub_chain}")
        print(f"\nFull Prompt content:")
        print("=" * 100)
        print(prompt)
        print("=" * 100)
        return {}  # Preview mode returns empty dict
    
    # 3. Call model to get multiple answers
    model_response = get_model_ans(prompt, config=config)
    
    # 4. Vote on answers
    vote_result = vote_answers(model_response['answers'])
    
    # 5. Return only operator execution results (without original data)
    return {
        "vote_verify": model_response,
        "vote_result": vote_result
    }

