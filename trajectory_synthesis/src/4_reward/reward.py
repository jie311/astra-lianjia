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
import sys
from pathlib import Path

# Add src directory to sys.path to ensure module imports work correctly
# reward.py -> 4_reward -> src
SRC_ROOT = Path(__file__).resolve().parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import json
import time
import asyncio
import re
import os
import numpy as np
from statistics import mean
from typing import Dict, Any, Optional
import argparse

from utils.api_config import (
    SAFE_TOOL_CONCISE_SCORE,
    SAFE_FINAL_ANSWER_SCORE_CORRELATION,
    SAFE_FINAL_ANSWER_SCORE_SUMMARY,
    TOOL_CALL_QUERY_NEED,
    TOOL_CALL_TOOL_STATUS,
    API_MAX_RETRY_TIMES,
    SAFE_TOOL_CALL_SCORE,
    SAFE_TOOL_CONTENT_PLAN_SCORE,
    SAFE_TOOL_CONTENT_UNDERSTAND_SCORE,
    SAFE_GLOBAL_PLAN_SCORE,
    API_CONFIGS
)
from utils.api_client import get_model_ans
from utils.semaphore_config import gather_with_semaphore, init_semaphore
from utils.prompt import (
    PROMPT_REWARD_CONCISE,
    PROMPT_REWARD_FINAL_ANSWER_SUMMARY,
    PROMPT_REWARD_FINAL_ANSWER_CORRELATION,
    PROMPT_REWARD_URL,
    PROMPT_TOOL_STATUS,
    PROMPT_TOOL_CONTENT_PLAN,
    PROMPT_TOOL_CONTENT_UNDERSTAND,
    PROMPT_QUERY_UNDERSTAND,
    PROMPT_QUERY_PLAN
)
from utils.log_utils import get_logger

logger = get_logger(__name__)


def _extract_think_and_clean_json(string: str) -> tuple:
    """
    general json preprocessing function
    1. extract </think> tag content
    2. clean markdown code block
    """
    think_content = None
    string = string.strip()
    
    
    if '</think>' in string:
        think_content, string = string.rsplit('</think>', 1)
        string = string.strip()
    
    
    if string.startswith('```json'):
        string = string[len('```json'):].strip()
    elif string.startswith('```'):
        string = string[len('```'):].strip()
    if string.endswith('```'):
        string = string[:-len('```')].strip()
    
    return think_content, string


# =============================================================================
# Step 01: Tool Concise Score
# =============================================================================
def _parse_json_concise(string):
    """
    parse json string to dict
    """
    think_content, string = _extract_think_and_clean_json(string)
    
    try:
        js = json.loads(string)
        js['think'] = think_content
        return js
    except Exception as e:
        logger.error(f'reward_step_01_concise: JSON parsing failed: {e}, raw_string: {string[:200] if string else "empty"}')
        return {
            'score': SAFE_TOOL_CONCISE_SCORE, 
            'extra_info': {
                'error': str(e),
                'raw_result': string,
                'note': 'JSON parsing failed, assigned safe score.',
                'think': think_content,
                'is_safe_score': 1
            }
        }


async def get_tool_concise(trj, model_name):
    """
    Evaluate the conciseness of tool calls in the trajectory.
    
    Assesses whether tool calls are efficient and not redundant.
    """
    logger.info(f'reward_step_01_concise: get tool concise score for trajectory....')
    model_config = API_CONFIGS[model_name]
    trj_data = trj
    trj_str = None

    if isinstance(trj, (bytes, bytearray)):
        trj = trj.decode('utf-8')

    if isinstance(trj, str):
        trj_str = trj
        trj_data = json.loads(trj)
    else:
        try:
            trj_str = json.dumps(trj, ensure_ascii=False)
        except (TypeError, ValueError) as e:
            logger.warning(f'reward_step_01_concise: json.dumps failed, using str(): {e}')
            trj_str = str(trj)

    has_tool_calls = False
    if isinstance(trj_data, dict):
        messages = trj_data.get("messages", [])
        for msg in messages:
            if msg.get("tool_calls") or (msg.get("role") == "tool"):
                has_tool_calls = True
                break
    if not has_tool_calls:
        return {
            "score": SAFE_TOOL_CONCISE_SCORE,
            "extra_info": {
                "thought": "No tool calls found in trajectory, assigned safe score.",
                "is_safe_score": 1
            }
        }

    final_input = PROMPT_REWARD_CONCISE.replace('{trajectory}', trj_str)
    res = await asyncio.to_thread(get_model_ans, final_input, **model_config)
    parsed_json = _parse_json_concise(res[0]['content'])

    tool_scores = parsed_json.get('tool_score_list', [])
    valid_scores = []
    for score in tool_scores:
        try:
            valid_scores.append(float(score))
        except (TypeError, ValueError) as e:
            logger.warning(f'reward_step_01_concise: invalid score value: {score}, error: {e}')
            continue
    
    is_safe_score = 0
    if not valid_scores:
        valid_scores = [SAFE_TOOL_CONCISE_SCORE]
        is_safe_score = 1
    
    final_score = round(float(mean(valid_scores)), 3)
    logger.info(f'reward_step_01_concise: get tool concise score for trajectory done')
    return {
        "score": final_score,
        "extra_info": {
            'thought': parsed_json.get('thought', ''), 
            'tool_evaluations': parsed_json.get('tool_evaluations', []), 
            'think': parsed_json.get('think', ''),
            'is_safe_score': is_safe_score
        }
    }


