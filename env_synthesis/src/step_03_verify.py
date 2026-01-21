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
import time
import os
from typing import Any, Dict, List
import sys
import numpy as np
import argparse

from utils.api_client import get_openai_model_ans
from utils.api_config import API_CONFIGS
from utils.semaphore_config import gather_with_semaphore, init_semaphore
from utils.logger import get_logger
from utils.prompt import (
    PROMPT_VERIFY_DEPENDENCY,
    PROMPT_VERIFY_ATOMICITY,
    PROMPT_VERIFY_FORCED_SERIALIZATION,
    PROMPT_VERIFY_SUBQA_COMPLETENESS,
)

logger = get_logger(__name__)

SAFE_DEPENDENCY_SCORE = 1
SAFE_ATOMICITY_SCORE = 1
SAFE_FORCED_SERIAL_SCORE = 1
SAFE_ALIGNMENT_SCORE = 1


def _extract_think_and_clean_response(response_text: str) -> tuple:
    """
    Extract think content from LLM response and clean markdown code blocks.
    """
    think_content = ""
    
    if isinstance(response_text, dict):
        response_text = json.dumps(response_text)
    
    response_text = response_text.strip()
    
    # Extract </think> tag content
    if "</think>" in response_text:
        think_content, response_text = response_text.rsplit("</think>", 1)
        response_text = response_text.strip()
    
    # Remove markdown code block markers
    response_text = response_text.strip()
    if response_text.startswith("```json"):
        response_text = response_text[len("```json"):].strip()
    elif response_text.startswith("```"):
        response_text = response_text[len("```"):].strip()
    if response_text.endswith("```"):
        response_text = response_text[:-len("```")].strip()
    
    return think_content, response_text


def _parse_json_from_llm_response(response) -> tuple:
    """
    Extract JSON object from LLM response.
    
    Supports multiple formats:
    - Response with </think> tags
    - Markdown code blocks (```json)
    - Raw JSON strings
    - Text containing JSON
    """
    think_content = ""
    
    # If already a dict, return directly
    if isinstance(response, dict):
        return response, think_content, json.dumps(response), None
    
    # Extract think content and clean response text
    think_content, cleaned_text = _extract_think_and_clean_response(response)
    
    # Try to parse JSON directly
    try:
        result = json.loads(cleaned_text)
        return result, think_content, cleaned_text, None
    except json.JSONDecodeError:
        pass
    
    # Try to extract from markdown code block (regex match)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned_text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            return result, think_content, cleaned_text, None
        except json.JSONDecodeError:
            pass
    
    # Try to extract from { }
    start = cleaned_text.find("{")
    end = cleaned_text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(cleaned_text[start:end + 1])
            return result, think_content, cleaned_text, None
        except json.JSONDecodeError as e:
            return None, think_content, cleaned_text, str(e)
    
    return None, think_content, cleaned_text, "No valid JSON found in response"


def _parse_json_dependency(string, uuid):
    """
    Parse JSON response for dependency verification and extract score.
    
    Handles multiple input formats: dict, string with </think> tags, 
    markdown code blocks (```json), and raw JSON strings.
    """
    # Use common parsing function
    parsed_dict, think_content, cleaned_text, error = _parse_json_from_llm_response(string)
    
    if error is not None or parsed_dict is None:
        logger.warning(f"[SAFE_SCORE] _parse_json_dependency: JSON parse failed for uuid={uuid}, error={error}, using SAFE_DEPENDENCY_SCORE={SAFE_DEPENDENCY_SCORE}")
        return {
            "score": SAFE_DEPENDENCY_SCORE,
            "extra_info": {
                "uuid": uuid,
                "error": error or "Unknown error",
                "think": think_content,
                "string": cleaned_text,
                "is_safe_score": 1
            }
        }
    
    # Parse score field
    score_raw = parsed_dict.get("score")
    if isinstance(score_raw, str):
        score = int(score_raw) if score_raw.isdigit() else SAFE_DEPENDENCY_SCORE
        if not score_raw.isdigit():
            logger.warning(f"[SAFE_SCORE] _parse_json_dependency: invalid score_raw string '{score_raw}', using SAFE_DEPENDENCY_SCORE={SAFE_DEPENDENCY_SCORE}, uuid={uuid}")
    elif isinstance(score_raw, (int, float)):
        score = int(score_raw)
    else:
        score = SAFE_DEPENDENCY_SCORE
        logger.warning(f"[SAFE_SCORE] _parse_json_dependency: score_raw type is {type(score_raw)}, using SAFE_DEPENDENCY_SCORE={SAFE_DEPENDENCY_SCORE}, uuid={uuid}")

    return {
        "score": score,
        "extra_info": {
            "uuid": uuid,
            "reason": parsed_dict.get("reason", ""),
            "think": think_content,
            "string": cleaned_text
        }
    }


