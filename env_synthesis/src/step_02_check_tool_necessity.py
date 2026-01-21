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
import re
import asyncio
from typing import List, Dict, Any
import sys
import argparse
from utils.api_client import get_openai_model_ans
from utils.api_config import API_CONFIGS

from utils.logger import get_logger
from utils.prompt import PROMPT_CHECK_TOOL_NECESSITY


logger = get_logger(__name__)


def _parse_json_list(string: str) -> List[Dict]:
    """
    Parse JSON response from API into a list of dicts.
    """
    think_content = None
    string = string.strip()
    
    
    if "</think>" in string:
        think_content, sub_string = string.rsplit("</think>", 1)
        string = sub_string.strip()

    
    string = string.strip()
    if string.startswith("```json"):
        string = string[len("```json"):].strip()
    elif string.startswith("```"):
        string = string[len("```"):].strip()
    if string.endswith("```"):
        string = string[:-len("```")].strip()
    
    try:
        result = json.loads(string)
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            return [result]
        else:
            return []
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR] JSON parse error: {e}")
        logger.debug(f"[DEBUG] Raw string (first 100 chars and last 100 chars): {string[:100]}...{string[-100:]}")
        
        
        match = re.search(r"\[.*\]", string, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return []


def build_prompt(main_question: str, decomposition_trace: List[Dict]) -> str:
    """
    Build the prompt for checking tool necessity. Replaces template placeholders {{main_question}} and {{decomposition_trace}}
    """
    if not main_question or not decomposition_trace:
        raise ValueError("invalid input data——main_question or decomposition_trace is empty")

    return PROMPT_CHECK_TOOL_NECESSITY.replace("{{main_question}}", main_question).replace("{{decomposition_trace}}", json.dumps(decomposition_trace, ensure_ascii=False))


async def check_necessity(
    model_name: str,
    input_data: Dict[str, Any] = None,
    max_retries: int = 3
) -> Dict[str, Any]:
    """
    Check tool necessity for ALL traces in decomposition_trace using LLM.
    """
    if not isinstance(input_data, dict):
        logger.error(f"step 02 check_tool_necessity: invalid input data——input_data is not a dict: {input_data}")
        raise ValueError("invalid input data——input_data is not a dict")
    
    logger.info(f"check necessity for data: {input_data['uuid']}")
    
    model_config = API_CONFIGS.get(model_name)
    if not model_config:
        raise ValueError(f"model {model_name} not in API_CONFIGS")
    prompt = build_prompt(input_data.get("main_question"), input_data.get("decomposition_trace"))

    attempt = 0
    while attempt <= max_retries:
        try:
            messages = [{"role": "user", "content": prompt}]
            ans = await asyncio.to_thread(get_openai_model_ans, messages, model_config, tmp_debug=False)
            if not ans or not isinstance(ans, dict):
                raise ValueError("empty or invalid response dict")
            content = ans.get("response") or ""
            if content == "None" or not content:
                raise ValueError("empty content in response")
            parsed_res = _parse_json_list(content)

            if len(parsed_res) != len(input_data["decomposition_trace"]):
                raise ValueError(f"result length mismatch——parsed_res length({len(parsed_res)}) != input_data['decomposition_trace'] length({len(input_data['decomposition_trace'])})")

            
            for idx, item in enumerate(parsed_res):
                if item.get("_uuid") == input_data["decomposition_trace"][idx].get("_uuid"):
                    input_data["decomposition_trace"][idx]["tool_necessity"] = bool(item.get("tool_necessity"))
                    input_data["decomposition_trace"][idx]["reason"] = item.get("reason")
                else:
                    raise ValueError(f"result uuid mismatch——parsed_res uuid({item.get('_uuid')}) != input_data['decomposition_trace'] uuid({input_data['decomposition_trace'][idx].get('_uuid')})")

            input_data["tool_necessity_legitimacy"] = True

            non_leaf_uuids = set()
            for trace_item in input_data["decomposition_trace"]:
                deps = trace_item.get("dependency") or []
                if isinstance(deps, list):
                    non_leaf_uuids.update(deps)
            for trace_item in input_data["decomposition_trace"]:
                if trace_item.get("_uuid") in non_leaf_uuids:
                    if not bool(trace_item.get("tool_necessity")):
                        input_data["tool_necessity_legitimacy"] = False
                        break
            logger.info(f"check necessity for data {input_data['uuid']} done")
            return input_data

        except Exception as e:
            attempt += 1
            if attempt > max_retries:
                logger.error(f"check_necessity failed after {max_retries} retries: {e}")
                logger.info(f"check necessity for data {input_data['uuid']} failed")
                input_data["tool_necessity_legitimacy"] = False
                return input_data

            await asyncio.sleep(5)


def main():
    import os
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--model_name", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    args = parser.parse_args() 
    input_file = args.input_file
    model_name = args.model_name
    output_file = args.output_file

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    data = json.loads(lines[0])
    res = asyncio.run(check_necessity(model_name, data))
    print(res)
    
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
