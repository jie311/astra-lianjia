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
import json
import requests
from ast import literal_eval
import argparse
import os
from utils.api_client import get_openai_model_ans
from utils.api_config import ( 
    API_CONFIGS,
    ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES,
    ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES, 
    SANDBOX_URL
)

from utils.prompt import ( 
    PROMPT_TOOL_DOCUMENT_GENERATION, 
    PROMPT_TOOL_DOCUMENT_COMPLEXITY_SCALING, 
    PROMPT_CALL_STATEMENT,
    PROMPT_TOOL_DEPLOYMENT,
)
from utils.logger import get_logger

logger = get_logger(__name__)

TMP_DEBUG = True


def parse_ans(string):
    """
    Parse the answer from the string
    """
    if "</think>" in string:
        string = string.split("</think>")[1].strip()
    if string.startswith("```json"):
        string = string[len("```json"):].strip()
    if string.startswith("```"):
        string = string[len("```"):].strip()
    if string.endswith("```"):
        string = string[:-len("```")].strip()

    try:
        return json.loads(string)
    except:    
        try:
            return literal_eval(string)
        except:
            if TMP_DEBUG:
                logger.exception("Failed to parse string")
            return None


def get_code_sandbox_ans(code):
    """
    Get the answer from the code sandbox
    """
    input_dict = \
        {
            "code": code,
            "language": "python"
        }
    response = requests.post(SANDBOX_URL, json=input_dict)
    return response.json()


def _tool_document_generation(question, model_name):
    """
    Step 1. Tool Document Generation
    Generate the tool document for the given question.
    """
    if TMP_DEBUG:
        logger.info(f" >> Step 1. Tool Document Generation")
    final_input = PROMPT_TOOL_DOCUMENT_GENERATION.format(question=question)

    output_parsed = None
    try_times = 0
    while output_parsed is None and try_times < ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES:
        final_input_message = [
            {"role":"user", "content":final_input}
        ]
        output = get_openai_model_ans(final_input_message, API_CONFIGS[model_name], tmp_debug=TMP_DEBUG)["response"]
        output_parsed = parse_ans(output)
        output_parsed = (output_parsed if "tool" in output_parsed and "analysis" in output_parsed else None)
        if output_parsed is None and TMP_DEBUG:
            logger.info(f"\n\n\n >> Tool Document Generation Failed, current try_times: {try_times}")
            
        try_times += 1

    if output_parsed is None:
        logger.info(f"\n\n\n >> After trying {try_times} times, still failed to parse the tool_document_generation answer, directly return None.")
        return None

    if TMP_DEBUG:
        logger.info(f"\n\n\n >> Tool Document Generation Success.")

    return {
        "content": output_parsed["tool"],
        "analysis":output_parsed["analysis"]
    }


def _tool_document_complexity_scaling(tool_document, model_name):
    """
    Step 2. Tool Document Complexity Scaling
    Scale the tool document to the complexity level.
    """
    if TMP_DEBUG:
        logger.info("\n\n\n ---------------------------------------------")
        logger.info(f" >> Step 2. Tool Document Complexity Scaling")
    final_input = PROMPT_TOOL_DOCUMENT_COMPLEXITY_SCALING.format(tool=tool_document)

    output_parsed = None
    try_times = 0
    while output_parsed is None and try_times < ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES:
        final_input_message = [
            {"role":"user", "content":final_input}
        ]
        output = get_openai_model_ans(final_input_message, API_CONFIGS[model_name], tmp_debug=TMP_DEBUG)["response"]
        output_parsed = parse_ans(output)
        output_parsed = (output_parsed if "refined_version" in output_parsed and "analysis" in output_parsed else None)
        if output_parsed is None and TMP_DEBUG:
            logger.info(f"\n\n\n >> Tool Document Complexity Scaling Failed, current try_times: {try_times}")
        try_times += 1

    if output_parsed is None:
        logger.info(f"\n\n\n >> After trying {try_times} times, still failed to parse the _tool_document_complexity_scaling answer, directly return None.")
        return None

    if TMP_DEBUG:
        logger.info(f"\n\n\n >> Tool Document Complexity Scaling Success.")

    return {
        "content": output_parsed["refined_version"],
        "analysis":output_parsed["analysis"]
    }


def _call_statement_generation(question, tool_description, model_name):
    """
    Step 3. Call Statement Generation
    Generate the call statement for the given question and tool description.
    """
    if TMP_DEBUG:
        logger.info("\n\n\n ---------------------------------------------")
        logger.info(f" >> Step 3. Call Statement Generation")
    final_input = PROMPT_CALL_STATEMENT.format(question=question, tool_description=tool_description)
    output_parsed = None
    try_times = 0
    while output_parsed is None and try_times < ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES:
        final_input_message = [
            {"role":"user", "content":final_input}
        ]
        output = get_openai_model_ans(final_input_message, API_CONFIGS[model_name], tmp_debug=TMP_DEBUG)["response"]
        output_parsed = parse_ans(output)
        output_parsed = (output_parsed if "call" in output_parsed and "analysis" in output_parsed else None)
        if output_parsed is None and TMP_DEBUG:
            logger.info(f"\n\n\n >> Call Statement Generation Failed, current try_times: {try_times}")
        try_times += 1

    if output_parsed is None:
        logger.info(f"\n\n\n >> After trying {try_times} times, still failed to parse the _call_statement_generation answer, directly return None.")
        return None

    if TMP_DEBUG:
        logger.info(f"\n\n\n >> Call Statement Generation Success.")

    return {
        "content": output_parsed["call"],
        "analysis":output_parsed["analysis"]
    }