def _split_trace_dependency(response):
    """
    Extract dependency information for each subqa that has dependencies.
    
    Transforms decomposition_trace into a list of formatted dependency samples,
    where each sample contains the subqa's query, answer, and its dependency context.
    """
    all_dependency_samples = []
    dependency_error = []
    for _trj in response:
        if _trj["dependency"] is not None:
            sub_question = _trj["sub_question"]
            sub_answer = _trj["sub_answer"]
            sub_uuid = _trj["_uuid"]
            dependency = []
            try:
                for idx, _dep in enumerate(_trj["dependency"]):
                    _uuid = response[_dep - 1]["_uuid"]
                    dep_query = response[_dep - 1]["sub_question"]
                    dep_answer = response[_dep - 1]["sub_answer"]
                    text = f" step_{_uuid}_query:{dep_query}\nstep_{_uuid}_answer: {dep_answer}\n\n"
                    dependency.append(text)
                if type(sub_question) != str:
                    if type(sub_question) == list:
                        sub_question = " ".join(sub_question)
                    else:
                        sub_question = str(sub_question)
                if type(sub_answer) != str:
                    if type(sub_answer) == list:
                        sub_answer = " ".join(sub_answer)
                    else:
                        sub_answer = str(sub_answer)
                if type(dependency) != str:
                    if type(dependency) == list:
                        dependency = "\n".join(dependency)
                    else:
                        dependency = str(dependency)

                tmp = {
                    "query": sub_question,
                    "answer": sub_answer,
                    "dependency": dependency,
                    "uuid": sub_uuid
                }
                all_dependency_samples.append(tmp)
            except:
                logger.warning(f"Failed to split dependency trace for uuid={sub_uuid}")
                # continue
                dependency_error.append(sub_uuid)

    return all_dependency_samples, dependency_error


async def _get_dependency_score(response, config):
    """
    Get dependency verification score for a single subqa by calling LLM.
    
    Constructs a prompt with the subqa's dependency context and query,
    sends it to the LLM, and parses the response to extract the score.
    """
    try:
        final_input = PROMPT_VERIFY_DEPENDENCY.replace("DEPENDENCY", response["dependency"]).replace("QUERY", response["query"])
        messages = [{"role": "user", "content": final_input}]
        ans = await asyncio.to_thread(get_openai_model_ans, messages, config)

        ans_content = ans["response"]
        result = _parse_json_dependency(ans_content, response["uuid"])

        return result

    except Exception as e:
        logger.error(f"[REQUEST_FAILED] _get_dependency_score: API call failed for uuid={response.get('uuid', 'unknown')}, error={e}, using SAFE_DEPENDENCY_SCORE={SAFE_DEPENDENCY_SCORE}")
        tmp_result = {
            "score": SAFE_DEPENDENCY_SCORE,
            "extra_info": {
                "uuid": response.get("uuid", "unknown"),
                "error": str(e),
                "think": "",
                "is_safe_score": 1,
                "final_input": "N/A (failed to construct)"
            }
        }
        return tmp_result