# =============================================================================
# Step 02: Final Answer Score
# =============================================================================
def _parse_json_final_answer(string: str, prompt: str) -> Dict[str, Any]:
    """
    post process the response to extract the JSON object
    support formats:
    1. pure JSON string
    2. JSON wrapped in markdown code block (```json...``` or ```...```)
    3. JSON object in mixed text
    4. response with <think> tag
    """
    
    think_content = None
    string = string.strip()
    response = string
    if '</think>' in string:
        think_content, sub_string = string.rsplit('</think>', 1)
        response = sub_string.strip()
    
    code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    code_blocks = re.findall(code_block_pattern, response, re.DOTALL)
    
    if code_blocks:
        response = code_blocks[0].strip()
    
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, response, re.DOTALL)
    
    if json_matches:
        for json_str in json_matches:
            try:
                result = json.loads(json_str.strip())
                result['think'] = think_content
                tmp = {
                    'score': result['score'],
                    'extra_info': result
                }
                return tmp
            except json.JSONDecodeError:
                continue
    
    try:
        result = json.loads(response.strip())
        result['think'] = think_content
        tmp = {
            'score': result['score'],
            'extra_info': result
        }
        return tmp
    except json.JSONDecodeError as e:
        logger.error(f'reward_step_02_final_answer: JSON decode error: {e}')
        if 'score_correlation' in prompt:
            return {
                'score': SAFE_FINAL_ANSWER_SCORE_CORRELATION,
                'extra_info': {
                    'error': str(e),
                    'safe_score': SAFE_FINAL_ANSWER_SCORE_CORRELATION,
                    'think': think_content,
                    'is_safe_score': 1
                }
            }
        else:
            return {
                'score': SAFE_FINAL_ANSWER_SCORE_SUMMARY,
                'extra_info': {
                    'error': str(e),
                    'safe_score': SAFE_FINAL_ANSWER_SCORE_SUMMARY,
                    'think': think_content,
                    'is_safe_score': 1
                }
            }


