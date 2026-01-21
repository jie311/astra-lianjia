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

from operators.vote_verify_chain import get_vote_score
from operators.back_translation_verify_chain import back_translation_verify_score

import sys
import os


# Add src directory to path for importing utils module
# operator_config.py -> verify -> 1_graph_build -> src
SRC_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
sys.path.insert(0, SRC_ROOT)
from utils.api_config import API_CONFIGS


# All model API configurations
OPERATOR_CONFIGS = {
    "vote_verify_chain1": {
        "name": "vote_verify_chain1",
        "func": get_vote_score,     # Entry function for the operator
        "api_config": {
            "model": "<YOUR_MODEL>",
            "base_url": "<YOUR_BASE_URL>",
            "api_key": "<YOUR_API_KEY>",
            "temperature": "<YOUR_TEMPERATURE>",
            "max_tokens": "<YOUR_MAX_TOKENS>",
            "extra_body": "<YOUR_EXTRA_BODY>"
        },
        "n_samples": "<YOUR_N_SAMPLES>",  # Number of voting rounds for voting-based operator
    },
    "vote_verify_chain2": {
        "name": "vote_verify_chain2",
        "func": get_vote_score,     # Entry function for the operator
        "api_config": {
            "model": "<YOUR_MODEL>",
            "base_url": "<YOUR_BASE_URL>",
            "api_key": "<YOUR_API_KEY>",
            "temperature": "<YOUR_TEMPERATURE>",
            "max_tokens": "<YOUR_MAX_TOKENS>",
            "extra_body": "<YOUR_EXTRA_BODY>"
        },
        "n_samples": "<YOUR_N_SAMPLES>",  # Number of voting rounds for voting-based operator
    },
    "back_translation": {
        "name": "back_translation",
        "func": back_translation_verify_score,
        "api_config": {
            "models": ["<YOUR_MODEL1>", "<YOUR_MODEL2>", "<YOUR_MODEL3>"],
            "base_url": "<YOUR_BASE_URL>",
            "api_key": "<YOUR_API_KEY>",
            "temperature": "<YOUR_TEMPERATURE>",
            "max_tokens": "<YOUR_MAX_TOKENS>",
            "max_workers": "<YOUR_MAX_WORKERS>"
        }
    }
}