async def _get_subquestions_dependency_score(response, config):
    """
    Get dependency verification scores for all subqas concurrently.
    
    Splits the decomposition_trace into individual dependency samples,
    then concurrently verifies each one using LLM calls.
    """
    # inputs = [_get_dependency_score(_trj, config) for _trj in _split_trace_dependency(response["decomposition_trace"])]
    all_dependency_samples, dependency_error = _split_trace_dependency(response["decomposition_trace"])
    inputs = [_get_dependency_score(_trj, config) for _trj in all_dependency_samples]
    results = await gather_with_semaphore(*inputs, name="dependency_score", return_exceptions=True)
    processed_results = []
    for r in results:
        if isinstance(r, Exception):
            logger.error(f"[REQUEST_FAILED] dependency_score coroutine exception: {type(r).__name__}: {r}, using SAFE_DEPENDENCY_SCORE={SAFE_DEPENDENCY_SCORE}")
            processed_results.append({"score": SAFE_DEPENDENCY_SCORE, "extra_info": {"error": str(r)}, "is_safe_score": 1})
        else:
            processed_results.append(r)
    results = processed_results
    numeric_scores = [item.get("score") for item in results]
    return numeric_scores, results, dependency_error


async def verify_dependency(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that each subqa's declared dependencies are actually necessary.
    
    Checks whether the dependency information provided in each sub-question 
    is genuinely required for answering that sub-question.
    """
    logger.info("start verifying dependency...")
    response_lst = [data]

    results = {
        "score": [],
        "extra_info": {"scores": [], "info": []}
    }
    scores = []
    dependency_error_all_uuid = []
    for idx, response in enumerate(response_lst):
        dependency_flag, info, dependency_error = await _get_subquestions_dependency_score(response, config)
        if len(dependency_error) > 0:
            final_score = {
                "score": -100,
                "extra_info": {
                    "dependency_error_all_uuid": dependency_error
                }
            }
            return final_score
        
        scores.append(dependency_flag)
        results["extra_info"]["info"].append(info)
    flat_scores = [s for sub in scores for s in sub]
    if flat_scores:
        results["score"] = sum(flat_scores) / len(flat_scores)
    else:
        logger.warning(f"[SAFE_SCORE] verify_dependency: No valid scores found, using SAFE_DEPENDENCY_SCORE={SAFE_DEPENDENCY_SCORE}")
        results["score"] = SAFE_DEPENDENCY_SCORE
        results["extra_info"]["info"].append({
            "score": SAFE_DEPENDENCY_SCORE,
            "reason": "No valid scores found",
            "is_safe_score": 1
        })
    results["extra_info"]["scores"] = scores
    results["extra_info"]["dependency_error_all_uuid"] = dependency_error_all_uuid
    logger.info("dependency verification completed.")
    return results


def _extract_qa_json_from_response_atomicity(response: str) -> dict:
    """
    Extract JSON object from atomicity verification LLM response.
    
    Supports multiple formats: raw JSON, markdown code blocks (```json),
    and responses with </think> tags. Strips thinking content and 
    extracts the JSON payload.
    """
    # Use common parsing function
    parsed_dict, think_content, _, error = _parse_json_from_llm_response(response)
    
    if error is not None or parsed_dict is None:
        logger.warning(f"[SAFE_SCORE] _extract_qa_json_from_response_atomicity: Failed to parse JSON, error={error}, using SAFE_ATOMICITY_SCORE={SAFE_ATOMICITY_SCORE}")
        return {
            "1": {
                "is_atomic": SAFE_ATOMICITY_SCORE,
                "reason_atomic": "The verification result is not a valid JSON object",
                "is_safe_score": 1,
            },
            "think": think_content,
        }
    
    parsed_dict["think"] = think_content
    return parsed_dict


async def verify_data_atomicity(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that each sub-question in the decomposition is atomic (indivisible).
    
    Checks whether each sub-question represents a single, minimal unit of work
    that cannot be further decomposed into smaller meaningful steps.
    """
    logger.info("start verifying data quality...")
    try:
        main_question = data.get("main_question", "")
        final_answer = data.get("final_answer", "")
        trace = data.get("decomposition_trace", [])

        prompt = PROMPT_VERIFY_ATOMICITY.format(
            MAIN_QUESTION=main_question,
            FINAL_ANSWER=final_answer,
            DECOMPOSITION_TRACE=json.dumps(trace, ensure_ascii=False, indent=2)
        )

    except Exception as e:
        logger.warning(f"[SAFE_SCORE] verify_data_atomicity: Data format error={e}, using SAFE_ATOMICITY_SCORE={SAFE_ATOMICITY_SCORE}")
        return {
            "score": SAFE_ATOMICITY_SCORE,
            "extra_info": {
                "scores": [SAFE_ATOMICITY_SCORE],
                "reason": f"Data format error{e}",
                "is_safe_score": 1,
                "think": ""
            }
        }

    messages = [
        {"role": "system", "content": "You are a helpful assistant that verifies data quality."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = await asyncio.to_thread(get_openai_model_ans, messages, config)
        verification_result = _extract_qa_json_from_response_atomicity(response.get("response", ""))
    except Exception as e:
        logger.error(f"[REQUEST_FAILED] verify_data_atomicity: LLM API call failed, error={e}, using SAFE_ATOMICITY_SCORE={SAFE_ATOMICITY_SCORE}")
        verification_result = {
            "1": {
                "is_atomic": SAFE_ATOMICITY_SCORE,
                "reason_atomic": "Parsing error or the verification result is not a valid JSON object",
                "is_safe_score": 1,
            },
            "think": f"Parsing error or the verification result is not a valid JSON object, safety score: {e}",
        }

    # collect scores
    score_lst = []
    for key, value in verification_result.items():
        if key == "think":
            continue
        if not isinstance(value, dict):
            continue
        raw_score = value.get("is_atomic", SAFE_ATOMICITY_SCORE)
        try:
            score = float(raw_score)
        except (TypeError, ValueError):
            logger.warning(f"[SAFE_SCORE] verify_data_atomicity: invalid raw_score type for key={key}, using SAFE_ATOMICITY_SCORE={SAFE_ATOMICITY_SCORE}")
            score = SAFE_ATOMICITY_SCORE
        score_lst.append(score)

    if not score_lst:
        logger.warning(f"[SAFE_SCORE] verify_data_atomicity: No valid scores found in verification_result, using SAFE_ATOMICITY_SCORE={SAFE_ATOMICITY_SCORE}")
        score_lst = [SAFE_ATOMICITY_SCORE]

    avg_score = sum(score_lst) / len(score_lst)
    result = {
        "score": avg_score,
        "extra_info": {
            "scores": score_lst,
            "reason": verification_result,
            "think": verification_result.get("think", "")
        }
    }
    logger.info("data quality verification completed.")
    return result


def _format_traj_forced_serial(traj: List[Dict[str, Any]]) -> str:
    """
    Format trajectory steps into a compact string representation for LLM prompt.
    
    Each step is formatted as a single line containing id, hop level, 
    is_parallel flag, dependencies, sub_question, and sub_answer.
    """
    lines = []
    for step in traj:
        lines.append(
            f"- id:{step.get('_uuid')} hop:{step.get('hop_level')} "
            f"is_parallel:{step.get('is_parallel')} "
            f"dep:{step.get('dependency')} "
            f"q:{step.get('sub_question')} "
            f"a:{step.get('sub_answer')}"
        )
    return "\n".join(lines)


def _build_prompt_forced_serial(traj: List[Dict[str, Any]]) -> str:
    """
    Build the complete prompt for forced serialization detection.
    
    Formats the trajectory and inserts it into the prompt template
    for detecting unnecessary sequential dependencies.
    """
    traj_text = _format_traj_forced_serial(traj)
    detect_forced_serialization = PROMPT_VERIFY_FORCED_SERIALIZATION.format(traj_text=traj_text)
    return detect_forced_serialization


def _parse_json_forced_serial(string: str, uuid: str) -> Dict[str, Any]:
    """
    Parse JSON response from forced serialization verification LLM call.
    
    Handles various input formats: dict, string with </think> tags,
    markdown code blocks. Extracts score (0 or 1) and problematic_steps list.
    """
    # Use common parsing function
    parsed_dict, think_content, cleaned_text, error = _parse_json_from_llm_response(string)
    
    if error is not None or parsed_dict is None:
        logger.error(f"[SAFE_SCORE] _parse_json_forced_serial: JSON parse failed for uuid={uuid}, error={error}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}")
        return {
            "score": SAFE_FORCED_SERIAL_SCORE,
            "problematic_steps": [],
            "extra_info": {
                "uuid": uuid,
                "error": error or "Unknown error",
                "think": think_content,
                "string": cleaned_text,
                "is_safe_score": 1
            }
        }
    
    # Parse score field (only accept 0 or 1)
    score_raw = parsed_dict.get("score")
    if isinstance(score_raw, str):
        score = int(score_raw) if score_raw.isdigit() and score_raw in ["0", "1","0.0","1.0"] else SAFE_FORCED_SERIAL_SCORE
        if not (score_raw.isdigit() and score_raw in ["0", "1","0.0","1.0"]):
            logger.warning(f"[SAFE_SCORE] _parse_json_forced_serial: invalid str score_raw='{score_raw}', using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}, uuid={uuid}")
    elif isinstance(score_raw, (int, float)):
        score = int(score_raw) if score_raw in [0, 1] else SAFE_FORCED_SERIAL_SCORE
        if score_raw not in [0, 1]:
            logger.warning(f"[SAFE_SCORE] _parse_json_forced_serial: invalid numeric score_raw={score_raw}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}, uuid={uuid}")
    else:
        score = SAFE_FORCED_SERIAL_SCORE
        logger.warning(f"[SAFE_SCORE] _parse_json_forced_serial: score_raw type is {type(score_raw)}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}, uuid={uuid}")

    # Parse problematic_steps field
    problematic_steps = parsed_dict.get("problematic_steps", [])
    if not isinstance(problematic_steps, list):
        problematic_steps = []

    return {
        "score": score,
        "problematic_steps": problematic_steps,
        "extra_info": {
            "uuid": uuid,
            "reasoning": parsed_dict.get("reasoning", ""),
            "think": think_content,
            "string": cleaned_text
        }
    }


async def _check_forced_serialization_async(traj: List[Dict[str, Any]], uuid: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Asynchronously check if forced serialization exists in the trajectory.
    
    Calls LLM to detect steps that are unnecessarily serialized when they 
    could be executed in parallel. Returns per-step scores (1=good, 0=problematic).
    """
    if not isinstance(traj, list):
        n = 1
    elif not traj:
        n = 1
    else:
        n = len(traj)

    if not isinstance(traj, list) or not traj:
        logger.warning(f"[SAFE_SCORE] _check_forced_serialization_async: invalid traj (empty or non-list) for uuid={uuid}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}")
        step_scores = [SAFE_FORCED_SERIAL_SCORE] * n
        return {
            "score": SAFE_FORCED_SERIAL_SCORE,
            "extra_info": {
                "step_scores": step_scores,
                "uuid": uuid,
                "error": "invalid traj: empty or non-list",
                "is_safe_score": 1
            }
        }

    try:
        prompt = _build_prompt_forced_serial(traj)
        messages = [{"role": "user", "content": prompt}]
        ans = await asyncio.to_thread(get_openai_model_ans, messages, config, tmp_debug=False)
        raw_content = (ans or {}).get("response", "")

        if not raw_content:
            logger.warning(f"[REQUEST_FAILED] _check_forced_serialization_async: empty response from model for uuid={uuid}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}")
            step_scores = [SAFE_FORCED_SERIAL_SCORE] * len(traj)
            return {
                "score": SAFE_FORCED_SERIAL_SCORE,
                "extra_info": {
                    "step_scores": step_scores,
                    "uuid": uuid,
                    "error": "empty response from model",
                    "is_safe_score": 1
                }
            }

        result = _parse_json_forced_serial(raw_content, uuid)
        problematic_steps = result.get("problematic_steps", [])
        problematic_steps = [int(x) for x in problematic_steps if isinstance(x, (int, str)) and str(x).isdigit()]

        step_scores = []
        for step in traj:
            step_id = step.get("_uuid")
            step_id_int = int(step_id) if isinstance(step_id, (int, str)) and str(step_id).isdigit() else None
            if step_id_int is not None and step_id_int in problematic_steps:
                step_scores.append(0)
            else:
                step_scores.append(1)

        avg_score = sum(step_scores) / len(step_scores) if step_scores else SAFE_FORCED_SERIAL_SCORE

        return {
            "score": avg_score,
            "extra_info": {"step_scores": step_scores, **result.get("extra_info", {})}
        }

    except Exception as e:
        logger.error(f"[REQUEST_FAILED] _check_forced_serialization_async: API call exception for uuid={uuid}, error={e}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}")
        step_scores = [SAFE_FORCED_SERIAL_SCORE] * len(traj)
        return {
            "score": SAFE_FORCED_SERIAL_SCORE,
            "extra_info": {
                "step_scores": step_scores,
                "uuid": uuid,
                "error": f"exception during model call: {e}",
                "is_safe_score": 1
            }
        }


async def verify_forced_serialization(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that the decomposition does not contain forced serialization.
    
    Detects steps that are unnecessarily marked as sequential when they 
    could be executed in parallel, which indicates suboptimal decomposition.
    """
    logger.info("start verifying forced serialization...")
    response_lst = [data]

    results = {
        "score": [],
        "extra_info": {
            "scores": [],
            "info": []
        }
    }

    tasks = [
        _check_forced_serialization_async(
            response.get("decomposition_trace", []),
            response.get("uuid", f"unknown_{idx}"),
            config
        )
        for idx, response in enumerate(response_lst)
    ]

    results_list = await gather_with_semaphore(
        *tasks,
        name="forced_serial_score",
        return_exceptions=True
    )

    processed_results = []
    for r in results_list:
        if isinstance(r, Exception):
            logger.error(f"[REQUEST_FAILED] forced_serial_score coroutine exception: {type(r).__name__}: {r}, using SAFE_FORCED_SERIAL_SCORE={SAFE_FORCED_SERIAL_SCORE}")
            processed_results.append({
                "score": SAFE_FORCED_SERIAL_SCORE,
                "extra_info": {"error": str(r), "is_safe_score": 1, "step_scores": []}
            })
        else:
            processed_results.append(r)

    scores = [item.get("score", SAFE_FORCED_SERIAL_SCORE) for item in processed_results]

    score = np.mean(scores)
    results["score"] = score
    results["extra_info"]["scores"] = scores
    results["extra_info"]["info"] = processed_results
    logger.info("forced serialization verification completed.")
    return results


# ============================================================================
# 4. verify subqa completeness
# ============================================================================
def _format_prompt_final_alignment_completeness(main_question: str, final_answer: str, decomposition_trace: list) -> str:
    """
    Format the prompt for sub-question completeness verification.
    
    Constructs a prompt that asks the LLM to verify whether the decomposed
    sub-questions fully cover all requirements of the main question.
    """
    decomposition_str = json.dumps(decomposition_trace, ensure_ascii=False, indent=2)
    prompt = PROMPT_VERIFY_SUBQA_COMPLETENESS.format(
        main_question=main_question,
        final_answer=final_answer,
        decomposition_trace=decomposition_str
    )
    return prompt


def _parse_json_response_completeness(response_text: str) -> dict:
    """
    Parse JSON response from completeness verification LLM call.
    
    Supports multiple formats: raw JSON, markdown code blocks (```json),
    and responses with </think> tags. Extracts coverage analysis and score.
    """
    # Use common parsing function
    parsed_dict, think_content, _, error = _parse_json_from_llm_response(response_text)
    
    if error is not None or parsed_dict is None:
        logger.warning(f"[SAFE_SCORE] _parse_json_response_completeness: JSON parsing failed, error={error}, using SAFE_ALIGNMENT_SCORE={SAFE_ALIGNMENT_SCORE}")
        return {
            "main_question_requirements": ["parsing failed"],
            "coverage_analysis": {
                "covered_requirements": [],
                "missing_requirements": []
            },
            "thought": "parsing failed, return safe score",
            "score": SAFE_ALIGNMENT_SCORE,
            "think": think_content
        }
    
    parsed_dict["think"] = think_content
    return parsed_dict


async def get_completeness_score(data: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Verify that the decomposed sub-questions completely cover the main question.
    
    Checks whether all requirements and aspects of the main question are
    addressed by the sub-questions, with no missing coverage.
    """
    logger.info("start verify completeness...")
    main_question = data.get("main_question", "")
    final_answer = data.get("final_answer", "")
    decomposition_trace = data.get("decomposition_trace", [])

    try:
        prompt_alignment = _format_prompt_final_alignment_completeness(
            main_question, final_answer, decomposition_trace
        )
        messages = [{"role": "user", "content": prompt_alignment}]

        ans = await asyncio.to_thread(get_openai_model_ans, messages, config)

        ans_content = (ans or {}).get("response", "")
        if not ans_content:
            logger.warning(f"[REQUEST_FAILED] get_completeness_score: empty response from model, using SAFE_ALIGNMENT_SCORE={SAFE_ALIGNMENT_SCORE}")
            return {
                "score": SAFE_ALIGNMENT_SCORE,
                "extra_info": {
                    "error": "empty response from model",
                    "is_safe_score": 1,
                    "main_question_requirements": [],
                    "coverage_analysis": {
                        "covered_requirements": [],
                        "missing_requirements": []
                    }
                }
            }

        result = _parse_json_response_completeness(ans_content)

        
        score_raw = result.get("score")
        if isinstance(score_raw, str) and score_raw in ["0", "1"]:
            score = int(score_raw)
        elif isinstance(score_raw, (int, float)) and score_raw in [0, 1]:
            score = int(score_raw)
        else:
            logger.warning(f"[SAFE_SCORE] get_completeness_score: invalid score_raw={score_raw}, type={type(score_raw)}, using SAFE_ALIGNMENT_SCORE={SAFE_ALIGNMENT_SCORE}")
            score = SAFE_ALIGNMENT_SCORE

        logger.info("completeness check completed.")
        return {
            "score": score,
            "extra_info": {
                "scores": score,
                "think": result.get("think", ""),
                "main_question_requirements": result.get("main_question_requirements", []),
                "coverage_analysis": result.get("coverage_analysis", {}),
                "thought": result.get("thought", ""),
                "response_text": ans_content[:500] if ans_content else ""
            }
        }
    except Exception as e:
        logger.error(f"[REQUEST_FAILED] get_completeness_score: API call failed, error={e}, using SAFE_ALIGNMENT_SCORE={SAFE_ALIGNMENT_SCORE}")
        return {
            "score": SAFE_ALIGNMENT_SCORE,
            "extra_info": {
                "error": str(e),
                "is_safe_score": 1,
                "main_question_requirements": [],
                "coverage_analysis": {
                    "covered_requirements": [],
                    "missing_requirements": []
                }
            }
        }


async def verify_all(data: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """
    Run all four verification checks concurrently and return aggregated results.
    
    Executes dependency, atomicity, forced serialization, and completeness
    verifications in parallel, then computes an overall average score.
    """

    config = API_CONFIGS.get(model_name)
    logger.info("=" * 60)
    logger.info("run all verifications...")
    logger.info("=" * 60)

    
    results = await asyncio.gather(
        verify_dependency(data, config),
        verify_data_atomicity(data, config),
        verify_forced_serialization(data, config),
        get_completeness_score(data, config),
        return_exceptions=True
    )

    
    result_names = ["dependency", "data_quality", "forced_serialization", "completeness"]
    final_results = {}
    scores = []

    for name, result in zip(result_names, results):
        if isinstance(result, Exception):
            logger.error(f"[REQUEST_FAILED] verify_all: {name} verification failed, error={result}, using safe_score=1.0")
            final_results[name] = {
                "score": 1.0,
                "extra_info": {"error": str(result), "is_safe_score": 1}
            }
            scores.append(1.0)
        else:
            final_results[name] = result
            scores.append(result.get("score", 1.0))

    data['verify_result'] = {
        "score": np.mean(scores), 
        "extra_info": final_results
        }

    logger.info("=" * 60)
    logger.info("all verifications completed")
    logger.info(f"overall score: {data['verify_result']['score']:.4f}")
    logger.info("=" * 60)

    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--model_name", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    parser.add_argument("--max_concurrent", type=int, default=5)
    args = parser.parse_args() 
    input_file = args.input_file
    model_name = args.model_name
    output_file = args.output_file
    max_concurrent = args.max_concurrent
    init_semaphore(max_concurrent=max_concurrent)
    results = []
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    start_time = time.time()
    for line in lines:
        TEST_DATA = json.loads(line)
        result = asyncio.run(verify_all(TEST_DATA, model_name))
        results.append(result)
    
    end_time = time.time()
    cost_time = end_time - start_time 

    
    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_file, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")

    print(f"\nDetailed results saved to: {output_file}")


if __name__ == "__main__":

    main()
