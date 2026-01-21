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
# api_config.py -> utils -> src
SRC_ROOT = Path(__file__).resolve().parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

########## 
# reward config
TOOL_CALL_QUERY_NEED = True # Default: tool call check requires tool invocation
TOOL_CALL_TOOL_STATUS = True # Default: tool call check returns success status
SAFE_FINAL_ANSWER_SCORE_CORRELATION=1.0
SAFE_FINAL_ANSWER_SCORE_SUMMARY=1.0
SAFE_TOOL_CONCISE_SCORE=1.0
SAFE_TOOL_CALL_SCORE=1.0
SAFE_TOOL_CONTENT_PLAN_SCORE=1.0
SAFE_TOOL_CONTENT_PLAN_ADD_GLOBAL_SCORE=1.0
SAFE_TOOL_CONTENT_UNDERSTAND_SCORE=1.0
SAFE_GLOBAL_PLAN_SCORE=1.0
SAFE_TOOL_CONTENT_UNDERSTAND_SCORE=1.0




######################
API_RETRY_SLEEP_TIME=5
API_MAX_RETRY_TIMES=10
ENV_SYNTHESIS_MAX_RETRY_TIMES=10
ENV_SYNTHESIS_INNER_MAX_RETRY_TIMES=5
ENV_SYNTHESIS_OUTER_MAX_RETRY_TIMES=15




API_CONFIGS = {
        "<Model_Name>": {
        "model": "<Model_Name>",
        "base_url": "<Your Model Base URL>",
        "api_key": "<Your Model API Key>",
        "temperature": 1,
        "max_tokens": 32000,
        "model_type": "oss_vllm",
        "fncall_prompt_type": "oss",
        "parallel_function_calls": True,
        "stream": True,
        "extra_body": {"chat_template_kwargs": {"enable_thinking": True}}
    }
}
