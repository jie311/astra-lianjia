#!/usr/bin/env python3
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

import json
import sys
import re
import uuid
from pathlib import Path
from multiprocessing import Pool
from tqdm import tqdm
from typing import List, Dict, Any
import argparse

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from api_client import get_openai_model_ans
from api_config import API_CONFIGS
import os


def process_single_prompt(args):
    """
    Process single prompt
    """
    item, config = args
    
    try:
        messages = [{"role": "user", "content": item["prompt"]}]
        # messages = item["prompt"]
        result = get_openai_model_ans(messages, config, tmp_debug=False)
        
        return {
            "index": item.get("index", 0),
            "params": item.get("params", {}),
            "prompt": item["prompt"],
            "response": result["response"],
            "reasoning_content": result["reasoning_content"]
        }
        
    except Exception as e:
        return {
            "index": item.get("index", 0),
            "params": item.get("params", {}),
            "prompt": item["prompt"],
            "response": None,
            "reasoning_content": None,
            "error": str(e)
        }


def _parse_json_list(string: str) -> List[Dict]:
    """
    Parse JSON list returned by LLM, supports:
    1. Remove think tags
    2. Remove markdown code block markers
    3. Return parsed list
    """
    think_content = None
    string = string.strip()
    
    # Remove think tags
    if "</think>" in string:
        think_content, sub_string = string.rsplit("</think>", 1)
        string = sub_string.strip()

    # Remove markdown code block markers
    string = string.strip()
    if string.startswith("```json"):
        string = string[len("```json"):].strip()
    elif string.startswith("```"):
        string = string[len("```"):].strip()
    if string.endswith("```"):
        string = string[:-len("```")].strip()
    
    try:
        result = json.loads(string)
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            # If returned as single object, wrap in list
            return [result]
        else:
            print(f"[WARNING] Unexpected JSON type: {type(result)}")
            return []
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parse error: {e}")
        print(f"[DEBUG] Raw string (first 100 chars and last 100 chars): {string[:100]}...{string[-100:]}")
        
        # Try to extract JSON array
        match = re.search(r"\[.*\]", string, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        return []


def _build_metadata(
    *,
    domain: str,
    knowledge_corpus: str,
    lang: str,
    model_name: str,
    num_hops: int = None,
    min_num_hops: int = None,
    max_num_hops: int = None,
) -> Dict[str, Any]:
    """
    Build metadata (compatible with fixed hops and range hops)
    """
    metadata = {
        "domain": domain,
        "language": lang,
        "knowledge_corpus": knowledge_corpus if knowledge_corpus else None,
        "model_name": model_name,
    }
    
    # Add hop info based on parameter type
    if num_hops is not None:
        metadata["num_hops"] = num_hops
    if min_num_hops is not None and max_num_hops is not None:
        metadata["min_num_hops"] = min_num_hops
        metadata["max_num_hops"] = max_num_hops
    
    return metadata


def post_process_file(input_file: str, output_file: str, model_name: str):
    """
    Post-processing function: Read all_results.jsonl format file, parse response field, extract metadata
    """
    print(f"Post-processing {input_file} -> {output_file}")
    
    results = []
    error_count = 0
    
    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            
            try:
                # Read raw data
                data = json.loads(line)
                response = data.get("response", "")
                params = data.get("params", {})
                
                # Parse JSON list in response
                parsed_items = _parse_json_list(response)
                
                # Extract metadata from params (compatible with fixed hops and range hops formats)
                metadata = _build_metadata(
                    domain=params.get("domain", "unknown"),
                    knowledge_corpus=params.get("knowledge_corpus", ""),
                    lang=params.get("lang", "unknown"),
                    model_name=model_name,
                    num_hops=params.get("num_hops"),
                    min_num_hops=params.get("min_num_hops"),
                    max_num_hops=params.get("max_num_hops"),
                )
                
                # Add uuid and metadata to each parsed item
                for item in parsed_items:
                    results.append({
                        "uuid": str(uuid.uuid4()),
                        **item,
                        "_metadata": metadata,
                    })
                    
            except Exception as e:
                error_count += 1
                print(f"[ERROR] Line {line_num}: {e}")
    
    # Statistics for each metric:
    count_hop_level = {}
    count_node = {}
    # Write to output file
    with open(output_file, "w", encoding="utf-8") as f:
        for item in tqdm(results):
            try:
                max_hop_level = 0
                if "decomposition_trace" in item:
                    for trace in item["decomposition_trace"]:
                        max_hop_level = max(max_hop_level, trace["hop_level"])
                    count_hop_level[max_hop_level] = count_hop_level.get(max_hop_level, 0) + 1
                    count_node[len(item["decomposition_trace"])] = count_node.get(len(item["decomposition_trace"]), 0) + 1
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
            except Exception as e:
                print(f"[ERROR] Line {line_num}: {e}")
    print(f"count_hop_level: {count_hop_level}")
    print(f"count_node: {count_node}")
    print(f"Processed {len(results)} items, {error_count} errors")
    return results


def run_inference(input_file: str, output_file: str, model: str, 
                  num_workers: int = 4, batch_size: int = 100):
    """
    Execute multi-process inference (can be called directly)
    """
    # Load input data
    print(f"Loading {input_file}...")
    data = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    
    print(f"Loaded {len(data)} records")
    
    # Load completed prompts
    processed_prompts = set()
    if os.path.exists(output_file):
        print(f"Loading existing results from {output_file}...")
        with open(output_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    result = json.loads(line)
                    processed_prompts.add(result.get("prompt", ""))
        print(f"Found {len(processed_prompts)} already processed records")
    
    # Filter out unprocessed data
    remaining_data = [item for item in data if item.get("prompt", "") not in processed_prompts]
    print(f"Remaining records to process: {len(remaining_data)}")
    
    if not remaining_data:
        print("All records already processed!")
    else:
        print(f"Using {num_workers} workers, model: {model}")
        print(f"Batch write size: {batch_size}")
        
        # Prepare tasks
        config = API_CONFIGS[model]
        tasks = [(item, config) for item in remaining_data]
        
        # Execute inference and batch write (append mode)
        with open(output_file, "a", encoding="utf-8") as f:
            with Pool(processes=num_workers) as pool:
                batch = []
                for result in tqdm(pool.imap_unordered(process_single_prompt, tasks), 
                                total=len(tasks), desc="Processing"):
                    batch.append(result)
                    
                    # Write when batch_size is reached
                    if len(batch) >= batch_size:
                        for item in batch:
                            f.write(json.dumps(item, ensure_ascii=False) + "\n")
                        f.flush()  # Flush to disk
                        batch = []
                
                # Write remaining records
                if batch:
                    for item in batch:
                        f.write(json.dumps(item, ensure_ascii=False) + "\n")
        
        print(f"\nDone! Results appended to {output_file}")
    
    # Auto execute post-processing
    print("\n" + "="*50)
    print("Starting post-processing...")
    print("="*50)
    
    # Generate processed filename
    output_path = Path(output_file)
    processed_file = output_path.parent / f"{output_path.stem}_processed{output_path.suffix}"
    
    post_process_file(output_file, str(processed_file), model)
    print(f"\nAll done! Final results saved to {processed_file}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_file", type=str, required=True)
    parser.add_argument("--output_file", type=str, required=True)
    parser.add_argument("--model", type=str, required=True, help="Model name (required)")
    parser.add_argument("--num_workers", type=int, default=4)
    parser.add_argument("--batch_size", type=int, default=100, help="Number of records to write per batch")
    args = parser.parse_args()
    
    run_inference(args.input_file, args.output_file, args.model, args.num_workers, args.batch_size)


if __name__ == "__main__":
    main()