async def _url_final_answer(query, answer, trajectory_str, model_dict):
    """
    Verify URLs in the answer exist in the trajectory.
    
    Returns 1 if all URLs are valid (exist in trajectory or verified by model),
    returns 0 if any URL fails verification.
    """
    logger.info(f'reward_step_02_final_answer: checking URL existence in trajectory...')
    def split_url(answer):
        """
        extract URLs from answer
        """
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]，。！？；：]+[^\s<>"{}|\\^`\[\]，。！？；：.,;:!?]'
        urls = re.findall(url_pattern, answer)
        return urls
    
    urls = split_url(answer)
    logger.info(f'reward_step_02_final_answer: found {len(urls)} URLs in answer')
    for url in urls:
        if url not in trajectory_str:
            logger.warning(f'reward_step_02_final_answer: URL not in trajectory, calling model to verify: {url[:100]}')
            prompt = PROMPT_REWARD_URL.replace("URL", url).replace("ANSWER", answer)
            response = await asyncio.to_thread(get_model_ans, prompt, **model_dict)

            try:
                response = _parse_json_final_answer(response[0]['content'], prompt)
            except Exception as e:
                logger.error(
                    f"reward_step_02_final_answer: JSON parsing failed: {e}, raw_string: "
                    f"{response[0]['content'][:200] if response[0].get('content') else 'empty'}"
                )
                return 1 # safe score


            if response['score'] == 1.0:
                logger.info(f'reward_step_02_final_answer: URL verified by model')
                return 1
            else:
                logger.warning(f'reward_step_02_final_answer: URL verification failed')
                return 0
    logger.info(f'reward_step_02_final_answer: all URLs exist in trajectory')
    return 1


def _check_language_consistency_final_answer(query, answer):
    """
    check the language consistency of query and answer
    by detecting the character type in the text
    """
    def detect_language(text):
        """
        simple language detection function
        return 'zh' for Chinese, 'en' for English, 'mixed' for mixed
        """
        if not text or not isinstance(text, str):
            return 'unknown'
        
        chinese_chars = 0
        english_chars = 0
        total_chars = 0
        
        for char in text:
            if '\u4e00' <= char <= '\u9fff':  
                chinese_chars += 1
                total_chars += 1
            elif char.isalpha():  
                english_chars += 1
                total_chars += 1
        
        if total_chars == 0:
            return 'unknown'
        
        chinese_ratio = chinese_chars / total_chars
        english_ratio = english_chars / total_chars
        
        if chinese_ratio > 0.6:
            return 'zh'
        elif english_ratio > 0.7:
            return 'en'
        else:
            return 'mixed'
    
    query_lang = detect_language(query)
    answer_lang = detect_language(answer)
    if query_lang == 'unknown' or answer_lang == 'unknown':
        return 1
    
    if query_lang == answer_lang:
        return 1
    
    return 0


async def _evaluate_final_answer_correlation_final_answer(query_data: dict, model_dict) -> Optional[Dict[str, Any]]:
    """
    Evaluate how relevant the final answer is to the user's query.
    """
    logger.info(f'reward_step_02_final_answer: evaluating correlation...')
    trajectory = query_data['messages']
    trajectory_str = json.dumps(trajectory[:-1], ensure_ascii=False)
    query = trajectory[1]['content']
    answer = trajectory[-1]['content']

    if not _check_language_consistency_final_answer(query, answer):
        return {
            'score': 0.0,
            'extra_info': {
                'score': 0.0,
                'reason': 'language inconsistency: query and answer have different languages',
                'thought': 'detected language inconsistency between query and answer.'
            }
        }

    prompt = PROMPT_REWARD_FINAL_ANSWER_CORRELATION.replace("QUERY", query).replace("ANSWER", answer)
    
    response = await asyncio.to_thread(get_model_ans, prompt, **model_dict)
    try:
        response = _parse_json_final_answer(response[0]['content'], prompt)
    except Exception as e:
        logger.error(f'reward_step_02_final_answer: correlation parsing failed: {e}')
        return {
            'score': SAFE_FINAL_ANSWER_SCORE_CORRELATION,
            'extra_info': {
                'error': str(e),
                'safe_score': SAFE_FINAL_ANSWER_SCORE_CORRELATION,
                'is_safe_score': 1
            }
        }
    return response


async def _evaluate_final_answer_summary_final_answer(query_data: dict, model_dict) -> Optional[Dict[str, Any]]:
    """
    evaluate if the final_answer is a good summary of the trajectory (async version)
    """
    logger.info(f'reward_step_02_final_answer: evaluating summary...')
    trajectory = query_data['messages']
    trajectory_str = json.dumps(trajectory[:-1], ensure_ascii=False)
    
    tmp_trajectory = json.loads(trajectory_str)
    if len(tmp_trajectory) == 2 and tmp_trajectory[0]['role'] == 'system' and tmp_trajectory[1]['role'] == 'user':
        return {
            'score': 1.0,
            'extra_info': {
                'trajectory': tmp_trajectory,
                'reason': 'trajectory only contains user and system interaction, directly score 1.0',
                'thought': 'trajectory only contains user and system interaction, directly score 1.0',
            }
        }
    final_answer = trajectory[-1]['content']

    query = trajectory[1]['content']
    if 'http' in final_answer:
        url_score = await _url_final_answer(query, final_answer, trajectory_str, model_dict)
        if url_score == 0:
            return {
                'score': 0,
                'extra_info': {
                    'url_score': url_score,
                    'reason': 'URL in answer does not exist in trajectory',
                }
            }

    prompt = PROMPT_REWARD_FINAL_ANSWER_SUMMARY.replace("TRAJECTORY", trajectory_str).replace("FINAL_ANSWER", final_answer)
    
    response = await asyncio.to_thread(get_model_ans, prompt, **model_dict)
    try:
        response = _parse_json_final_answer(response[0]['content'], prompt)
    except Exception as e:
        logger.error(f'reward_step_02_final_answer: summary parsing failed: {e}')
        return {
            'score': SAFE_FINAL_ANSWER_SCORE_SUMMARY,
            'extra_info': {
                'error': str(e),
                'safe_score': SAFE_FINAL_ANSWER_SCORE_SUMMARY,
                'is_safe_score': 1
            }
        }
    return response


async def get_final_answer_score(query_data: dict, model_name) -> tuple:
    """
    judge the final answer of query
    focus on two parts: 
    Correlation: Evaluates how relevant the answer is to the user's question
    Summary: Evaluates whether the answer accurately summarizes the information from the conversation trajectory
    """
    logger.info(f'reward_step_02_final_answer: evaluate the final answer of query....')
    model_dict = API_CONFIGS[model_name]
    score_correlation, score_summary = await asyncio.gather(
        _evaluate_final_answer_correlation_final_answer(query_data, model_dict),
        _evaluate_final_answer_summary_final_answer(query_data, model_dict)
    )
    avge_score = (score_correlation['score'] + score_summary['score']) / 2
    out_format = {
        'score': avge_score,
        'extra_info': {
            'score_correlation': score_correlation,
            'score_summary': score_summary,
            'avge_score': avge_score,
        }
    }
    logger.info(f'reward_step_02_final_answer: evaluate done, correlation={score_correlation["score"]:.4f}, summary={score_summary["score"]:.4f}, avg={avge_score:.4f}')
    return out_format


# =============================================================================
# Step 03: Tool Call Score 
# =============================================================================
def _parse_json_tool_call(string: str, prompt: str) -> Dict[str, Any]:
    """
    post process the response to extract the JSON object
    """
    think_content = None
    string = string.strip()
    response = string
    if '</think>' in string:
        think_content, sub_string = string.rsplit('</think>', 1)
        response = sub_string.strip()
    
    code_block_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
    code_blocks = re.findall(code_block_pattern, response, re.DOTALL)
    
    if code_blocks:
        response = code_blocks[0].strip()
    
    json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
    json_matches = re.findall(json_pattern, response, re.DOTALL)
    
    if json_matches:
        for json_str in json_matches:
            try:
                result = json.loads(json_str.strip())
                result['think'] = think_content
                return result
            except json.JSONDecodeError as e:
                logger.error(f'reward_step_03_tool_call: JSON decode error: {e}')
                if 'need_tool_call' in prompt:
                    return {
                        'thought': 'parse_json failed: cannot get tool call judgment result',
                        'need_tool_call': TOOL_CALL_QUERY_NEED,
                        'think': think_content
                    }
                else:
                    return {
                        'thought': 'parse_json failed: cannot get tool call judgment result',
                        'tool_status': TOOL_CALL_TOOL_STATUS,
                        'think': think_content
                    }
    
    try:
        result = json.loads(response.strip())
        result['think'] = think_content
        return result
    except json.JSONDecodeError as e:
        logger.error(f'reward_step_03_tool_call: JSON decode error: {e}')
        if 'need_tool_call' in prompt:
            return {
                'thought': 'parse_json failed: cannot get tool call judgment result',
                'need_tool_call': TOOL_CALL_QUERY_NEED,
                'think': think_content
            }
        else:
            return {
                'thought': 'parse_json failed: cannot get tool call judgment result',
                'tool_status': TOOL_CALL_TOOL_STATUS,
                'think': think_content
            }


async def _get_LLM_tool_status(tool_return_content: str, model_dict: Dict) -> Dict[str, Any]:
    """
    Use LLM to determine if a tool call succeeded or failed based on its return content.
    """
    for i in range(API_MAX_RETRY_TIMES):
        try:
            prompt = PROMPT_TOOL_STATUS.replace("TOOL_CONTENT", tool_return_content)
            
            response = await asyncio.to_thread(get_model_ans, prompt, **model_dict)
            response_content = response[0]['content']
            
            result = _parse_json_tool_call(response_content, prompt)
            logger.info(f'reward_step_03_tool_call: get_LLM_tool_status success, tool_status={result.get("tool_status", "N/A")}')
            return result
            
        except Exception as e:
            logger.error(f'reward_step_03_tool_call: get_LLM_tool_status error (attempt {i+1}/{API_MAX_RETRY_TIMES}): {e}')
            if i < API_MAX_RETRY_TIMES - 1:
                wait_time = 2 ** i
                logger.info(f'reward_step_03_tool_call: retrying after {wait_time}s...')
                await asyncio.sleep(wait_time)
            continue
    logger.error(f'reward_step_03_tool_call: get_LLM_tool_status failed after {API_MAX_RETRY_TIMES} retries')
    return {
        'tool_status': TOOL_CALL_TOOL_STATUS,
        'thought': 'get_LLM_tool_status failed: cannot get tool call judgment status'
    }


async def get_tool_call_score(query_data: Optional[Dict] = None, model_name: str = "GLM-4.7-FP8") -> Dict[str, Any]:
    """
    Evaluate tool call success/failure status in the trajectory.
    
    Calculates a weighted score based on the success rate of tool executions.
    """
    logger.info(f'reward_step_03_tool_call: evaluate the quality of tool call....')
    model_dict = API_CONFIGS[model_name]
    trajectory = query_data['messages']
    query = trajectory[1]['content']
    all_LLM_ans = []
    

    tool_call_map = {}
    messages = trajectory
    for msg in messages:
        role = msg.get('role')
        if role == 'assistant' and 'tool_calls' in msg:
            for tool_call in msg['tool_calls']:
                tool_call_id = tool_call.get('id')
                if tool_call_id and 'function' in tool_call:
                    function_name = tool_call['function'].get('name')
                    if function_name:
                        tool_call_map[tool_call_id] = function_name
    tool_name_times_call = {}
    total_fail, total_success = 0, 0
    
    tool_status_tasks = []
    tool_msg_list = []
    for msg in messages:
        role = msg.get('role')
        if role == 'tool':
            tool_call_id = msg.get('tool_call_id')
            if tool_call_id:
                function_name = tool_call_map.get(tool_call_id)
                if function_name not in tool_name_times_call:
                    tool_name_times_call[function_name] = {
                        'success': 0,
                        'fail': 0
                    }
                tool_msg_list.append((tool_call_id, function_name, msg))
                tool_status_tasks.append(_get_LLM_tool_status(msg.get('content'), model_dict))
    
    if tool_status_tasks:
        logger.info(f'reward_step_03_tool_call: processing {len(tool_status_tasks)} tool calls...')
        tool_status_results = await gather_with_semaphore(*tool_status_tasks, name="tool_call", return_exceptions=True)
        
        for (tool_call_id, function_name, msg), tool_status in zip(tool_msg_list, tool_status_results):
            if isinstance(tool_status, Exception):
                logger.error(f"tool_call coroutine exception: {type(tool_status).__name__}: {tool_status}")
                tool_status = {'tool_status': TOOL_CALL_TOOL_STATUS}
            all_LLM_ans.append(tool_status)
            if tool_status.get('tool_status'):
                tool_name_times_call[function_name]['success'] += 1
                total_success += 1
            else:
                tool_name_times_call[function_name]['fail'] += 1
                total_fail += 1

    total_calls = total_success + total_fail
    logger.info(f'reward_step_03_tool_call: tool call stats - total={total_calls}, success={total_success}, fail={total_fail}')
    safe_flag = 0
    if total_calls > 0:
        avg_score = (1.0 * total_success + 0.5 * total_fail) / total_calls
        logger.info(f'reward_step_03_tool_call: calculated avg_score={avg_score:.4f}')
    else:
        avg_score = SAFE_TOOL_CALL_SCORE
        safe_flag = 1
        logger.warning(f'reward_step_03_tool_call: no tool calls found, using safe_score={SAFE_TOOL_CALL_SCORE}')
    
    weighted_score = avg_score

    if safe_flag == 1:
        logger.info(f'reward_step_03_tool_call: evaluate the quality of tool call done, safe score')
        return {
            'score': SAFE_TOOL_CALL_SCORE,
            'extra_info': {
                'safe_score': SAFE_TOOL_CALL_SCORE,
                'is_safe_score': 1
            }
        }
    else:
        logger.info(f'reward_step_03_tool_call: evaluate the quality of tool call done')
        return {
            'score': weighted_score,
            'extra_info': {
                'tool_call_name_times_call': tool_name_times_call,
                'success_times': total_success,
                'fail_times': total_fail,
                'fail_reasons': all_LLM_ans,
                'score': weighted_score
            }
        }


# =============================================================================
# Step 04: Tool Content Plan Score
# =============================================================================
def _split_trj_tool_content_plan(trj_dict):
    """
    Split trajectory into intermediate planning segments.
    
    Extracts assistant messages that follow tool responses and contain tool_calls,
    excluding the first global plan.
    """
    if isinstance(trj_dict, str):
        trj_dict = json.loads(trj_dict)

    tools = trj_dict.get("tools", [])
    messages = trj_dict.get("messages") or []
    segments = []

    for idx, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        if idx == 0:
            continue
        if messages[idx - 1].get("role") != "tool":
            continue
        if not message.get("tool_calls"):
            continue
        
        if not any(m.get("role") == "tool" for m in messages[idx + 1:]):
            continue
        segments.append(
            {
                "tools": tools,
                "trajectory": messages,
                "plan": {
                    "assistant_index": idx,
                    "tool_calls": message.get("tool_calls"),
                },
            }
        )

    return segments


def _parse_json_tool_content_plan(string):
    """
    Parse JSON response for tool content plan evaluation.
    """
    think_content, string = _extract_think_and_clean_json(string)
    
    try:
        tmp = json.loads(string)
        score = float(tmp.get('score'))
        
        return {
            'score': score,
            'extra_info': {
                "thought": tmp.get('thought', ''),
                "think": think_content
            }
        }
    except Exception as e:
        logger.error(f'reward_step_04_tool_content_plan: _parse_json error: {e}')
        return {
            'score': SAFE_TOOL_CONTENT_PLAN_SCORE,
            'extra_info': {
                'error': str(e),
                'think': think_content,
                'is_safe_score': 1
            }
        }


async def get_tool_plan_score(data_dict, model_dict):
    """
    Evaluate a single intermediate planning segment using LLM.
    """
    logger.info(f'reward_step_04_tool_content_plan: evaluating single plan segment...')
    final_input = (
        PROMPT_TOOL_CONTENT_PLAN.replace("{tools}", str(data_dict["tools"]))
        .replace("{trajectory}", json.dumps(data_dict["trajectory"], ensure_ascii=False))
        .replace("{plan}", json.dumps(data_dict["plan"], ensure_ascii=False))
    )

    ans = await asyncio.to_thread(get_model_ans, final_input, **model_dict)

    if isinstance(ans, dict) and ans.get('response') == 'None':
        logger.error(f'reward_step_04_tool_content_plan: model call failed')
        return {
            "assistant_index": data_dict.get("plan", {}).get("assistant_index", ''),
            "tool_calls": "",
            "score": SAFE_TOOL_CONTENT_PLAN_SCORE,
            "extra_info": {
                "error": "model call failed",
                'is_safe_score': 1
            }
        }

    if not ans or not isinstance(ans, tuple) or len(ans) < 1:
        logger.error(f'reward_step_04_tool_content_plan: model return format error')
        return {
            "assistant_index": data_dict.get("plan", {}).get("assistant_index", ''),
            "tool_calls": "",
            "score": SAFE_TOOL_CONTENT_PLAN_SCORE,
            "extra_info": {
                "error": "model return format error",
                'is_safe_score': 1
            }
        }

    result = _parse_json_tool_content_plan(ans[0]['content'])
    
    assistant_index = data_dict.get("plan", {}).get("assistant_index", '')
    tool_calls = data_dict.get("plan", {}).get("tool_calls")
    tool_calls_str = ' | '.join([f"{tool_call['id']}: {tool_call['function']['name']}" for tool_call in tool_calls]) if tool_calls else ''
    result = {
        "assistant_index": assistant_index,
        "tool_calls": tool_calls_str,
        **result
    }
    return result


async def get_tools_plan_score(trj, model_name: str = "GLM-4.7-FP8"):
    """
    Evaluate the quality of intermediate tool content planning.
    
    Assesses how well the model plans tool usage based on previous tool outputs.
    """
    logger.info(f'reward_step_04_tool_content_plan: evaluate the quality of tool content plan....')
    model_dict = API_CONFIGS[model_name]
    segments = _split_trj_tool_content_plan(trj)
    logger.info(f'reward_step_04_tool_content_plan: found {len(segments)} plan segments to evaluate')
    inputs = [get_tool_plan_score(_trj, model_dict) for _trj in segments]
    if not inputs:
        logger.warning(f'reward_step_04_tool_content_plan: no valid intermediate planning steps found, returning safe score')
        fallback = [
            {
                "assistant_index": -1,
                "tool_calls": "",
                "score": SAFE_TOOL_CONTENT_PLAN_SCORE,
                "extra_info": {
                    "thought": "No valid intermediate planning steps found.",
                    "is_safe_score": 1
                }
            }
        ]
        return {
            "score": SAFE_TOOL_CONTENT_PLAN_SCORE,
            "extra_info": json.dumps(fallback, ensure_ascii=False),
            'is_safe_score': 1
        }
    results = await gather_with_semaphore(*inputs, name="tool_content_plan", return_exceptions=True)
    
    processed_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f'reward_step_04_tool_content_plan: tool_content_plan coroutine exception: {type(r).__name__}: {r}')
            processed_results.append({"score": SAFE_TOOL_CONTENT_PLAN_SCORE, "extra_info": {"error": str(r)}, 'is_safe_score': 1})
        else:
            processed_results.append(r)
    results = processed_results
    numeric_scores = [
        item.get("score") for item in results if isinstance(item.get("score"), (int, float))
    ]
    aggregated_score = round(mean(numeric_scores), 3) if numeric_scores else SAFE_TOOL_CONTENT_PLAN_SCORE
    is_safe_score = 1 if not numeric_scores else 0
    logger.info(f'reward_step_04_tool_content_plan: evaluate done, scores={numeric_scores}, aggregated={aggregated_score:.4f}')
    return {
        "score": aggregated_score,
        "extra_info": results,
        "is_safe_score": is_safe_score
    }


