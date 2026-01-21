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

import os
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '../..'))
sys.path.insert(0, SRC_ROOT)
from utils.utils import multi_call


def process_raw_func(response):
    """
    Process raw response, remove messages field
    """
    raw_output = response.copy()
    raw_output.pop("messages", None)
    return raw_output


def gen(inp_file, out_file_raw, out_file_parsed, pool_size, model):
    """
    Generate scores (supports checkpoint resume)
    """
    # Read input data
    inp_list = []
    with open(inp_file, 'r', encoding='utf-8') as f:
        for line in f:
            data = json.loads(line)
            inp_list.append(data)
    
    print(f"Original input data: {len(inp_list)} entries")
    
    # Checkpoint resume: check already processed data
    processed_ids = set()
    append_mode = False
    
    if os.path.exists(out_file_raw):
        print(f"Detected existing output file, loading processed records...")
        try:
            with open(out_file_raw, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if 'metadata' in data and 'prompt_id' in data['metadata']:
                            processed_ids.add(data['metadata']['prompt_id'])
                    except json.JSONDecodeError:
                        continue
            print(f"Already processed: {len(processed_ids)} records")
            append_mode = True  # Has processed data, use append mode
        except Exception as e:
            print(f"Error reading processed records: {e}, will start from beginning")
            processed_ids = set()
            append_mode = False
    
    # Filter out already processed data
    if processed_ids:
        inp_list = [
            data for data in inp_list 
            if data.get('metadata', {}).get('prompt_id') not in processed_ids
        ]
        print(f"To be processed: {len(inp_list)} records")
    
    if len(inp_list) == 0:
        print("All data has been processed, no need to continue")
        return
    
    # Use multi_call function from utils
    multi_call(
        inp_list=inp_list,
        out_file_raw=out_file_raw,
        out_file_parsed=out_file_parsed,
        pool_size=pool_size,
        model=model,
        parse_func=None,  
        process_raw_func=process_raw_func,
        append_mode=append_mode  
    )


def main():
    parser = argparse.ArgumentParser(description='Generate query quality scores')
    parser.add_argument('--model', required=True, help='Model name (configured in api_config.py)')
    parser.add_argument('--inp_file', required=True, help='Input file path (*_prepared.jsonl)')
    parser.add_argument('--out_file_raw', required=True, help='Raw output file path (.jsonl)')
    parser.add_argument('--out_file_parsed', required=True, help='Parsed output file path (.jsonl, but not used)')
    parser.add_argument('--pool_size', type=int, default=128, help='Parallelism')
    
    args = parser.parse_args()
    
    gen(args.inp_file, args.out_file_raw, args.out_file_parsed, args.pool_size, args.model)


if __name__ == '__main__':
    main()
