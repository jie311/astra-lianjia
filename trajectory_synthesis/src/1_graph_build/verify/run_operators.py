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

"""
Multi-process operator execution module - data dimension parallelism

Each operator executes sequentially, but processes multiple data entries in parallel on the data dimension

Usage:
    from run_operators import run_operators_on_dataset
    results = run_operators_on_dataset(data_list, operator_configs, n_processes=4)

Command line:
    python run_operators.py input.jsonl output.jsonl -p 4
"""

import argparse
import copy
import json
import sys
import traceback
from pathlib import Path
from typing import Dict, Any, List
from multiprocessing import Pool, cpu_count
from functools import partial
from tqdm import tqdm

# Add current directory to path
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

from operator_config import OPERATOR_CONFIGS


def _execute_single_operator_on_data(data: Dict[str, Any], operator_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Worker function to execute a single operator on a single data entry
    """
    try:
        operator_name = operator_config['name']
        operator_func = operator_config['func']
        api_config = operator_config['api_config']
        n_samples = operator_config.get('n_samples', 1)
        preview_prompt = operator_config.get('preview_prompt', False)
        
        # Merge n_samples and preview_prompt into api_config
        config = {**api_config, 'n_samples': n_samples, 'preview_prompt': preview_prompt}
        
        # Execute operator
        result = operator_func(data, config)
        
        return {
            'data': data,
            'operator_name': operator_name,
            'result': result,
            'status': 'success',
            'error': None
        }
    except Exception as e:
        return {
            'data': data,
            'operator_name': operator_config.get('name', 'unknown'),
            'result': None,
            'status': 'error',
            'error': str(e)
        }


def run_operators_on_dataset(data_list: List[Dict[str, Any]], 
                             operator_configs: List[Dict[str, Any]], 
                             n_processes: int = None) -> List[Dict[str, Any]]:
    """
    Execute multiple operators on dataset (each operator parallel on data dimension)
    
    Processing flow:
    1. Iterate through each operator sequentially
    2. For each operator, process all data in parallel
    3. Add results to each data entry's chain_info.operator_results field
    """
    if n_processes is None:
        n_processes = cpu_count()
    
    # Initialize results, add operator_results field to each data entry's chain_info
    results = []
    for data in data_list:
        result_data = data.copy()
        if 'chain_info' not in result_data:
            result_data['chain_info'] = {}
        if 'operator_results' not in result_data['chain_info']:
            result_data['chain_info']['operator_results'] = {}
        results.append(result_data)
    
    # Execute each operator sequentially
    for operator_config in tqdm(operator_configs, desc="Operator progress", unit="operator"):
        operator_name = operator_config['name']
        print(f"\n{'='*80}")
        print(f"Executing operator: {operator_name} (parallel processing {len(data_list)} data entries)")
        print(f"{'='*80}")
        
        # Preview prompt using first data entry
        if len(data_list) > 0:
            print(f"\n[Prompt preview] Using first data entry to preview prompt:")
            print(f"{'-'*80}")
            try:
                # Create a deep copy of config, add preview flag (avoid modifying original config)
                preview_config = copy.deepcopy(operator_config)
                preview_config['preview_prompt'] = True
                
                # Execute once in main process for preview
                preview_result = _execute_single_operator_on_data(
                    data_list[0], 
                    preview_config
                )
                print(f"{'-'*80}\n")
            except Exception as e:
                print(f"Preview failed: {e}")
                print(traceback.format_exc())
                print(f"{'-'*80}\n")
        
        # For current operator, process all data in parallel
        with Pool(processes=n_processes) as pool:
            execute_func = partial(_execute_single_operator_on_data, operator_config=operator_config)
            # Use imap_unordered with tqdm to show progress
            operator_results = list(tqdm(
                pool.imap(execute_func, data_list),
                total=len(data_list),
                desc=f"  Processing {operator_name}",
                unit="data entries"
            ))
        
        # Update operator results to corresponding data entry's chain_info.operator_results
        for i, op_result in enumerate(operator_results):
            if op_result['status'] == 'success':
                results[i]['chain_info']['operator_results'][operator_name] = op_result['result']
            else:
                results[i]['chain_info']['operator_results'][operator_name] = {
                    'error': op_result['error'],
                    'status': 'failed'
                }
    
    return results


def run_operators_from_jsonl(input_file: str, 
                              operator_configs: List[Dict[str, Any]], 
                              output_file: str, 
                              n_processes: int = None) -> None:
    """
    Read data from JSONL file, batch process and output
    
    Input data format: Each entry contains sub_chains field (multiple sub-chains)
    Output data format: Each sub_chain becomes one data entry, sub_chain info stored in chain_info field
    """
    # Read all data and split each sub_chain
    data_list = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    print("Reading and splitting data...")
    for line in tqdm(lines, desc="Reading data", unit="original entries"):
        if line.strip():
            original_data = json.loads(line)
            
            # Get sub_chains list
            sub_chains = original_data.get('graph', {}).get('sub_chains', [])
            
            if not sub_chains:
                print(f"Warning: Data missing sub_chains field, skipping: {original_data.get('mcp_info', {}).get('base_info', {}).get('group_info', {}).get('group_id', 'unknown')}")
                continue
            
            # Create new data entry for each sub_chain
            for sub_chain in sub_chains:
                # Copy original data structure
                new_data = {
                    'mcp_info': original_data.get('mcp_info', {}),
                    'graph': original_data.get('graph', {}),
                    'chain_info': {
                        'sub_chain': sub_chain
                    }
                }
                
                data_list.append(new_data)
    
    print(f"Read {len(lines)} original data entries")
    print(f"Split into {len(data_list)} sub_chain data entries")
    
    # Execute operators (data dimension parallel)
    results = run_operators_on_dataset(data_list, operator_configs, n_processes)
    
    # Write results
    with open(output_file, 'w', encoding='utf-8') as f:
        for result in tqdm(results, desc="Writing results", unit="entries"):
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    
    print(f"Results saved to: {output_file}")


def main():
    """
    Command line tool: Multi-process operator execution
    """
    parser = argparse.ArgumentParser(description='Multi-process operator execution')
    parser.add_argument('input', nargs='?', help='Input JSONL file path')
    parser.add_argument('output', nargs='?', help='Output JSONL file path')
    parser.add_argument('-p', '--processes', type=int, default=None, 
                        help='Number of processes (default is CPU core count)')
    parser.add_argument('-o', '--operators', nargs='+', default=None,
                        help='Specify operator names to execute (default executes all operators)')
    parser.add_argument('--show-operators', action='store_true',
                        help='Show all available operators')
    
    args = parser.parse_args()
    
    # Show available operators
    if args.show_operators:
        print("Available operators:")
        for name, config in OPERATOR_CONFIGS.items():
            print(f"  - {name}")
            print(f"    Function: {config['func'].__name__}")
            print(f"    Samples: {config.get('n_samples', 1)}")
        return
    
    # Check required parameters
    if not args.input or not args.output:
        parser.error("Input and output file paths are required (or use --show-operators to view operators)")
        return
    
    # Prepare operator configuration
    if args.operators:
        # Execute only specified operators
        operator_configs = []
        for op_name in args.operators:
            if op_name in OPERATOR_CONFIGS:
                operator_configs.append(OPERATOR_CONFIGS[op_name])
            else:
                print(f"Warning: Operator '{op_name}' does not exist, skipping")
    else:
        # Execute all operators
        operator_configs = list(OPERATOR_CONFIGS.values())
    
    if not operator_configs:
        print("Error: No operators to execute")
        return
    
    print(f"Input file: {args.input}")
    print(f"Output file: {args.output}")
    print(f"Executing operators: {[op['name'] for op in operator_configs]}")
    print(f"Processes: {args.processes or 'auto'}")
    print()
    
    # Execute batch processing
    try:
        run_operators_from_jsonl(
            input_file=args.input,
            operator_configs=operator_configs,
            output_file=args.output,
            n_processes=args.processes
        )
        print("✓ Processing complete!")
    except Exception as e:
        print(f"✗ Processing failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
