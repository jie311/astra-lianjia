# -*- coding: utf-8 -*-
from .prompts import tool_prompts
import json
from openai import OpenAI
import re
import random


def convert_messages_for_tool_role(tool_defs, parameters, server_description,query, moc_prompt=None, sys_prompt=None, curr_time=None, curr_day=None):
    if moc_prompt is None:
        # 50% chance to use query, 50% chance not to use query
        if query:
            moc_prompt = tool_prompts.tool_mock_en_prompt_have_query
        else:
            moc_prompt = tool_prompts.tool_mock_en_prompt
    if sys_prompt is None:
        sys_prompt = tool_prompts.tool_role_en_system_prompt
    new_messages = [{"role": "system", "content": sys_prompt}]
    if curr_time:
        new_messages[0]["content"] += f"The current time is {curr_time}."
    if curr_day:
        new_messages[0]["content"] += f"Today is {curr_time}."
    # new_messages[0]["content"] += f"The server description is: {server_description}"
    tool_call = json.dumps(parameters, ensure_ascii=False)
    prompt = moc_prompt.replace("[tool_defs]", tool_defs).replace("[tool_calls]", tool_call).replace("[server_description]", server_description)
    # If prompt has [query] placeholder, replace it
    if "[query]" in prompt and query:
        prompt = prompt.replace("[query]", query)
    new_messages.append({"role": "user", "content": prompt})
    return new_messages


def convert_history_to_string(history):
    history_str = ""
    for i,item in enumerate(history):
        invo_call, obs = item["function_call"], item["observation"]
        str_line = f"<function_call_{i}> {invo_call} </function_call_{i}> \n <observation_{i}> {obs} </observation_{i}>"
        history_str += str_line + "\n"
    return history_str



def convert_messages_for_tool_role_with_history(tool_defs, parameters, server_description, query,history, moc_prompt=None, sys_prompt=None, curr_time=None, curr_day=None):
    if moc_prompt is None:
        # 50% chance to use query, 50% chance not to use query
        # use_query = query and random.random() < 0.5
        if query:
            moc_prompt = tool_prompts.tool_mock_en_prompt_with_history_have_query
        else:
            moc_prompt = tool_prompts.tool_mock_en_prompt_with_history
    if sys_prompt is None:
        sys_prompt = tool_prompts.tool_role_en_system_prompt
    new_messages = [{"role": "system", "content": sys_prompt}]
    if curr_time:
        new_messages[0]["content"] += f"The current time is {curr_time}."
    if curr_day:
        new_messages[0]["content"] += f"Today is {curr_time}."
    # new_messages[0]["content"] += f"The server description is: {server_description}"

    tool_call = json.dumps(parameters, ensure_ascii=False)
    prompt = moc_prompt.replace("[tool_defs]", tool_defs).replace("[tool_calls]", tool_call).replace("[server_description]", server_description).replace("[history]", convert_history_to_string(history[-5:]))
    # If prompt has [query] placeholder, replace it
    if "[query]" in prompt and query:
        prompt = prompt.replace("[query]", query)
    new_messages.append({"role": "user", "content": prompt})
    return new_messages
    

def convert_gpt_tool_role_output_to_toolace(gpt_output):
    content = gpt_output.strip()
    if content.startswith("```json"):
        content = content.strip().lstrip("```json").rstrip("```").strip()
    return content
    # try:
    #     tool_res = json.loads(content)
    #     assert isinstance(tool_res, list) or isinstance(tool_res, dict)
    # except:
    #     tool_res = content
    # return {"role": "tool", "content": "", "tool_response": tool_res}


def moc_tool_call(tool_defs, parameters, server_description,api_config,query=None,history=[],moc_prompt=None, sys_prompt=None, curr_time=None, ):
    """
    tool_defs: Tool definitions, each line is json.dumps of a tool definition, each tool definition defaults to a dict conforming to json schema
    parameters: Input parameters, list of dict, each list element is one tool call
    query: User query, optional parameter, 50% chance to be used in prompt
    history: Historical call records, list of dict
    curr_time: Current time of data, None if not available
    used_model: Which gpt model to use, default is gpt-4-turbo-2024-04-09
    try_num: Maximum number of retry attempts, returns None if still fails after exceeding
    """
    if not history:
        messages = convert_messages_for_tool_role(tool_defs, parameters, server_description, query, moc_prompt, sys_prompt, curr_time)
    else:
        messages = convert_messages_for_tool_role_with_history(tool_defs, parameters, server_description, query, history, moc_prompt, sys_prompt, curr_time)
    response = openai_call(messages, api_config)
    if response.get("answer",{}):
        return convert_gpt_tool_role_output_to_toolace(response.get("answer"))
    else:
        return None


def parse_response(response_obj, content):
    """
    Parse model response, handling three cases:
    1. Reasoning model: API returns with reasoning_content field
    2. Reasoning model: Thinking process and answer separated by <think> tag in content
    3. Regular model: Returns answer directly
    
    Args:
        response_obj: OpenAI API response object
        content: response.choices[0].message.content
    
    Returns:
        dict: Contains answer and reasoning (optional)
    """
    result = {
        "answer": content,
        "reasoning": None
    }
    
    # Case 1: Check if API response contains reasoning_content field
    try:
        if hasattr(response_obj.choices[0].message, 'reasoning_content'):
            reasoning_content = response_obj.choices[0].message.reasoning_content
            if reasoning_content:
                result["reasoning"] = reasoning_content
                result["answer"] = content
                return result
    except Exception:
        pass
    
    # Case 2: Check if content contains <think> tag
    think_pattern = r'<think>(.*?)</think>(.*)'
    match = re.search(think_pattern, content, re.DOTALL)
    if match:
        result["reasoning"] = match.group(1).strip()
        result["answer"] = match.group(2).strip()
        return result
    
    # Case 3: Regular model, return answer directly
    result["answer"] = content
    result["reasoning"] = None
    
    return result


def openai_call(messages, api_config):
    """OpenAI API call (for multiprocessing)"""
    client = OpenAI(
        base_url=api_config['model_server'],
        api_key=api_config['api_key']
    )
    
    try:
        # Build API parameters
        params = {
            "model": api_config['model'],
            "messages": messages,
            "max_tokens": 16384,
            "temperature": 1,
            "n": 1
        }
        if api_config["generate_cfg"]['extra_body']:
            params['extra_body'] = api_config["generate_cfg"]['extra_body']
            if params['extra_body'].get('chat_template_kwargs'):
                params['extra_body']['chat_template_kwargs']['enable_thinking'] = False
        
        # Call API
        response = client.chat.completions.create(**params)
        content = response.choices[0].message.content
        
        # Parse response
        parsed = parse_response(response, content)
        return parsed
    except Exception as ex:
        print(f"API call failed: {ex}")
        return None
    