# =============================================================================
# Step 05: Tool Content Understand Score 
# =============================================================================
def _split_trj_tool_content_understand(trj_dict):
    """
    split trajectory, identify consecutive tool messages as a batch (parallel calls)
    skip the last batch of tool calls (usually corresponds to the final answer), the rest of the batches are all evaluated
    """
    cur_tools = trj_dict['tools']
    cur_messages = trj_dict['messages']
    i = 0
    trj_list = []
    
    while i < len(cur_messages):
        if cur_messages[i]['role'] != 'tool':
            i += 1
            continue
        
        tool_batch_start = i
        tool_batch_indices = []
        
        while i < len(cur_messages) and cur_messages[i]['role'] == 'tool':
            tool_batch_indices.append(i)
            i += 1
        
        if i >= len(cur_messages):
            continue
        
        is_final_answer = True
        j = i + 1
        while j < len(cur_messages):
            if cur_messages[j]['role'] == 'tool':
                is_final_answer = False
                break
            j += 1
        
        if is_final_answer:
            continue
        
        index_call_pairs = []
        tool_call_ids = []
        for idx in tool_batch_indices:
            tool_msg = cur_messages[idx]
            tool_call_id = tool_msg.get("tool_call_id", "")
            index_call_pairs.append({
                "index": idx,
                "tool_call_id": tool_call_id
            })
            if tool_call_id:
                tool_call_ids.append(tool_call_id)
        
        trj_list.append({
            "tools": cur_tools,
            "context": cur_messages,
            "ans": cur_messages[i],
            "tool_batch_indices": tool_batch_indices,
            "tool_call_ids": tool_call_ids,
            "tool_index_call_ids": index_call_pairs,
            "tool_batch_start": tool_batch_start,
            "tool_batch_end": i - 1
        })
    return trj_list


