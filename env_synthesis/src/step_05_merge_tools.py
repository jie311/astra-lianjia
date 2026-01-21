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
import asyncio
import sys
import random
import time
from typing import List, Dict, Any, Optional, Tuple
from copy import deepcopy
import requests
import ast
import argparse
from utils.api_config import API_CONFIGS,API_MAX_RETRY_TIMES, API_RETRY_SLEEP_TIME,SANDBOX_URL
from utils.api_client import get_openai_model_ans

from utils.prompt import PROMPT_MERGE_INTENT_AGGREGATION, PROMPT_MERGE_TOOLS_CODE, PROMPT_MERGE_TOOL_CALL_GEN
from utils.logger import get_logger


logger = get_logger(__name__)


def _parse_json_list_intent_aggregation(string: str) -> List[Dict]:
    """
    Parse the JSON response from LLM API for intent aggregation.
    
    Processing steps:
    1. Remove </think> tags and content before it
    2. Remove markdown code block tags (```json or ```)
    3. Parse and return the JSON object
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
            if len(result) > 0:
                return result[0]
            else:
                raise ValueError(f"Unexpected JSON type: {type(result)}")
        elif isinstance(result, dict):
            return result
        else:
            logger.warning(f"[WARNING] merge_intent_aggregation Unexpected JSON type: {type(result)}")
            return []
    except json.JSONDecodeError as e:
        logger.error(f"[ERROR]merge_intent_aggregation JSON parse error: {e}")
        logger.debug(f"[DEBUG] merge_intent_aggregation Raw string (first 100 chars and last 100 chars): {string[:100]}...{string[-100:]}")


def build_prompt_intent_aggregation(input_data: Dict[str, Any]) -> str:
    """
    Build the prompt for intent aggregation from decomposition trace.
    
    Extracts sub-questions from decomposition_trace and formats them
    into a prompt for LLM to cluster by intent similarity.
    """
    q_list = [{
        "_uuid": item["_uuid"],
        "question": item["sub_question"],
        "answer": item["sub_answer"],
        "function_implementation": {},
    } for item in input_data["decomposition_trace"]]

    
    prompt = PROMPT_MERGE_INTENT_AGGREGATION.replace("{{questions}}", json.dumps(q_list, ensure_ascii=False))
    return prompt


async def intent_aggregation(
    model_name: str,
    input_data: Dict[str, Any] = None,
    max_retries: int = API_MAX_RETRY_TIMES,
    base_delay: float = API_RETRY_SLEEP_TIME
) -> Dict:
    """
    Cluster sub-questions by intent similarity using LLM.
    
    Calls LLM to analyze decomposition trace and group sub-questions
    that share similar intents into clusters for potential code merging.
    """
    model_config = API_CONFIGS.get(model_name)
    if not model_config:
        raise ValueError(f"model {model_name} not in API_CONFIGS")
    
    if not isinstance(input_data, dict):
        raise ValueError("invalid input data——input_data is not a dict")
    prompt = build_prompt_intent_aggregation(input_data)
    input_message = [
        {"role":"user", "content":prompt}
    ]
    attempt = 0
    while attempt <= max_retries:
        try:
            ans = await asyncio.to_thread(get_openai_model_ans, input_message, model_config, tmp_debug=False)
            if not ans or not isinstance(ans, dict):
                raise ValueError("empty or invalid response dict")
            content = ans.get("response") or ""
            if content == "None" or not content:
                raise ValueError("empty content in response")
            parsed_res = _parse_json_list_intent_aggregation(content)
            parsed_res = {
                "uuid": input_data["uuid"],
                **parsed_res
            }
            
            num_clusters = len(parsed_res.get("clusters", []))
            logger.info(f"Intent aggregation completed for uuid={input_data['uuid']}, found {num_clusters} clusters")
            return parsed_res

        except Exception as e:
            last_err = e
            attempt += 1
            if attempt > max_retries:
                logger.error(f"Intent aggregation failed after {max_retries} retries for uuid={input_data['uuid']}")
                parsed_res = {
                    "uuid": input_data["uuid"],
                    "clusters": []
                }
                return parsed_res

            delay = base_delay * (1.5 ** (attempt - 1))
            delay = delay + random.uniform(0, delay * 0.1)
            await asyncio.sleep(delay)


def get_code_sandbox_ans(code):
    """
    Execute Python code in a remote sandbox environment.
    
    Sends code to a remote code execution service and returns the result.
    """
    input_dict = \
        {
            "code": code,
            "language": "python"
        }
    response = requests.post(SANDBOX_URL, json=input_dict)
    return response.json()


def extract_qa_code_by_uuids(data_dict, sub_uuids):
    """
    Extract QA pairs and code information for specified uuids from data_dict.
    
    Looks up each uuid in env_result and extracts the corresponding
    question, answer, code, tool information for merging.
    """

    env_result = data_dict.get("env_result", [])
    decomposition_trace = data_dict.get("decomposition_trace", [])
    
    
    if isinstance(env_result, dict):
        return _extract_from_dict_env_result(env_result, sub_uuids)
    else:
        logger.warning(f"Warning: env_result format not supported: {type(env_result)}")
        return []


def _extract_from_dict_env_result(env_result, sub_uuids):
    """
    Extract QA and code data from dictionary-format env_result.
    """
    qa_code_list = []
    for uuid in sub_uuids:
        env = env_result.get(str(uuid)) or env_result.get(int(uuid) if str(uuid).isdigit() else None)
        if env is None:
            logger.warning(f"Warning: data not found for _uuid={uuid}")
            continue
        
        question = env.get("question", "")
        answer = env.get("answer", "")
        
        
        env_synthesis = env.get("env_synthesis_result", {})
        data_section = env_synthesis.get("data", {})
        code = data_section.get("code", "")
        tool_name = data_section.get("tool_document", {}).get("name", "")
        tool_document = data_section.get("tool_document", {})
        tool_call_statement = data_section.get("tool_call_statement", "")
        
        qa_code_list.append({
            "_uuid": uuid,
            "question": question,
            "answer": answer,
            "code": code,
            "tool_name": tool_name,
            "tool_document": tool_document,
            "tool_call_statement": tool_call_statement
        })
    
    return qa_code_list


def _extract_first_function_signature(code: str) -> Tuple[Optional[str], List[str]]:
    """
    Extract the function name and parameter names of the first function definition in the code (only the parameter names, without the specific expansion of *args/**kwargs)
    """
    try:
        tree = ast.parse(code)
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                arg_names: List[str] = []
                for a in getattr(node.args, "posonlyargs", []):
                    arg_names.append(a.arg)
                for a in node.args.args:
                    arg_names.append(a.arg)
                if node.args.vararg:
                    arg_names.append(node.args.vararg.arg)
                for a in node.args.kwonlyargs:
                    arg_names.append(a.arg)
                if node.args.kwarg:
                    arg_names.append(node.args.kwarg.arg)
                return node.name, arg_names
    except Exception:
        pass
    return None, []


def _strip_code_fences(text: str) -> str:
    """
    Strip markdown code fences and think tags from LLM response.
    
    Removes </think> tags, ```python and ``` markers to extract clean code.
    """
    text = (text or "").strip()
    if "</think>" in text:
        text = text.split("</think>", 1)[-1].strip()
    if text.startswith("```python"):
        text = text[len("```python"):].strip()
    if text.startswith("```"):
        text = text[3:].strip()
    if text.endswith("```"):
        text = text[:-3].strip()
    return text


def _extract_json_obj(text: str) -> Optional[Any]:
    """
    Try to extract JSON from the model output (supports text/code blocks before and after)
    """
    if not text:
        return None
    s = _strip_code_fences(text)
    
    try:
        return json.loads(s)
    except Exception:
        pass
    
    start_candidates = []
    for ch in ("[", "{"):
        idx = s.find(ch)
        if idx != -1:
            start_candidates.append(idx)
    if not start_candidates:
        return None
    start = min(start_candidates)
    
    end = max(s.rfind("]"), s.rfind("}"))
    if end == -1 or end <= start:
        return None
    snippet = s[start:end + 1]
    try:
        return json.loads(snippet)
    except Exception:
        return None


def _normalize_tool_call_statement(stmt: str) -> str:
    """
    Normalize the tool_call_statement: ensure it is a "function call expression", do not include print(...)
    """
    s = (stmt or "").strip()
    if s.startswith("print(") and s.endswith(")"):
        inner = s[len("print("):-1].strip()
        if inner:
            return inner
    return s


def create_patch_mock_prompt(base_code: str, qa_list: List[Dict[str, Any]], intent_summary: str = "") -> str:
    """
    Given a code + multiple QA, let the model only modify the "mock data/Mock data" part, ensuring that the call of each QA returns an output containing the corresponding answer.
    """
    fn_name, arg_names = _extract_first_function_signature(base_code)
    fn_hint = f"{fn_name}({', '.join(arg_names)})" if fn_name else "(unable to parse function signature)"

    qa_parts = []
    for i, item in enumerate(qa_list, 1):
        qa_parts.append(
            f"""### instance {i}
                question: {item.get("question", "")}
                answer(need to appear as a substring of the return value): {item.get("answer", "")}
                tool_call_statement: {item.get("tool_call_statement", "")}
                """
        )
    qa_section = "\n".join(qa_parts)

    intent_line = f"tool intent: {intent_summary}" if intent_summary else ""
    return PROMPT_MERGE_TOOLS_CODE.format(intent_line=intent_line, fn_hint=fn_hint, qa_section=qa_section, base_code=base_code)


def create_tool_call_gen_prompt(code: str, qa_list: List[Dict[str, Any]]) -> str:
    """
    Create prompt for generating tool call statements for each QA.
    
    Builds a prompt that asks LLM to generate appropriate function call
    statements for each QA pair based on the merged code.
    """
    fn_name, arg_names = _extract_first_function_signature(code)
    fn_name = fn_name or "FUNCTION_NAME_UNKNOWN"
    arg_list = ", ".join(arg_names) if arg_names else ""

    qa_parts = []
    for i, item in enumerate(qa_list, 1):
        qa_parts.append(
            f"""### QA {i}
            _uuid: {item.get("_uuid")}
            question: {item.get("question", "")}
            answer: {item.get("answer", "")}
            """
            )
    qa_section = "\n".join(qa_parts)

    return PROMPT_MERGE_TOOL_CALL_GEN.format(fn_name=fn_name, arg_list=arg_list, qa_section=qa_section, code=code)


def generate_tool_call_statements(code: str, qa_list: List[Dict[str, Any]], config: Dict[str, Any]) -> Dict[Any, str]:
    """
    Generate tool_call_statement for each QA using LLM.
    
    Calls LLM to generate appropriate function call statements that will
    produce the expected answers when executed with the merged code.
    """
    prompt = create_tool_call_gen_prompt(code, qa_list)
    input_messages = [{"role": "user", "content": prompt}]
    result = get_openai_model_ans(input_messages, config, False)
    resp = result.get("response", "")
    obj = _extract_json_obj(resp)
    mapping: Dict[Any, str] = {}
    if isinstance(obj, list):
        for it in obj:
            if not isinstance(it, dict):
                continue
            uuid = it.get("_uuid")
            stmt = _normalize_tool_call_statement(it.get("tool_call_statement", ""))
            if uuid is None or not stmt:
                continue
            
            uuid_key: Any = uuid
            if isinstance(uuid, str) and uuid.isdigit():
                try:
                    uuid_key = int(uuid)
                except Exception:
                    uuid_key = uuid
            mapping[uuid_key] = stmt
            # Bidirectional mapping to avoid int/str type mismatch lookup failures
            if isinstance(uuid_key, int):
                mapping[str(uuid_key)] = stmt
            elif isinstance(uuid_key, str) and uuid_key.isdigit():
                try:
                    mapping[int(uuid_key)] = stmt
                except Exception:
                    pass
    return mapping


def verify_merged_code(merged_code, qa_code_list):
    """
    Verify that the merged code can correctly handle all test cases
    Note: No longer replace function names through regular expressions; external provision of correct tool_call_statement is required
    """
    test_results = []
    all_passed = True
    modified_tool_calls = {}  
    has_actual_test = False  
    
    for item in qa_code_list:
        question = item["question"]
        answer = item["answer"]
        tool_call_statement = _normalize_tool_call_statement(item.get("tool_call_statement", ""))
        uuid = item["_uuid"]
        
        if not tool_call_statement:
            test_results.append({
                "uuid": uuid,
                "status": "skipped",
                "reason": "No tool_call_statement"
            })
            modified_tool_calls[uuid] = tool_call_statement
            all_passed = False  
            continue

        
        modified_tool_calls[uuid] = tool_call_statement
        has_actual_test = True  
        
        
        final_code = f"{merged_code}\nprint({tool_call_statement})"
        
        try:
            
            call_ans = get_code_sandbox_ans(final_code)
            
            if call_ans["status"] == "Success":
                stdout = call_ans.get("run_result", {}).get("stdout", "")
                
                if answer in stdout:
                    test_results.append({
                        "uuid": uuid,
                        "status": "passed",
                        "stdout": stdout  
                    })
                else:
                    all_passed = False
                    test_results.append({
                        "uuid": uuid,
                        "status": "failed",
                        "reason": f"Answer '{answer}' not in stdout",
                        "stdout": stdout
                    })
            else:
                all_passed = False
                test_results.append({
                    "uuid": uuid,
                    "status": "error",
                    "error": call_ans.get("error", "Unknown error")
                })
        except Exception as e:
            all_passed = False
            test_results.append({
                "uuid": uuid,
                "status": "exception",
                "error": str(e)
            })
    
    
    if not has_actual_test:
        all_passed = False
    
    return all_passed, test_results, modified_tool_calls


async def merge_single_cluster_code(data_dict, config, max_retry=20):
    """
    Asynchronously merge code for a single intent cluster with retry and verification.
    
    Takes multiple QA pairs that share similar intent and merges their tool code
    into a single function that can handle all cases. Uses LLM to patch mock data
    and verifies the merged code against all test cases.
    """
    cluster = data_dict.get("clusters", {})
    intent_summary = cluster.get("intent_summary", "")
    sub_uuids = cluster.get("_uuids", [])
    reason = cluster.get("reason", "")
    main_uuid = data_dict.get("main_uuid", "")
    
    logger.info(f"Starting merge code for cluster: intent='{intent_summary}', uuids={sub_uuids}, main_uuid={main_uuid}")
    
    try:
        # Extract QA and code
        qa_code_list = extract_qa_code_by_uuids(data_dict, sub_uuids)
        original_qa_code = deepcopy(qa_code_list)
        
        if not qa_code_list:
            logger.warning(f"Warning: no data found for cluster '{intent_summary}'")
            return {
                "intent_summary": intent_summary,
                "reason": reason,
                "main_uuid": main_uuid,
                "_uuids": sub_uuids,
                "status": "no_data",
                "merged_code": None,
                "original_qa_code": []
            }
        
        
        tool_names = set((item.get("tool_name") or "") for item in qa_code_list)
        tool_names.discard("")
        
        
        retry_count = 0
        best_result = None
        best_passed_count = 0
        
        while retry_count < max_retry:
            try:
                
                base_code = ((qa_code_list[0].get("code") or "").strip() if qa_code_list else "")

                
                if retry_count > 0:
                    prompt = create_patch_mock_prompt(base_code, qa_code_list, intent_summary) + f"\n\nNote: This is attempt {retry_count + 1}. Please fix the mock data to pass verification."
                else:
                    prompt = create_patch_mock_prompt(base_code, qa_code_list, intent_summary)
                
                input_messages = [{"role": "user", "content": prompt}]
                
                
                result = await asyncio.to_thread(
                    get_openai_model_ans,
                    input_messages,
                    config,
                    False  # tmp_debug=False
                )
                
                merged_code = _strip_code_fences(result.get("response", ""))

                
                tool_call_map = await asyncio.to_thread(generate_tool_call_statements, merged_code, qa_code_list, config)
                for it in qa_code_list:
                    uuid = it.get("_uuid")
                    it["tool_call_statement"] = tool_call_map.get(uuid) or tool_call_map.get(str(uuid), "")
                
                
                is_valid, test_results, modified_tool_calls = verify_merged_code(merged_code, qa_code_list)
                passed_count = sum(1 for t in test_results if t["status"] == "passed")
                total_count = len(test_results)
                logger.info(f"Verification result for cluster '{intent_summary}': {passed_count}/{total_count} tests passed (attempt {retry_count + 1})")
                
                
                if passed_count >= best_passed_count:
                    best_passed_count = passed_count
                    best_result = {
                        "merged_code": merged_code,
                        "test_results": test_results,
                        "is_valid": is_valid,
                        "retry_count": retry_count,
                        "modified_tool_calls": modified_tool_calls
                    }
                
                
                if is_valid:
                    logger.info(f"Merge code succeeded for cluster '{intent_summary}' after {retry_count + 1} attempts")
                    tool_call_statements = [
                        {
                            "_uuid": qa["_uuid"],
                            "tool_call_statement": modified_tool_calls.get(qa["_uuid"], qa.get("tool_call_statement", "")),
                            "question": qa.get("question", ""),
                            "answer": qa.get("answer", "")
                        }
                        for qa in qa_code_list
                    ]
                    
                    return {
                        "intent_summary": intent_summary,
                        "reason": reason,
                        "main_uuid": main_uuid,
                        "_uuids": sub_uuids,
                        "status": "success",
                        "merged_code": merged_code,
                        "tool_names": list(tool_names),
                        "tool_document": original_qa_code[0].get("tool_document") if original_qa_code else None,
                        "tool_call_statements": tool_call_statements,
                        "original_qa_code": original_qa_code,
                        "verification": {
                            "all_tests_passed": True,
                            "test_results": test_results,
                            "retry_count": retry_count
                        }
                    }
                
                retry_count += 1
                
            except Exception as e:
                logger.error(f"Error: retry {retry_count + 1} failed: {str(e)}")
                retry_count += 1
                continue
        
        
        if best_result:
            logger.info(f"Best merge result for cluster '{intent_summary}': {best_passed_count}/{len(qa_code_list)} tests passed")
            modified_tool_calls = best_result.get("modified_tool_calls", {})
            tool_call_statements = [
                {
                    "_uuid": qa["_uuid"],
                    "tool_call_statement": modified_tool_calls.get(qa["_uuid"], qa.get("tool_call_statement", "")),
                    "question": qa.get("question", ""),
                    "answer": qa.get("answer", "")
                }
                for qa in qa_code_list
            ]
            
            return {
                "intent_summary": intent_summary,
                "reason": reason,
                "main_uuid": main_uuid,
                "_uuids": sub_uuids,
                "status": "partial_success",
                "merged_code": best_result["merged_code"],
                "tool_names": list(tool_names),
                "tool_document": original_qa_code[0].get("tool_document") if original_qa_code else None,
                "tool_call_statements": tool_call_statements,
                "original_qa_code": original_qa_code,
                "verification": {
                    "all_tests_passed": False,
                    "test_results": best_result["test_results"],
                    "passed_count": best_passed_count,
                    "total_count": len(qa_code_list),
                    "retry_count": best_result["retry_count"]
                }
            }
        else:
            
            tool_call_statements = [
                {
                    "_uuid": qa["_uuid"],
                    "tool_call_statement": qa.get("tool_call_statement", ""),
                    "question": qa.get("question", ""),
                    "answer": qa.get("answer", "")
                }
                for qa in qa_code_list
            ]
            
            return {
                "intent_summary": intent_summary,
                "reason": reason,
                "main_uuid": main_uuid,
                "_uuids": sub_uuids,
                "status": "failed",
                "error": f"All {max_retry} retries failed",
                "merged_code": merged_code,
                "tool_names": list(tool_names),
                "tool_call_statements": tool_call_statements,
                "original_qa_code": original_qa_code
            }
        
    except Exception as e:
        logger.error(f"Error: processing cluster {intent_summary} failed: {str(e)} == {data_dict['uuid']}")
        
        return {
            "intent_summary": intent_summary,
            "reason": reason,
            "main_uuid": main_uuid,
            "_uuids": sub_uuids,
            "status": "error",
            "error": str(e),
            "merged_code": merged_code,
            "original_qa_code": []
        }


def _check_env(data_dict):
    """
    Validate environment synthesis results for all entries in data_dict.
    
    Checks that each env_result entry has valid:
    - tool_call_statement (not None, no "http")
    - code (not None)
    - tool_document (with name, description, parameters)
    - tool_call_ans containing the expected answer
    """
    for k, v in data_dict["env_result"].items():
        if v is None:
            continue
        if k != "wrong_info" and v["env_synthesis_result"] is not None:
            cur_answer = v["answer"]
            cur_statement = v["env_synthesis_result"]["data"]["tool_call_statement"]
            cur_code = v["env_synthesis_result"]["data"]["code"]
            cur_tool_doc = v["env_synthesis_result"]["data"]["tool_document"]
            cur_tool_ans = v["env_synthesis_result"]["data"]["tool_call_ans"]
            if cur_statement is None or cur_code is None or cur_tool_doc is None or cur_tool_ans is None: # Cannot be None
                return False
            if "name" not in cur_tool_doc or "description" not in cur_tool_doc or "parameters" not in cur_tool_doc: # tool_document must contain name, description, parameters
                return False
            if "http" in cur_statement: # tool_call_statement cannot contain http
                return False
            if cur_answer not in cur_tool_ans:
                return False
    return True


def post_process_merge_tools(data):
    """
    Post-process merged tools by updating env_result with merged code.
    
    For each cluster with multiple uuids, updates the env_result entries
    with the merged code, tool document, and tool call statements from
    the aggregated environment. Validates that all test cases passed.
    """
    
    logger.info(f"post process merge tools for data: {data['uuid']}")
    aggregated_env_lst = data["aggregated_env"]
    clusters = data["clusters"]

    aggregated_env_lst = data["aggregated_env"]
    aggregated_env_uuids = {}
    for aggregated_env in aggregated_env_lst:
        try:
            _uuids = str(aggregated_env["_uuids"])
            aggregated_env_uuids[_uuids] = aggregated_env
        except:
            logger.error(f"### {data['uuid']} aggregated_env: {aggregated_env} ")
            return None

    env_result= data["env_result"]
    merge_all_passed_flag = 1
    for cluster in clusters:
        _uuids = cluster["_uuids"]
        if len(_uuids) == 1:
            continue
        cur_aggregated_env = aggregated_env_uuids[str(_uuids)]
        merge_code = cur_aggregated_env["merged_code"]
        tool_document = cur_aggregated_env["tool_document"]
        tool_call_statements = cur_aggregated_env["tool_call_statements"]
        tool_call_statements_dict = {}
        for sub_tool_call_statement in tool_call_statements:
            tool_call_statements_dict[sub_tool_call_statement["_uuid"]] = sub_tool_call_statement
        verification = cur_aggregated_env["verification"]
        test_results = verification["test_results"]
        for test_result in test_results:
            
            if test_result["status"] == "passed":
                uuid = test_result["uuid"]
                env_result[str(uuid)]["env_synthesis_result"]["data"]["code"] = merge_code
                env_result[str(uuid)]["env_synthesis_result"]["data"]["tool_document"] = tool_document
                env_result[str(uuid)]["env_synthesis_result"]["data"]["tool_call_statement"] = tool_call_statements_dict[uuid]["tool_call_statement"]
                answer = env_result[str(uuid)]["answer"]
                stdout = test_result["stdout"]
                env_result[str(uuid)]["merge_flag"] = True
                if answer not in stdout:
                    logger.error(f"### {data['uuid']} answer: {answer} is not in stdout: {stdout}")
                    return None
                
            else:
                merge_all_passed_flag = 0
                logger.error(f"### {data['uuid']} test_result: {test_result} is not passed")
                return None
    if merge_all_passed_flag:
        return data
    else:
        return None
    

def merge_tools(data, model_name):
    """
    Main entry point for tool clustering and code merging pipeline.
    
    Pipeline steps:
    1. Filter out sub-questions where tool_necessity is False
    2. Cluster remaining sub-questions by intent similarity using LLM
    3. For clusters with multiple items, merge their tool code into one
    4. Post-process to update env_result with merged code
    """
    if data["env_result"] is None:
        return data
    
    
    if not _check_env(data):
        logger.error(f"env_result is not valid for data: {data['uuid']}")
        return None

    tmp_data = deepcopy(data)
    logger.info(f"judge clusters for data: {data['uuid']} ")
    decomposition_trace = data["decomposition_trace"]
    new_decomposition_trace = []
    for trace in decomposition_trace:
        if trace["tool_necessity"] is False:
            continue
        new_decomposition_trace.append(trace)
    
    num_filtered = len(decomposition_trace) - len(new_decomposition_trace)
    logger.info(f"Filtered {num_filtered} traces with tool_necessity=False, remaining {len(new_decomposition_trace)} traces")
    
    tmp_data["decomposition_trace"] = new_decomposition_trace
    res = asyncio.run(intent_aggregation(model_name, tmp_data))
    data["clusters"] = res["clusters"]
    clusters = res["clusters"]
    logger.info(f"judge clusters for data: {data['uuid']} done, found {len(clusters)} clusters")
    

    logger.info(f"merge cluster code for data: {data['uuid']} ")
    copy_data = deepcopy(data)
    data["aggregated_env"] = []
    not_merge_flag = 1
    merge_count = 0
    for idx, cluster in enumerate(clusters):
        if len(cluster["_uuids"]) > 1:
            not_merge_flag = 0
            merge_count += 1
            logger.info(f"Processing cluster {idx + 1}/{len(clusters)}: {len(cluster['_uuids'])} items, intent='{cluster.get('intent_summary', '')}'")
            config = API_CONFIGS[model_name]
            copy_data["clusters"] = cluster
            merge_env =  asyncio.run(merge_single_cluster_code(copy_data, config))
            data["aggregated_env"].append(merge_env)
            logger.info(f"Cluster {idx + 1} merge completed with status: {merge_env.get('status', 'unknown')}")
            
    
    if not_merge_flag:
        logger.info(f"not merge cluster code for data: {data['uuid']} ")
        return data

    logger.info(f"Merged {merge_count} clusters for data: {data['uuid']}")
    logger.info(f"post process merge tools for data: {data['uuid']} ")
    data = post_process_merge_tools(data)
    logger.info(f"post process merge tools for data: {data['uuid']} done")
    if data is None:
        logger.warning(f"Post-processing failed for data: {data['uuid']}")
        return None
    return data


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
    
    logger.info(f"Starting merge_tools: input_file={input_file}, model_name={model_name}, output_file={output_file}")
    
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    data = json.loads(lines[0])
    uuid = data.get("uuid", "unknown")
    logger.info(f"Loaded input data: uuid={uuid}, num_traces={len(data.get('decomposition_trace', []))}")
    
    start_time = time.time()
    result = merge_tools(data, model_name)
    end_time = time.time()

    elapsed_time = end_time - start_time
    logger.info(f"Merge tools completed for uuid={uuid}, time taken: {elapsed_time:.2f} seconds")
    
    if result is None:
        logger.error(f"Merge tools failed for uuid={uuid}")
        return
    
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)
    logger.info(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()
