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

from pathlib import Path

DOMAIN_ROOT = Path(__file__).parent.parent / "data" / "taxonomy"

DOMAIN_MAP = {
    "weather": DOMAIN_ROOT / "weather.json",  # 支持英文键
}


def get_domain_config(domain: str) -> Path:
    """
    Get the domain config by domain name
    """
    return DOMAIN_MAP.get(domain, None)