def _parse_json_tool_content_understand(string):
    """
    Parse JSON response for tool content understanding evaluation.
    """
    think_content, string = _extract_think_and_clean_json(string)
    
    try:
        result = json.loads(string)
        result['score'] = result['understand_score']
        result['think'] = think_content
        return result
    except Exception as e:
        logger.error(f'reward_step_05_tool_content_understand: json parse error: {e}')
        return {
            'score': SAFE_TOOL_CONTENT_UNDERSTAND_SCORE,
            'extra_info': {
                'error': str(e),
                'think': think_content,
                'is_safe_score': 1
            }
        }


async def get_tool_understand(data_dict, model_dict):
    """
    Evaluate a single tool understanding segment using LLM.
    """
    logger.info(f'reward_step_05_tool_content_understand: evaluating single tool understand segment...')
    tool_batch_indices = data_dict.get('tool_batch_indices', [])
    tool_batch_indices_str = str(tool_batch_indices) if tool_batch_indices else "[]"
    
    tool_call_ids = data_dict.get('tool_call_ids', [])
    tool_call_ids_str = str(tool_call_ids) if tool_call_ids else "[]"
    tool_index_call_ids = data_dict.get('tool_index_call_ids', [])
    tool_index_call_ids_str = str(tool_index_call_ids) if tool_index_call_ids else "[]"
    
    final_input = PROMPT_TOOL_CONTENT_UNDERSTAND.replace('{tools}', str(data_dict['tools'])) \
                       .replace('{trajectory}', str(data_dict['context'])) \
                       .replace('{ans}', str(data_dict['ans'])) \
                       .replace('{tool_batch_indices}', tool_batch_indices_str) \
                       .replace('{tool_call_ids}', tool_call_ids_str) \
                       .replace('{tool_index_call_ids}', tool_index_call_ids_str)
    
    ans = await asyncio.to_thread(get_model_ans, final_input, **model_dict)
    if not ans or not isinstance(ans, (list, tuple)) or len(ans) == 0:
        logger.warning(f'reward_step_05_tool_content_understand: API returned invalid result, using default score')
        return {
            "score": SAFE_TOOL_CONTENT_UNDERSTAND_SCORE,
            "extra_info": [{"content": "API call failed, returning default score"}],
            "is_safe_score": 1
        }
    if not ans[0].get('content'):
        logger.warning(f'reward_step_05_tool_content_understand: API returned empty content, using default score')
        return {
            "score": SAFE_TOOL_CONTENT_UNDERSTAND_SCORE,
            "extra_info": ans,
            "is_safe_score": 1
        }
    tmp_parse_content = _parse_json_tool_content_understand(ans[0]['content'])
    
    result = {
        "score": float(tmp_parse_content['score']),
        "extra_info": {
            'ans': ans,
            'think': tmp_parse_content.get('think', '')
        }
    }
    return result


