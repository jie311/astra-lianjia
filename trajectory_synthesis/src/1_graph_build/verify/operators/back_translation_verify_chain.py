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

import copy
import json
import os
import sys
import traceback
from concurrent.futures import as_completed
from concurrent.futures.thread import ThreadPoolExecutor
from typing import List, Dict, Any

from tqdm import tqdm

# Add src directory to path for importing utils module
# back_translation_verify_chain.py -> operators -> verify -> 1_graph_build -> src
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))
sys.path.insert(0, SRC_ROOT)
from utils.api_client import get_model_ans

from .prompts import GENERATE_CHAIN_FROM_QUERY_PROMPT, \
    GENERATE_QUERY_FROM_CHAIN_PROMPT


def generate_query_from_chain(scenery: str, tool_list: List, chain: List, config: Dict[str, Any], retry: int=3):
    """
    Generate query from chain
    """
    prompt = GENERATE_QUERY_FROM_CHAIN_PROMPT.format(
        TOOLS=json.dumps(tool_list, ensure_ascii=False),
        SCENERY=scenery,
        chain=json.dumps(chain, ensure_ascii=False)
    )
    
    # If preview mode, print prompt
    if config.get("preview_prompt", False):
        print(f"Operator: back_translation_verify_chain")
        print(f"Step 1: Generate query from chain")
        print(f"Chain: {chain}")
        print(f"\nFull Prompt content:")
        print("=" * 100)
        print(prompt)
        print("=" * 100)
        return None  # Preview mode returns directly

    count = 0
    while count <= retry:
        try:
            response, _ = get_model_ans(
                q=prompt,
                base_url=config["base_url"],
                api_key=config.get("api_key", ""),
                model=config["model"],
                temperature=config.get("temperature", 0.6),
                max_tokens=config.get("max_tokens", 16384),
                stream=config.get("stream", True),
                extra_body=config.get("extra_body", {})
            )
            content = response.get('content', '') if isinstance(response, dict) else str(response)
            jd = json.loads(content.strip("```").strip("json"))
            if jd["valid"]:
                return jd["query"]
            return None
        except:
            print("generate query failed\n" + traceback.format_exc())
            if count < retry:
                count += 1
                print(f"retry {count}/{retry}")
            else:
                print("All attempts failed")
                return None


def generate_chain_from_query(scenery: str, tool_list: List, query: str, chain: List, config: Dict[str, Any],
                              retry: int=3):
    """
    Generate chain from query
    """
    if not query:
        query = generate_query_from_chain(scenery, tool_list, chain, config, retry)
    if not query:  # No query generated, skip verification
        return None

    prompt = GENERATE_CHAIN_FROM_QUERY_PROMPT.format(
        SCENERY=scenery,
        TOOLS=json.dumps(tool_list, ensure_ascii=False),
        query=query
    )

    count = 0
    while count <= retry:
        try:
            response, _ = get_model_ans(
                q=prompt,
                base_url=config["base_url"],
                api_key=config.get("api_key", ""),
                model=config["model"],
                temperature=config.get("temperature", 0.6),
                max_tokens=config.get("max_tokens", 16384),
                stream=config.get("stream", True),
                extra_body=config.get("extra_body", {})
            )
            content = response.get('content', '') if isinstance(response, dict) else str(response)
            jd = json.loads(content.strip("```").strip("json"))

            chain = jd.get("chain", [])
            if not chain:
                raise Exception()
            # Validate chain correctness
            tool_names = [item["name"] for item in tool_list]
            for tool in chain:
                if tool not in tool_names:
                    raise Exception(f"{tool} in generated chain is not exist")
            jd["query"] = query
            return jd
        except:
            print("generate chain from query failed\n" + traceback.format_exc())
            if count < retry:
                count += 1
                print(f"retry {count}/{retry}")
            else:
                print("All attempts failed")
                return None


def do_verify(data: Dict[str, Any], config: Dict[str, Any], retry: int=3):
    """
    Verify chain correctness
    """
    query = data.get("query")
    group_info = data.get("mcp_info", {}).get("base_info", {}).get("group_info", {})
    tool_list = data.get("mcp_info", {}).get("base_info", {}).get("tool_list", [])
    chain = data.get("chain_info", {}).get("sub_chain", [])
    
    scenery = json.dumps(group_info, ensure_ascii=False)

    syn_jd = generate_chain_from_query(scenery, tool_list, query, chain, config, retry)
    if not syn_jd:
        verify = "fail"
        valid = False
    else:
        verify = "succeed"
        valid = True

        syn_chain = syn_jd.get("chain")

        if len(syn_chain) != len(chain):
            valid = False
        else:
            for i in range(len(syn_chain)):
                if syn_chain[i] != chain[i]:
                    valid = False
                    break
    return {"valid": valid, "verify": verify, "back_translation": syn_jd}


def back_translation_verify_score(data: Dict[str, Any], config: Dict[str, Any]) -> Dict:
    """
    Verify chain correctness; approach is to synthesize query from chain, 
    then synthesize chain from query, and compare if they match
    """
    # If preview mode, only preview prompt without execution
    if config.get("preview_prompt", False):
        # Call do_verify directly to trigger prompt printing
        do_verify(data, config, retry=0)
        return {}  # Preview mode returns empty dict
    
    models = config.pop("models")
    max_workers = config.pop("max_workers", 3)

    cfgs = []
    for model in models:
        cfg = copy.deepcopy(config)
        cfg["model"] = model
        cfgs.append(cfg)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_model = {executor.submit(do_verify, data=data, config=cfg, retry=3): cfg["model"] for cfg in cfgs}

        for future in as_completed(future_to_model):
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"thread exception: {e}\n{traceback.format_exc()}")

    verify_true = len([r for r in results if r["valid"]])
    verify_false = len([r for r in results if not r["valid"]])
    vote_valid = verify_true > verify_false
    
    # Return only operator execution results (without original data)
    return {
        "vote_valid": vote_valid,
        "back_verifies": results
    }
