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

from openai import AsyncOpenAI, OpenAI
import json
from tqdm import tqdm
import re
import asyncio
from typing import List, Dict, Any, Callable, Optional
from multiprocessing import Process, Queue, Pool, cpu_count
import math

from .api_config import API_CONFIGS


# ==================== Multi-process Sync API Call Related ====================
# Global variables (for multiprocessing worker)
_global_client = None
_global_config = {}


def parse_response(response_obj, content):
    """
    Parse model response, handling three cases:
    1. Reasoning model: API returns with reasoning_content field
    2. Reasoning model: Thinking process and answer separated by <think> tag in content
    3. Regular model: Returns answer directly
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


async def openai_call_async(input: Dict[str, Any], api_config: Dict[str, Any] = None, semaphore: asyncio.Semaphore = None, client: AsyncOpenAI = None) -> Dict[str, Any]:
    """
    Async OpenAI API call
    """
    
    # Merge default configuration
    config = {**api_config}
    
    # Use semaphore for concurrency control
    if semaphore:
        async with semaphore:
            return await _do_openai_call(input, config, client)
    else:
        return await _do_openai_call(input, config, client)


async def _do_openai_call(input: Dict[str, Any], config: Dict[str, Any], client: AsyncOpenAI = None) -> Dict[str, Any]:
    """
    Execute actual API call (streaming version)
    """
    should_close_client = False
    try:
        # Create new client if not passed in (backward compatibility)
        if client is None:
            client = AsyncOpenAI(
                base_url=config["base_url"],
                api_key=config["api_key"]
            )
            should_close_client = True
        
        # Build request parameters
        request_params = {
            "model": config["model"],
            "max_tokens": config["max_tokens"],
            "temperature": config["temperature"],
            "frequency_penalty": 0.1,
            "presence_penalty": 0,
            "messages": input["messages"],
            "stream": True  # Enable streaming response
        }
        
        # Add extra_body parameters
        if config.get("extra_body"):
            request_params["extra_body"] = config["extra_body"]
        
        # Stream response
        stream = await client.chat.completions.create(**request_params)
        
        # Collect streaming response content
        content_chunks = []
        reasoning_chunks = []
        
        async for chunk in stream:
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                
                # Collect regular content
                if hasattr(delta, 'content') and delta.content:
                    content_chunks.append(delta.content)
                
                # Collect reasoning content (if any)
                if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                    reasoning_chunks.append(delta.reasoning_content)
        
        # Merge all chunks
        content = ''.join(content_chunks)
        reasoning_content = ''.join(reasoning_chunks) if reasoning_chunks else None
        
        # Parse response, handle three different model cases
        result = {
            "answer": content,
            "reasoning": None
        }
        
        # Case 1: Streaming response has reasoning_content
        if reasoning_content:
            result["reasoning"] = reasoning_content
            result["answer"] = content
        else:
            # Case 2: Check if content contains <think> tag
            think_pattern = r'<think>(.*?)</think>(.*)'
            match = re.search(think_pattern, content, re.DOTALL)
            if match:
                result["reasoning"] = match.group(1).strip()
                result["answer"] = match.group(2).strip()
            # Case 3: Regular model, use content as answer directly (already set in initialization)
        
        # Save raw response and parsed result
        input["response"] = content  # Raw response content
        input["answer"] = result["answer"]  # Parsed answer
        
        # Save reasoning if available
        if result["reasoning"]:
            input["reasoning"] = result["reasoning"]
        
        # Only close client if created in this function
        if should_close_client:
            await client.close()
            
    except Exception as ex:
        print(f"Error: {ex}")
        input["response"] = f'error msg: {str(ex)}'
        input["answer"] = f'error msg: {str(ex)}'
    
    return input


def openai_call(input: Dict[str, Any], api_config: Dict[str, Any]=None, semaphore: asyncio.Semaphore=None):
    """
    Sync OpenAI API call
    """
    return asyncio.run(openai_call_async(input, api_config, semaphore))


async def async_call(inp_list: List[Dict[str, Any]], out_file: str, api_config: Dict[str, Any] = None, max_concurrent: int = 32) -> None:
    """
    Async model call (using asyncio, streaming version)
    """

    
    num_rows = len(inp_list)
    print(f"Total {num_rows} records to process, max concurrency: {max_concurrent}")
    
    # Create shared client for connection reuse
    client = AsyncOpenAI(
        base_url=api_config["base_url"],
        api_key=api_config["api_key"]
    )
    
    try:
        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)
        
        # Create all tasks with shared client
        tasks = [openai_call_async(input_data.copy(), api_config, semaphore, client) for input_data in inp_list]
        
        # Use asyncio.as_completed with tqdm for progress display
        with open(out_file, 'w', encoding='utf-8') as f:
            for coro in tqdm(asyncio.as_completed(tasks), total=num_rows, desc="Completed samples"):
                result = await coro
                # Remove messages when saving to save space
                if "messages" in result:
                    result.pop("messages")
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()  # Write in real-time
        
        print(f"Processing complete, results saved to {out_file}")
    finally:
        # Ensure client is properly closed
        await client.close()


def run_async_call(inp_list: List[Dict[str, Any]], out_file: str, api_config: Dict[str, Any] = None, max_concurrent: int = 32) -> None:
    """
    Sync wrapper for non-async environment (pure async mode)
    """
    asyncio.run(async_call(inp_list, out_file, api_config, max_concurrent))


def _process_worker(process_id: int, inp_chunk: List[Dict[str, Any]], api_config: Dict[str, Any], max_concurrent: int, result_queue: Queue) -> None:
    """
    Process worker function: Each process uses async calls internally and returns results in streaming fashion
    """
    async def process_chunk():
        # Create shared client for connection reuse
        client = AsyncOpenAI(
            base_url=api_config["base_url"],
            api_key=api_config["api_key"]
        )
        
        try:
            semaphore = asyncio.Semaphore(max_concurrent)
            tasks = [openai_call_async(input_data.copy(), api_config, semaphore, client) for input_data in inp_chunk]
            
            # Streaming: Return result immediately upon task completion
            for coro in asyncio.as_completed(tasks):
                result = await coro
                if "messages" in result:
                    result.pop("messages")
                # Put result in queue immediately instead of waiting for all tasks
                result_queue.put((process_id, result))
        finally:
            # Ensure client is properly closed
            await client.close()
    
    # Run async task in process
    asyncio.run(process_chunk())


def multi_process_async_call(
    inp_list: List[Dict[str, Any]], 
    out_file: str, 
    api_config: Dict[str, Any] = None, 
    num_processes: int = None,
    max_concurrent_per_process: int = 32
) -> None:
    """
    Multi-process + async hybrid mode model call (optimized version)
    
    This mode combines advantages of multi-process and async:
    - Multi-process: Fully utilize multi-core CPU, avoid GIL limitation
    - Async: Efficiently handle I/O-intensive API calls within each process
    - Connection reuse: Each process creates one shared client for TCP connection reuse
    - Streaming: Results returned and written in real-time, no waiting for batch completion
    """
    if num_processes is None:
        # Default to CPU core count but cap at 16 (too many processes reduce performance for I/O-intensive tasks)
        num_processes = min(cpu_count(), 16)
    
    total_items = len(inp_list)
    print(f"Total {total_items} records to process")
    print(f"Using {num_processes} processes, max concurrency per process: {max_concurrent_per_process}")
    print(f"Total concurrency capacity: {num_processes * max_concurrent_per_process}")
    
    # Split data into chunks for different processes
    chunk_size = math.ceil(total_items / num_processes)
    chunks = [inp_list[i:i + chunk_size] for i in range(0, total_items, chunk_size)]
    
    # Create result queue
    result_queue = Queue()
    
    # Create and start processes
    processes = []
    for i, chunk in enumerate(chunks):
        if chunk:  # 确保chun
            p = Process(target=_process_worker, args=(i, chunk, api_config, max_concurrent_per_process, result_queue))
            p.start()
            processes.append(p)
    
    # Stream collect results and write to file
    # Now each result is returned individually, not in batches
    result_count = 0
    with open(out_file, 'w', encoding='utf-8') as f:
        with tqdm(total=total_items, desc="Completed samples") as pbar:
            # Continuously get results from queue until all tasks complete
            while result_count < total_items:
                process_id, result = result_queue.get()
                # Write result immediately
                f.write(json.dumps(result, ensure_ascii=False) + '\n')
                f.flush()  # Ensure data is written to disk promptly
                result_count += 1
                pbar.update(1)
    
    # Wait for all processes to complete
    for p in processes:
        p.join()
    
    print(f"Processing complete! Total {result_count} records processed, results saved to {out_file}")


# Generate report from final sub_chain result file
def sub_chain_extract_report(inp_file):
    """
    Analyze sub_chains result file and generate statistics report
    """
    import json
    from collections import Counter
    
    data_list = []
    with open(inp_file, 'r', encoding='utf-8') as f:
        data_list = [json.loads(line) for line in f if line.strip()]
    
    # Extract chains and sub_chains, support both new and old formats
    all_chains = []
    all_sub_chains = []
    
    for d in data_list:
        # New format: Data under graph field
        if 'graph' in d:
            graph = d.get('graph', {})
            all_chains.extend(graph.get('graph_detect', []))
            all_sub_chains.extend(graph.get('sub_chains', []))
        # Old format: Data at top level
        else:
            all_chains.extend(d.get('chains', []))
            all_sub_chains.extend(d.get('sub_chains', []))
    
    # Count lengths
    chain_lens = [len(c.get('tool_graph_detect_chain', [])) if isinstance(c, dict) else len(c) for c in all_chains]
    sub_chain_lens = [len(sc) for sc in all_sub_chains]
    
    report = {
        "chains_count": len(all_chains),
        "chains_length_distribution": dict(sorted(Counter(chain_lens).items())),
        "sub_chains_count": len(all_sub_chains),
        "sub_chains_length_distribution": dict(sorted(Counter(sub_chain_lens).items())),
    }
    
    print(f"\n{'='*60}\nSub Chains Extraction Report\n{'='*60}")
    print(f"chains_count: {report['chains_count']}")
    print(f"chains_length_distribution: {report['chains_length_distribution']}")
    print(f"sub_chains_count: {report['sub_chains_count']}")
    print(f"sub_chains_length_distribution: {report['sub_chains_length_distribution']}")
    print(f"{'='*60}\n")
    
    return report


# ==================== Multi-process Sync API Call (for task_construction pipeline) ====================
def _parse_response_sync(response_obj, content: str) -> Dict[str, Any]:
    """
    Parse response, extract reasoning and answer (sync version for multi-process)
    """
    result = {"answer": content, "reasoning": None}
    
    # Case 1: API returns with reasoning_content field
    try:
        if hasattr(response_obj.choices[0].message, 'reasoning_content'):
            reasoning = response_obj.choices[0].message.reasoning_content
            if reasoning:
                result["reasoning"] = reasoning
                return result
    except Exception:
        pass
    
    # Case 2: Content contains <think> tag
    match = re.search(r'<think>(.*?)</think>(.*)', content, re.DOTALL)
    if match:
        result["reasoning"] = match.group(1).strip()
        result["answer"] = match.group(2).strip()
    
    return result


def _openai_call_sync(input_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    OpenAI API sync call (for multiprocessing worker) - supports streaming output
    """
    global _global_client, _global_config
    
    # Initialize client in subprocess
    if _global_client is None:
        _global_client = OpenAI(
            base_url=_global_config['base_url'],
            api_key=_global_config['api_key']
        )
    
    try:
        # Build API parameters
        params = {
            "model": _global_config['model'],
            "messages": input_data["messages"],
            "max_tokens": _global_config['max_tokens'],
            "temperature": _global_config['temperature'],
            "stream": True,
            "n": 1
        }
        if _global_config.get('extra_body'):
            params['extra_body'] = _global_config['extra_body']
        
        # Stream API call and accumulate content
        response_stream = _global_client.chat.completions.create(**params)
        content = ""
        for chunk in response_stream:
            if chunk.choices[0].delta.content:
                content += chunk.choices[0].delta.content
        
        # Parse response
        parsed = _parse_response_sync(response_stream, content)
        input_data["response"] = parsed["answer"]
        if parsed["reasoning"]:
            input_data["reasoning"] = parsed["reasoning"]
            
    except Exception as ex:
        print(f"API call failed: {ex}")
        input_data["response"] = f'error msg: {str(ex)}'
    
    return input_data


