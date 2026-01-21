# Copyright 2023 The Qwen team, Alibaba Group. All rights reserved.
# 
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
# 
#    http://www.apache.org/licenses/LICENSE-2.0
# 
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
import logging
import os
from pprint import pformat
from typing import Dict, Iterator, List, Optional, Literal, Union, Tuple

import openai

if openai.__version__.startswith('0.'):
    from openai.error import OpenAIError  # noqa
else:
    from openai import OpenAIError

from qwen_agent.llm.base import ModelServiceError, register_llm
from qwen_agent.llm.function_calling import BaseFnCallModel
from qwen_agent.llm.schema import ASSISTANT, Message, FunctionCall
from qwen_agent.log import logger
import json
from transformers import AutoTokenizer


@register_llm('oai')
class TextChatAtOAI(BaseFnCallModel):

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        self.model = self.model or 'gpt-4o-mini'
        cfg = cfg or {}

        api_base = cfg.get('api_base')
        api_base = api_base or cfg.get('base_url')
        api_base = api_base or cfg.get('model_server')
        api_base = (api_base or '').strip()

        api_key = cfg.get('api_key')
        api_key = api_key or os.getenv('OPENAI_API_KEY')
        api_key = (api_key or 'EMPTY').strip()

        if openai.__version__.startswith('0.'):
            if api_base:
                openai.api_base = api_base
            if api_key:
                openai.api_key = api_key
            self._complete_create = openai.Completion.create
            self._chat_complete_create = openai.ChatCompletion.create
        else:
            api_kwargs = {}
            if api_base:
                api_kwargs['base_url'] = api_base
            if api_key:
                api_kwargs['api_key'] = api_key

            def _chat_complete_create(*args, **kwargs):
                # OpenAI API v1 does not allow the following args, must pass by extra_body
                extra_params = ['top_k', 'repetition_penalty', 'stop_token_ids']
                if any((k in kwargs) for k in extra_params):
                    kwargs['extra_body'] = copy.deepcopy(kwargs.get('extra_body', {}))
                    for k in extra_params:
                        if k in kwargs:
                            kwargs['extra_body'][k] = kwargs.pop(k)
                if 'request_timeout' in kwargs:
                    kwargs['timeout'] = kwargs.pop('request_timeout')

                client = openai.OpenAI(**api_kwargs)
                # Call the API and capture the response
                response = client.chat.completions.create(*args, **kwargs)
                return response

            def _complete_create(*args, **kwargs):
                # OpenAI API v1 does not allow the following args, must pass by extra_body
                extra_params = ['top_k', 'repetition_penalty', 'stop_token_ids']
                if any((k in kwargs) for k in extra_params):
                    kwargs['extra_body'] = copy.deepcopy(kwargs.get('extra_body', {}))
                    for k in extra_params:
                        if k in kwargs:
                            kwargs['extra_body'][k] = kwargs.pop(k)
                if 'request_timeout' in kwargs:
                    kwargs['timeout'] = kwargs.pop('request_timeout')

                client = openai.OpenAI(**api_kwargs)
                return client.completions.create(*args, **kwargs)

            self._complete_create = _complete_create
            self._chat_complete_create = _chat_complete_create

    def _chat_stream(
        self,
        messages: List[Message],
        delta_stream: bool,
        generate_cfg: dict,
    ) -> Iterator[List[Message]]:
        messages = self.convert_messages_to_dicts(messages)
        try:
            response = self._chat_complete_create(model=self.model, messages=messages, stream=True, **generate_cfg)
            if delta_stream:
                for chunk in response:
                    if chunk.choices:
                        if hasattr(chunk.choices[0].delta,
                                   'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                            yield [
                                Message(role=ASSISTANT,
                                        content='',
                                        reasoning_content=chunk.choices[0].delta.reasoning_content)
                            ]
                        if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                            yield [Message(role=ASSISTANT, content=chunk.choices[0].delta.content)]
            else:
                full_response = ''
                full_reasoning_content = ''
                for chunk in response:
                    if chunk.choices:
                        if hasattr(chunk.choices[0].delta,
                                   'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                            full_reasoning_content += chunk.choices[0].delta.reasoning_content
                        if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                            full_response += chunk.choices[0].delta.content
                        yield [Message(role=ASSISTANT, content=full_response, reasoning_content=full_reasoning_content)]

        except OpenAIError as ex:
            raise ModelServiceError(exception=ex)



    def _chat_no_stream_save_function_calls(
        self,
        messages: List[Message],
        generate_cfg: dict,
    ) -> List[Message]:
        original_messages = copy.deepcopy(messages)
        new_messages = self.convert_messages_to_dicts(original_messages)
        final_message = []
        try:
            response = self._chat_complete_create(model=self.model, messages=new_messages, stream=False, **generate_cfg)
            if hasattr(response.choices[0].message, 'reasoning_content'):
                final_message =  [
                    Message(role=ASSISTANT,
                            content=response.choices[0].message.content,
                            reasoning_content=response.choices[0].message.reasoning_content)
                ]
            
            else:
                final_message = [Message(role=ASSISTANT, content=response.choices[0].message.content)]

            # Handle tool call
            if hasattr(response.choices[0].message, 'tool_calls') and response.choices[0].message.tool_calls:
                for tool_call in response.choices[0].message.tool_calls:
                    fn_name = tool_call.function.name
                    args_json = tool_call.function.arguments
                    final_message.append(Message(role=ASSISTANT, content=[], function_call=FunctionCall(name=fn_name, arguments=args_json)))
            return final_message
        except OpenAIError as ex:
            raise Exception(ex)

    def _chat_stream_save_function_calls(
        self,
        messages: List[Message],
        delta_stream: bool,
        generate_cfg: dict,
    ) -> List[Message]:
        messages = self.convert_messages_to_dicts(messages)
        try:
            response = self._chat_complete_create(model=self.model, messages=messages, stream=True, **generate_cfg)
            full_response = ''
            full_reasoning_content = ''
            accumulated_tool_calls = []
            for chunk in response:
                if chunk.choices:
                    # Collect think content
                    if hasattr(chunk.choices[0].delta,'reasoning_content') and chunk.choices[0].delta.reasoning_content:
                        full_reasoning_content += chunk.choices[0].delta.reasoning_content
                    # Collect answer content
                    if hasattr(chunk.choices[0].delta, 'content') and chunk.choices[0].delta.content:
                        full_response += chunk.choices[0].delta.content
                    if hasattr(chunk.choices[0].delta, 'tool_calls') and chunk.choices[0].delta.tool_calls:
                                        # Accumulate tool_calls
                        for tool_call_chunk in chunk.choices[0].delta.tool_calls:
                            index = tool_call_chunk.index
                            
                            # Ensure accumulated_tool_calls has enough space
                            while len(accumulated_tool_calls) <= index:
                                accumulated_tool_calls.append({
                                    'id': '',
                                    'type': 'function',
                                    'function': {'name': '', 'arguments': ''}
                                })
                            
                            # Accumulate parts of tool_call
                            if hasattr(tool_call_chunk, 'id') and tool_call_chunk.id:
                                accumulated_tool_calls[index]['id'] = tool_call_chunk.id
                            
                            if hasattr(tool_call_chunk, 'type') and tool_call_chunk.type:
                                accumulated_tool_calls[index]['type'] = tool_call_chunk.type
                            
                            if hasattr(tool_call_chunk, 'function'):
                                if hasattr(tool_call_chunk.function, 'name') and tool_call_chunk.function.name:
                                    accumulated_tool_calls[index]['function']['name'] = tool_call_chunk.function.name
                                
                                if hasattr(tool_call_chunk.function, 'arguments') and tool_call_chunk.function.arguments:
                                    accumulated_tool_calls[index]['function']['arguments'] += tool_call_chunk.function.arguments

            message_collected = {
                'role': ASSISTANT,
                'content': full_response,
                'reasoning_content': full_reasoning_content
            }

            final_messages = []
            # Parse reasoning content
            if not full_reasoning_content and "<think>" in full_response or "</think>" in full_response:
                full_reasoning_content = full_response.split("</think>")[0]
                full_response = full_response.split("</think>")[1]
                message_collected['reasoning_content'] = full_reasoning_content.strip()
                message_collected['content'] = full_response.strip()

            final_messages.append(Message(**message_collected))
            if accumulated_tool_calls: # Parallel calls may occur
                for tool_call in accumulated_tool_calls:
                    fn_name = tool_call["function"]["name"]
                    args_json = tool_call["function"]["arguments"]
                    final_messages.append(Message(role=ASSISTANT, content=[],reasoning_content="", function_call=FunctionCall(name=fn_name, arguments=args_json)))
            return final_messages
        except OpenAIError as ex:
            raise ModelServiceError(exception=ex)

            

    def _chat_no_stream(
        self,
        messages: List[Message],
        generate_cfg: dict,
    ) -> List[Message]:
        messages = self.convert_messages_to_dicts(messages)
        try:
            response = self._chat_complete_create(model=self.model, messages=messages, stream=False, **generate_cfg)
            if hasattr(response.choices[0].message, 'reasoning_content'):
                return [
                    Message(role=ASSISTANT,
                            content=response.choices[0].message.content,
                            reasoning_content=response.choices[0].message.reasoning_content)
                ]
            else:
                return [Message(role=ASSISTANT, content=response.choices[0].message.content)]
        except OpenAIError as ex:
            raise ModelServiceError(exception=ex)


    def convert_messages_to_dicts(self, messages: List[Message]) -> List[dict]:
        messages = [msg.model_dump() for msg in messages]
        converted_messages = []
        i = 0
        while i < len(messages):
            # If system/user, just save
            if messages[i]['role'] in ['system', 'user']:
                converted_messages.append(messages[i])
                i += 1
                continue

            # If assistant, check for subsequent tool calls:
            if messages[i]['role'] == 'assistant':
                # If there are subsequent tool calls, merge consecutive tool calls into tool_list and save to current assistant
                tool_call_list = []
                messages_copy = copy.deepcopy(messages[i])
                tool_call_idx = 0
                while i<len(messages)-1 and (messages[i+1]['role'] == 'assistant' and messages[i+1].get("function_call",{}) != {}):
                    fn_name = messages[i+1].get("function_call",{}).get("name","")
                    fn_args = messages[i+1].get("function_call",{}).get("arguments",{})
                    # Ensure arguments are in string format
                    if isinstance(fn_args, dict):
                        fn_args = json.dumps(fn_args, ensure_ascii=False)
                    # Build tool_call format compliant with OpenAI API
                    tool_call_save = {
                        "id": f"call_{tool_call_idx}_{fn_name}",  # Generate unique ID
                        "type": "function",                        # Type must be "function"
                        "function": {                              # Function object
                            "name": fn_name,
                            "arguments": fn_args
                        }
                    }
                    tool_call_list.append(tool_call_save)
                    tool_call_idx += 1
                    i += 1
                if tool_call_list:
                    messages_copy['tool_calls'] = tool_call_list
                    converted_messages.append(messages_copy)
                    i += 1
                    continue
                else:
                    # If no subsequent tool calls, just save
                    converted_messages.append(messages_copy)
                    i += 1
                    continue   
            # If tool, change role to tool, add tool_call_id, save
            if messages[i]['role'] == 'function':
                messages_copy = copy.deepcopy(messages[i])
                messages_copy['role'] = 'tool'
                # Add tool_call_id to tool message (if not present)
                if 'tool_call_id' not in messages_copy and 'name' in messages_copy:
                    # Try to find corresponding tool_call_id from previous assistant message
                    tool_name = messages_copy.get('name', '')
                    for j in range(len(converted_messages) - 1, -1, -1):
                        if converted_messages[j].get('role') == 'assistant' and 'tool_calls' in converted_messages[j]:
                            for tool_call in converted_messages[j]['tool_calls']:
                                if tool_call['function']['name'] == tool_name:
                                    messages_copy['tool_call_id'] = tool_call['id']
                                    break
                            if 'tool_call_id' in messages_copy:
                                break
                converted_messages.append(messages_copy) 
                i += 1
                continue

        return converted_messages