def _tool_deployment(tool_document, q_a_pairs, call_statement, model_name):
    """
    Step 4. Tool Deployment
    Deploy the tool for the given question and tool description.
    """
    if TMP_DEBUG:
        logger.info("\n\n\n ---------------------------------------------")
        logger.info(f" >> Step 4. Tool Deployment")
    final_input = PROMPT_TOOL_DEPLOYMENT.format(document=tool_document, pairs=q_a_pairs, call_statement=call_statement)
    output_parsed = None
    try_times = 0
    while output_parsed is None and try_times < ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES:
        final_input_message = [
            {"role":"user", "content":final_input}
        ]
        output = get_openai_model_ans(final_input_message, API_CONFIGS[model_name], tmp_debug=TMP_DEBUG)["response"]
        output_parsed = parse_ans(output)
        if output_parsed is None:
            logger.info(f"\n\n\n >> Tool Deployment Failed, current try_times: {try_times}")
            try_times += 1
            continue
        output_parsed = (output_parsed if "function" in output_parsed and "analysis" in output_parsed else None)
        if output_parsed is not None:
            cur_code = output_parsed["function"]
            code_ans = get_code_sandbox_ans(cur_code)
            if code_ans["status"] == "Failed": # the code cannot be deployed
                output_parsed = None

        if output_parsed is None and TMP_DEBUG:
            logger.info(f"\n\n\n >> Tool Deployment Failed, current try_times: {try_times}")

        try_times += 1

    if output_parsed is None:
        logger.info(f"\n\n\n >> After trying {try_times} times, still failed to parse the _tool_deployment answer, directly return None.")
        return None
    
    if TMP_DEBUG:
        logger.info(f"\n\n\n >> Tool Deployment Success.")

    return {
        "content": output_parsed["function"],
        "analysis":output_parsed["analysis"]
    }


def _single_env_synthesis(q_a_pairs, model_name):
    """
    Single Environment Synthesis
    Synthesize the environment for the given question and tool description.
    """
    ret_dict = {
        "data":{
            "tool_document":None,
            "tool_call_statement":None,
            "code":None,
            "tool_call_ans":None
        },
        "extra_info":{
            "tool_document_generation_result":None,
            "tool_document_complexity_scaling_result":None,
            "tool_call_statement_result":None,
            "tool_deployment_result":None,
        }
    }

    
    tool_document_generation_result = _tool_document_generation(q_a_pairs["question"], model_name)
    if tool_document_generation_result is None:
        return None
    ret_dict["extra_info"]["tool_document_generation_result"] = tool_document_generation_result
    ret_dict["data"]["tool_document"] = tool_document_generation_result["content"]
    
    
    tool_document_complexity_scaling_result = _tool_document_complexity_scaling(tool_document_generation_result["content"], model_name)
    if tool_document_complexity_scaling_result is None:
        return None
    ret_dict["extra_info"]["tool_document_complexity_scaling_result"] = tool_document_complexity_scaling_result
    ret_dict["data"]["tool_document"] = tool_document_complexity_scaling_result["content"]


    try_times = 0
    is_success = False
    while try_times < ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES:
        
        call_statement_generation_result = _call_statement_generation(q_a_pairs["question"], tool_document_complexity_scaling_result["content"], model_name)
        if call_statement_generation_result is None:
            logger.info(f"\n\n\n >> Call Statement Generation Failed, current try_times: {try_times}")
            try_times += 1
            continue

        
        tool_deployment_result = _tool_deployment(tool_document_complexity_scaling_result["content"], q_a_pairs, call_statement_generation_result["content"], model_name)
        if tool_deployment_result is None:
            try_times += 1
            logger.info(f"\n\n\n >> Tool Deployment Failed, current try_times: {try_times}")
            continue

        cur_code = tool_deployment_result["content"]
        call_statement = call_statement_generation_result["content"]
        final_code = f"{cur_code}\nprint({call_statement})"

        call_ans = get_code_sandbox_ans(final_code)
        if call_ans["status"] == "Success": # the code cannot be deployed
            if q_a_pairs["answer"] in call_ans["run_result"]["stdout"]:
                is_success = True

                ret_dict["data"]["code"] = cur_code
                ret_dict["data"]["tool_call_statement"] = call_statement
                ret_dict["data"]["tool_call_ans"] = call_ans["run_result"]["stdout"]
                ret_dict["extra_info"]["tool_deployment_result"] = tool_deployment_result
                ret_dict["extra_info"]["tool_call_statement_result"] = call_statement_generation_result

                break
        
        if TMP_DEBUG:
            logger.info(f"\n\n\n >> Test Case not passed, current try_times: {try_times}")
        

        try_times += 1

    if is_success:
        if TMP_DEBUG:
            logger.info("\n\n\n ---------------------------------------------")
            logger.info(f" >> Data Generation Success.")
        return ret_dict
    if TMP_DEBUG:
        logger.info("\n\n\n ---------------------------------------------")
        logger.info(f" >>  Data Generation Failed.")
    return None