def multi_call(
    inp_list: List[Dict[str, Any]],
    out_file_raw: str,
    out_file_parsed: str,
    pool_size: int,
    model: str,
    parse_func: Optional[Callable] = None,
    process_raw_func: Optional[Callable] = None,
    append_mode: bool = True
) -> Dict[str, int]:
    """
    Multi-process API call (supports checkpoint resume)
    """
    global _global_config
    
    # Get model configuration from api_config
    if model not in API_CONFIGS:
        raise ValueError(f"Model '{model}' not configured in api_config.py, available models: {list(API_CONFIGS.keys())}")
    
    config = API_CONFIGS[model]
    
    # Set global configuration (for multi-process worker)
    _global_config = {
        'base_url': config['base_url'],
        'api_key': config['api_key'],
        'model': config['model'],
        'max_tokens': config.get('max_tokens', 32000),
        'temperature': config.get('temperature', 0.6),
        'stream': config.get('stream', False),
        'extra_body': config.get('extra_body', {})
    }
    
    pool = Pool(pool_size)
    total, success = 0, 0
    
    print(f"Total: {len(inp_list)}, Model: {model}, Concurrency: {pool_size}")
    
    # Choose file open mode based on append_mode
    file_mode = 'a' if append_mode else 'w'
    
    with open(out_file_raw, file_mode, encoding='utf-8') as f_raw, \
         open(out_file_parsed, file_mode, encoding='utf-8') as f_parsed:
        
        for response in tqdm(pool.imap_unordered(_openai_call_sync, inp_list, chunksize=3),
                            total=len(inp_list), mininterval=1, maxinterval=10):
            
            # Write raw response
            raw_output = process_raw_func(response) if process_raw_func else response.copy()
            if not process_raw_func:
                raw_output.pop("messages", None)
            f_raw.write(json.dumps(raw_output, ensure_ascii=False) + '\n')
            f_raw.flush()
            total += 1
            
            # Parse and write
            if parse_func:
                parsed = parse_func(response)
                if parsed:
                    results = parsed if isinstance(parsed, list) else [parsed]
                    for result in results:
                        if result:
                            f_parsed.write(json.dumps(result, ensure_ascii=False) + '\n')
                            f_parsed.flush()
                            success += 1
    
    pool.close()
    pool.join()
    
    print(f"Complete - Total: {total}, Success: {success}")
    return {"total": total, "success": success}