async def get_tools_understand(trj, model_name):
    """
    Evaluate how well the model understands tool return content.
    
    Assesses whether the model correctly interprets and utilizes tool outputs.
    """
    logger.info(f'reward_step_05_tool_content_understand: evaluate the quality of tool content understand....')
    model_dict = API_CONFIGS[model_name]
    trj_list = _split_trj_tool_content_understand(trj)
    logger.info(f'reward_step_05_tool_content_understand: found {len(trj_list)} understand segments to evaluate')

    if not trj_list:
        logger.warning(f'reward_step_05_tool_content_understand: no valid intermediate planning steps found, returning default score')
        return {
            "score": SAFE_TOOL_CONTENT_UNDERSTAND_SCORE,
            "extra_info": [
                {
                    "thought": "No valid intermediate planning steps found.",
                    "score": SAFE_TOOL_CONTENT_UNDERSTAND_SCORE
                }
            ],
            "is_safe_score": 1
        }
    
    inputs = [get_tool_understand(_trj, model_dict) for _trj in trj_list]
    results = await gather_with_semaphore(*inputs, name="tool_content_understand", return_exceptions=True)
    
    valid_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f'reward_step_05_tool_content_understand: tool_content_understand coroutine exception: {type(r).__name__}: {r}')
            valid_results.append({"score": SAFE_TOOL_CONTENT_UNDERSTAND_SCORE, "extra_info": {"error": str(r)}, 'is_safe_score': 1})
        else:
            valid_results.append(r)
    results = valid_results
    score = mean([_result['score'] for _result in results])
    extra_info_list = [_result['extra_info'] for _result in results]
    logger.info(f'reward_step_05_tool_content_understand: evaluate done, final_score={score:.4f}')

    return {
        "score": score,
        "extra_info": extra_info_list
    }