def synthesis_single_env(q_a_pairs, model_name, case_save_path=None, debug=True):
    """
    Single Environment Synthesis
    Synthesize the environment for the given question and tool description.
    """
    try_times = 0
    while try_times < ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES:
        ans = _single_env_synthesis(q_a_pairs, model_name)
        if ans is not None:
            if debug:
                logger.info(f"\n\n\n >> Final success.")
            ans.update(q_a_pairs)
            if case_save_path:
                with open(case_save_path, "w") as f:
                    json.dump(ans, f, indent=2, ensure_ascii=False)
            return ans
        try_times += 1
    else:
        if debug:
            logger.info(f"\n\n\n >> Final failed.")
        return None


def env_synthesis(data_dict, model_name):
    """
    env synthesis for each trace in decomposition_trace
    except leaf node tool necessity is False, env_result is directly set to None. because only tool necessity is True will be synthesized.
    """
    decomposition_trace = data_dict["decomposition_trace"]
    data_dict["env_result"] = {}
    uuid_map = {sub_qa['_uuid']: sub_qa for sub_qa in data_dict['decomposition_trace']}
    for trace in decomposition_trace:
        _uuid = trace["_uuid"]
        dependency = trace.get("dependency")
        hop_level = trace.get("hop_level", 1)
        sub_qa = trace
        
        if not trace.get("tool_necessity", True):
            data_dict["env_result"][str(_uuid)] = None
            continue

        if hop_level == 1:
            q_a_pairs = {
                "question": trace.get("sub_question", ""),
                "answer": trace.get("sub_answer", ""),
                "_uuid": _uuid,
                "hop_level": hop_level,
            }
        else:
            if dependency in ("null", "None", None, ""):
                dependency = None
            
            if dependency is not None and dependency != []:
                tmp_question = sub_qa.get('sub_question', '')
                tmp_answer = sub_qa.get('sub_answer', '')
                ref_samples = []
                
                if isinstance(dependency, list):
                    for dep_uuid in dependency:
                        if dep_uuid not in uuid_map:
                            logger.warning(f"Dependency uuid {dep_uuid} not found in decomposition_trace")
                            continue
                        ref_sample = uuid_map[dep_uuid]
                        ref_samples.append(
                            {'question': ref_sample.get('sub_question', ''), 'answer': ref_sample.get('sub_answer', '')}
                        )
                else:
                    if dependency not in uuid_map:
                        logger.warning(f"Dependency uuid {dependency} not found in decomposition_trace")
                    else:
                        ref_sample = uuid_map[dependency]
                        ref_samples.append(
                            {'question': ref_sample.get('sub_question', ''), 'answer': ref_sample.get('sub_answer', '')}
                        )
                
                # 只有当有有效依赖时才添加额外信息
                if ref_samples:
                    question = f"{tmp_question}\n- Additional Information\n{ref_samples}"
                else:
                    question = tmp_question
                
                q_a_pairs = {
                    "question": question,
                    "answer": tmp_answer,
                    "_uuid": _uuid,
                    "hop_level": hop_level,
                }
            else:
                q_a_pairs = {
                    "question": sub_qa.get('sub_question', ''),
                    "answer": sub_qa.get('sub_answer', ''),
                    "_uuid": _uuid,
                    "hop_level": hop_level,
                }

        
        out = synthesis_single_env(
            q_a_pairs=q_a_pairs,
            model_name=model_name,
            debug=TMP_DEBUG
        )
        if out is None:
            data_dict["env_result"][str(_uuid)] = None
        else:
            # Wrap the result in env_synthesis_result to match expected format
            data_dict["env_result"][str(_uuid)] = {
                "question": out.get("question", ""),
                "answer": out.get("answer", ""),
                "env_synthesis_result": {
                    "data": out.get("data", {}),
                    "extra_info": out.get("extra_info", {})
                }
            }
    return data_dict


def main():
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--model_name", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    parser.add_argument("--threshold", type=float, required=True)
    args = parser.parse_args() 
    input_file = args.input_file
    model_name = args.model_name
    output_file = args.output_file
    threshold = args.threshold

    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    results = []
    for line in lines:
        data_dict = json.loads(line)
        if data_dict['tool_necessity_legitimacy'] is False:
            logger.info(f"\n\n\n >> Tool necessity legitimacy is False, skip this data.")
            continue
        if data_dict['verify_result']['score'] < threshold:
            logger.info(f"\n\n\n >> Verify result is less than threshold, skip this data.")
            continue
        data_dict = env_synthesis(data_dict, model_name)
        results.append(data_dict)

    output_dir = os.path.dirname(output_file)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    with open(output_file, "w", encoding="utf-8") as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
