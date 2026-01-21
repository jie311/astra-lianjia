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

from openai import OpenAI
import time
import random
import json
from .api_config import API_CONFIGS, API_RETRY_SLEEP_TIME, API_MAX_RETRY_TIMES


def get_model_ans(
    q,
    base_url,
    api_key,
    model,
    history=[],
    role="user",
    system=None,
    stream=False,
    retry_times=3,
    temperature=0.0,
    max_tokens=16384,
    extra_body={"enable_thinking":True},
    sleep_time=10
):
    if isinstance(base_url, list):
        base_url = random.choice(base_url)
    
    def ensure_str_arguments(args):
        if args is None:
            return "{}"
        if isinstance(args, str):
            return args
        try:
            return json.dumps(args, ensure_ascii=False)
        except Exception:
            return str(args)

    def to_api_tool_calls(tool_calls_like):
        # Compatible with two formats: {'id','type','function':{name, arguments(str)}} or {'function':{name, arguments(dict)}}
        api_calls = []
        for idx, tc in enumerate(tool_calls_like or []):
            _id = tc.get('id') or f"call_{idx}"
            fn = tc.get('function') or {}
            name = fn.get('name') or ''
            args = fn.get('arguments')
            api_calls.append({
                'id': _id,
                'type': 'function',
                'function': {'name': name, 'arguments': ensure_str_arguments(args)}
            })
        return api_calls

    def normalize_messages_for_api(msgs):
        norm, last_assistant_tool_id = [], None
        for m in msgs:
            r, c = m.get('role'), m.get('content')
            nm = {'role': r, 'content': c}
            if r == 'assistant' and m.get('tool_calls'):
                api_calls = to_api_tool_calls(m['tool_calls'])
                nm['tool_calls'] = api_calls
                if api_calls and api_calls[0].get('id'):
                    last_assistant_tool_id = api_calls[0]['id']
            if r == 'tool':
                nm['tool_call_id'] = m.get('tool_call_id') or last_assistant_tool_id
            norm.append(nm)
        return norm

    def split_tool_calls_for_user_and_api(collected):
        # Input: [{'id', 'name', 'arguments'(str)}...], Output two sets: user-readable (parsed), API-usable (string)
        tool_calls_for_user, tool_calls_for_api = [], []
        for i, tc in enumerate(collected):
            raw_args = tc.get('arguments') or ''
            try:
                parsed = json.loads(raw_args) if raw_args else {}
            except Exception:
                parsed = raw_args
            name = tc.get('name') or ''
            _id = tc.get('id') or f'call_{i}'
            tool_calls_for_user.append({'type': 'function', 'function': {'name': name, 'arguments': parsed}})
            tool_calls_for_api.append({'id': _id, 'type': 'function',
                                       'function': {'name': name, 'arguments': ensure_str_arguments(parsed)}})
        return tool_calls_for_user, tool_calls_for_api

    client = OpenAI(api_key=api_key, base_url=base_url)
    default_tools = None

    base_history = history[:] if history else ([{'role': 'system', 'content': system}] if system else [])

    if role == 'tool':
        # Try to bind to the most recent assistant's tool call id
        last_tool_id = None
        for m in reversed(base_history):
            if m.get('role') == 'assistant' and m.get('tool_calls'):
                try:
                    tc0 = m['tool_calls'][0]
                    last_tool_id = tc0.get('id') or tc0.get('function', {}).get('id')
                except Exception:
                    pass
                break
        tool_msg = {'role': 'tool', 'content': q}
        if last_tool_id:
            tool_msg['tool_call_id'] = last_tool_id
        messages_user_view = base_history + [tool_msg]
    else:
        messages_user_view = base_history + [{'role': role, 'content': q}]

    messages_api = normalize_messages_for_api(messages_user_view)

    params = {
        'model': model,
        'messages': messages_api,
        'tools': default_tools,
        'temperature': temperature,
        'top_p': 0.95,
        'max_tokens': max_tokens,
        'stream': stream,
        'extra_body': extra_body
    }
    # print(f'## param: {params}')
    cur_retry = 0
    while True:
        try:
            if stream:
                response_text, acc = '', {}
                for chunk in client.chat.completions.create(**params):
                    if not getattr(chunk, 'choices', None):
                        continue
                    choice = chunk.choices[0]
                    delta = getattr(choice, 'delta', None)
                    if delta:
                        piece = getattr(delta, 'content', None)
                        if piece:
                            # print(piece, end='', flush=True)
                            response_text += piece
                        tcd = getattr(delta, 'tool_calls', None)
                        if tcd:
                            for tc in tcd:
                                idx = getattr(tc, 'index', 0)
                                cur = acc.setdefault(idx, {'id': None, 'name': '', 'arguments': ''})
                                if getattr(tc, 'id', None):
                                    cur['id'] = tc.id
                                fn = getattr(tc, 'function', None)
                                if fn:
                                    if getattr(fn, 'name', None):
                                        cur['name'] = fn.name
                                    if getattr(fn, 'arguments', None):
                                        cur['arguments'] += fn.arguments

                collected = [acc[k] for k in sorted(acc.keys())] if acc else []
                tool_calls_for_user, tool_calls_for_api = split_tool_calls_for_user_and_api(collected)

                new_dict_user = {'role': 'assistant', 'content': response_text, 'tool_calls': tool_calls_for_user}
                new_dict_api = {'role': 'assistant', 'content': response_text, 'tool_calls': tool_calls_for_api}
                return new_dict_user, messages_user_view + [new_dict_api]

            # Non-streaming
            ans = client.chat.completions.create(**params)
            choice = ans.choices[0]
            msg = choice.message
            tc_list = getattr(msg, 'tool_calls', None) or []
            # Unify to collected format then reuse the same formatting logic
            collected = []
            for i, tc in enumerate(tc_list):
                fn = getattr(tc, 'function', None)
                name = getattr(fn, 'name', '') if fn else ''
                raw_args = getattr(fn, 'arguments', '') if fn else ''
                collected.append({
                    'id': getattr(tc, 'id', None) or f'call_{i}',
                    'name': name,
                    'arguments': raw_args if isinstance(raw_args, (str, bytes)) else ensure_str_arguments(raw_args)
                })
            tool_calls_for_user, tool_calls_for_api = split_tool_calls_for_user_and_api(collected)

            new_dict_user = {'role': 'assistant', 'content': msg.content, 'tool_calls': tool_calls_for_user}
            new_dict_api = {'role': 'assistant', 'content': msg.content, 'tool_calls': tool_calls_for_api}
            return new_dict_user, messages_user_view + [new_dict_api]

        except Exception as e:
            cur_retry += 1
            if cur_retry > retry_times:
                print(f"[ERROR] current retry times: {cur_retry}, retry times limit: {retry_times}. directly return None.")
                return {'response': 'None'}
            
            print(f"[WARNING] {str(e)}")
            if " maximum context length of 51200 tokens." in str(e) or 'longer than ' in str(e):
                return {'response': 'None'}
            print(f"sleeping {sleep_time} seconds before retry.")
            time.sleep(sleep_time)