# =============================================================================
# Step 06: Query Understand Plan Score 
# =============================================================================
def parse_json_with_retry_query_understand_plan(response_content: str, first_response: str, max_retries: int = 1) -> dict:
    """
    JSON parsing with retry mechanism
    """
    try:
        result = _parse_json_query_understand_plan(response_content, first_response)
        return result
    except Exception as e:
        logger.error(f'reward_step_06_query_understand_plan: JSON parsing with retry failed: {e}')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': f'JSON parsing failed: {str(e)}',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'raw_response': response_content[:200] if response_content else '',
                'is_safe_score': 1
            }
        }


def _parse_json_query_understand_plan(string, first_response):
    """
    Parse the JSON string returned by LLM, extract the score.
    """
    if isinstance(string, dict):
        return string
    
    think_content, string = _extract_think_and_clean_json(string)
    
    try:
        result = json.loads(string)
        result['source_content'] = first_response
        result['think'] = think_content
        tmp = {
            'score': float(result['score']),
            'extra_info': result
        }
        return tmp
    except Exception as e:
        logger.error(f'reward_step_06_query_understand_plan: JSON parsing failed: {str(e)}')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': str(e),
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'think': think_content,
                'is_safe_score': 1
            }
        }


async def get_query_understand_score(data_dict, model_name):
    """
    Get query understanding quality score (with retry mechanism)
    """
    model_dict = API_CONFIGS[model_name]
    logger.info(f'reward_step_06_query_understand_plan: evaluating query understanding...')
    query = None
    total_understand = None
    trajectory = str(data_dict['messages'][2:])
    
    for msg in data_dict['messages']:
        if msg['role'] == 'user':
            query = msg['content']
        if msg['role'] == 'assistant':
            total_understand = str(msg)
            break
    
    if not query or not total_understand:
        logger.error(f'reward_step_06_query_understand_plan: missing query or assistant response')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': 'Missing query or assistant response',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'is_safe_score': 1
            }
        }
    
    final_input = PROMPT_QUERY_UNDERSTAND.replace('{query}', query).replace('{query_understand}', total_understand).replace('{trajectory}', trajectory)
    
    response = await asyncio.to_thread(get_model_ans, final_input, **model_dict)
    
    if not response:
        logger.error(f'reward_step_06_query_understand_plan: model returned empty')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': 'Model returned empty',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'think': None,
                'is_safe_score': 1
            }
        }
    
    try:
        response_content = response[0]['content']
        final_ans = parse_json_with_retry_query_understand_plan(response_content, total_understand)
        return final_ans
    except Exception as e:
        logger.error(f'reward_step_06_query_understand_plan: response processing failed: {str(e)}')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': f'Response processing failed: {str(e)}',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'think': None,
                'is_safe_score': 1
            }
        }


