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

API_RETRY_SLEEP_TIME=5
API_MAX_RETRY_TIMES=10
ENV_SYNTHESIS_MAX_RETRY_TIMES=10
ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES=5
ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES=15

SANDBOX_URL = "<Sandbox_URL>:<Sandbox_Port>/run_code"



API_CONFIGS = {
    "<Model_Name>": {
        "model": "<Model_Name>",
        "base_url": "<Model_URL>",
        "api_key": "<API_Key>",
        "temperature": 1,
        "max_tokens": 32000,
        "stream": True,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}
    }
}



