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

from utils.api_config import API_CONFIGS, API_RETRY_SLEEP_TIME, API_MAX_RETRY_TIMES
from utils.logger import get_logger

logger = get_logger(__name__)


def get_openai_model_ans(messages, config, tmp_debug=False):
    """
    Call the OpenAI-compatible API with the given configuration.
    """
    retry_times = API_MAX_RETRY_TIMES
    sleep_time = API_RETRY_SLEEP_TIME
    
    model = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    while True:
        cur_retry = 0
        try:
            params = {
                "model": config["model"],
                "messages": messages,
                "temperature": config.get("temperature", 1.0),
                "top_p": 0.95,
                "max_tokens": config.get("max_tokens", 30*1024),
                "stream": config.get("stream", False),
                "extra_body": config.get("extra_body", {})
            }
            stream = config.get("stream", False)
            # Handle streaming and non-streaming modes separately
            if stream:
                response_text = ""
                reasoning_text = ""
                usage = None
                for chunk in model.chat.completions.create(**params):
                    # Some chunks may not contain choices, so we need to check first
                    if not hasattr(chunk, "choices") or not chunk.choices or not hasattr(chunk.choices[0], "delta"):
                        continue
                    delta = chunk.choices[0].delta
                    content_piece = getattr(delta, "content", None)
                    # Get content (streaming)
                    if content_piece:
                        if reasoning_text and not response_text and tmp_debug:
                            print("\n")
                        if tmp_debug:
                            print(content_piece, end="", flush=True)
                        response_text += content_piece
                    # Get reasoning_content (streaming)
                    reasoning_piece = getattr(delta, "reasoning_content", None)
                    if reasoning_piece:
                        if tmp_debug:
                            print(reasoning_piece, end="", flush=True)
                        reasoning_text += reasoning_piece
                    usage = getattr(chunk, "usage", usage)
                return {
                    "response": response_text,
                    "reasoning_content": reasoning_text if reasoning_text else None,
                    "usage": usage
                }
            else:
                ans = model.chat.completions.create(**params)
                # Get reasoning_content (non-streaming)
                reasoning_content = getattr(ans.choices[0].message, "reasoning_content", None)
                return {
                    "response": ans.choices[0].message.content,
                    "reasoning_content": reasoning_content,
                    "usage": ans.usage
                }

        except Exception as e:
            cur_retry += 1
            if cur_retry > retry_times:
                print(f"[ERROR] Current retry times: {cur_retry}, retry times limit: {retry_times}. Directly return None.")
                return {
                    "response": None,
                    "reasoning_content": None,
                    "usage": None
                }
            if "is longer than the model's context length (51200 tokens)" in str(e):
                print(f"[ERROR] {str(e)}. Directly return None.")
                return {
                    "response": None,
                    "reasoning_content": None,
                    "usage": None
                }

            print(f"[WARNING] {str(e)}")
            print(f"Sleeping {sleep_time} seconds before retry.")
            time.sleep(sleep_time)