async def get_query_plan_score(data_dict, model_name):
    """
    Get query plan quality score (with retry mechanism)
    """
    model_dict = API_CONFIGS[model_name]
    logger.info(f'reward_step_06_query_understand_plan: evaluating query plan...')
    query = None
    total_plan = None
    trajectory = str(data_dict['messages'][2:])
    tools = []
    for to in data_dict['tools']:
        tools.append(to['function']['name'])
    tools = ', '.join(tools)
    
    for msg in data_dict['messages']:
        if msg['role'] == 'user':
            query = msg['content']
        if msg['role'] == 'assistant':
            total_plan = msg['content']
            break
    
    if not query or not total_plan:
        logger.error(f'reward_step_06_query_understand_plan: missing query or assistant response in get_query_plan_score')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': 'Missing query or assistant response',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'is_safe_score': 1
            }
        }
    
    final_input = PROMPT_QUERY_PLAN.replace('{query}', query).replace('{query_plan}', total_plan).replace('{trajectory}', trajectory).replace('{tools}', tools)
    
    response = await asyncio.to_thread(get_model_ans, final_input, **model_dict)
    
    if not response:
        logger.error(f'reward_step_06_query_understand_plan: model returned empty')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': f'Model call failed: {response}',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'is_safe_score': 1
            }
        }
    
    try:
        response_content = response[0]['content']
        final_ans = parse_json_with_retry_query_understand_plan(response_content, total_plan)
        return final_ans
    except Exception as e:
        logger.error(f'reward_step_06_query_understand_plan: response processing failed: {str(e)}')
        return {
            'score': SAFE_GLOBAL_PLAN_SCORE,
            'extra_info': {
                'error': f'Response processing failed: {str(e)}',
                'safe_score': SAFE_GLOBAL_PLAN_SCORE,
                'is_safe_score': 1
            }
        }


# =============================================================================
# Main Test 
# =============================================================================
async def reward_all(data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """
    Run all reward evaluations and return aggregated results.
    """
    logger.info("=" * 60)
    logger.info("Running all reward evaluations...")
    logger.info("=" * 60)

    # Execute all evaluations in parallel
    results = await asyncio.gather(
        get_tool_concise(data, model_name),
        get_final_answer_score(data, model_name),
        get_tool_call_score(data, model_name),
        get_tools_plan_score(data, model_name),
        get_tools_understand(data, model_name),
        get_query_understand_score(data, model_name),
        get_query_plan_score(data, model_name),
        return_exceptions=True
    )

    # Process results
    result_names = [
        'tool_concise', 
        'final_answer', 
        'tool_call', 
        'tool_plan', 
        'tool_understand', 
        'query_understand',
        'query_plan'
    ]
    final_results = {}
    scores = []

    for name, result in zip(result_names, results):
        if isinstance(result, Exception):
            logger.error(f"[ERROR] {name} evaluation failed: {result}")
            final_results[name] = {
                'score': 1.0,
                'extra_info': {'error': str(result), 'is_safe_score': 1}
            }
            scores.append(1.0)
        else:
            final_results[name] = result
            scores.append(result.get('score', 1.0))

    # Calculate overall score
    final_results['overall_score'] = float(np.mean(scores))

    logger.info("=" * 60)
    logger.info("All evaluations completed")
    logger.info(f"Overall score: {final_results['overall_score']:.4f}")
    logger.info("=" * 60)

    return final_results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--inname', type=str, default='ex_data2.json')
    parser.add_argument('--model_name', type=str, default='GLM-4.7-FP8')
    parser.add_argument('--max_concurrent', type=int, default=5)
    args = parser.parse_args()

    
    inname = args.inname
    model_name = args.model_name

    init_semaphore(max_concurrent=args.max_concurrent)

    with open(inname, 'r', encoding='utf-8') as f:
        TEST_DATA = json.load(f)
    

    print(f"🔧 model_name: {model_name}")

    print("=" * 60)
    print("🧪 Reward Functions Test - test reward all")
    print("=" * 60)

    start_time = time.time()
    result = asyncio.run(reward_all(TEST_DATA, model_name))
    end_time = time.time()
    cost_time = end_time - start_time

    
    print("\n" + "=" * 60)
    print("📊 result")
    print("=" * 60)
    for key, value in result.items():
        if key == 'overall_score':
            print(f"  🎯 {key}: {value:.4f}")
        elif isinstance(value, dict):
            score = value.get('score', value.get('score_query_plan', 'N/A'))
            print(f"  📝 {key}: score={score}")
        else:
            print(f"  {key}: {value}")

    print(f"\n⏱️  cost time: {cost_time:.2f}s")

    outname = 'test_out'
    if not os.path.exists(outname):
        os.makedirs(outname)
    output_file = os.path.join(outname, 'test.reward_all.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"💾 result saved to: {output_file}")


if __name__ == '__main__':
    main()
    

