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

import asyncio
from typing import Optional, Dict, Tuple


_semaphores: Dict[str, Tuple[asyncio.Semaphore, int]] = {}
_max_concurrent: int =5


def init_semaphore(max_concurrent: int = 5):
    """
    semaphore config
    """
    global _semaphores, _max_concurrent
    _max_concurrent = max_concurrent
    _semaphores = {}


def get_semaphore(name: str) -> asyncio.Semaphore:
    """
    get semaphore instance by name
    """
    global _semaphores, _max_concurrent
    
    
    try:
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
    except RuntimeError:
        current_loop_id = None
    
    
    if name in _semaphores:
        semaphore, loop_id = _semaphores[name]
        if loop_id == current_loop_id:
            return semaphore
    
    
    new_semaphore = asyncio.Semaphore(_max_concurrent)
    _semaphores[name] = (new_semaphore, current_loop_id)
    return new_semaphore


def get_max_concurrent() -> int:
    """
    get max concurrent number
    """
    return _max_concurrent


async def run_with_semaphore(coro, semaphore: asyncio.Semaphore):
    """
    run coroutine with specified semaphore
    """
    async with semaphore:
        return await coro


async def gather_with_semaphore(*coros, name: str = "default", return_exceptions: bool = False):
    """
    run multiple coroutines with named semaphore
    """
    semaphore = get_semaphore(name)
    wrapped_coros = [run_with_semaphore(coro, semaphore) for coro in coros]
    return await asyncio.gather(*wrapped_coros, return_exceptions=return_exceptions)

