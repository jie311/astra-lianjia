#!/usr/bin/env python
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
import subprocess
import argparse
from pathlib import Path

from utils.multiprocess_inference import run_inference

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT = BASE_DIR / "src/utils/get_prompt_batch.py"

PROMPT_DIR = BASE_DIR / "data/prompt"

DEFAULT_MIN_HOPS = 3
DEFAULT_MAX_HOPS = 5
DEFAULT_NUM_REPEATS = 1
# Model name is required, no default value
DEFAULT_NUM_WORKERS = 4
DEFAULT_BATCH_SIZE = 4


def run_prompt_generation(prompt_type, output_dir, lang=None, knowledge=None, question=None, tool_doc=None, 
        min_h=DEFAULT_MIN_HOPS, max_h=DEFAULT_MAX_HOPS, repeats=DEFAULT_NUM_REPEATS, domain="general", mask_example=False):
    """
    Execute get_prompt_batch.py
    """
    cmd = ["python", str(SCRIPT), "--prompt_type", prompt_type, "--domain", domain,
           "--min_num_hops", str(min_h), "--max_num_hops", str(max_h), "--num_repeats", str(repeats)]
    
    if lang: cmd += ["--lang", lang]
    if knowledge: cmd += ["--knowledge_file", str(knowledge)]
    if question: cmd += ["--question_file", str(question)]
    if tool_doc: cmd += ["--tool_document_file", str(tool_doc)]
    if mask_example: cmd += ["--mask_example"]
    
    # Output filename
    suffix = f"{lang}_" if lang else ""
    suffix += f"{domain}_taxonomy_" if prompt_type == "taxonomy" else ""
    output = output_dir / f"{suffix}{prompt_type}_prompts.jsonl"
    cmd += ["--output", str(output)]
    
    return cmd, output


def get_generators(output_dir, num_repeats, min_hops, max_hops, lang=None, knowledge=None, question=None, tool_doc=None, domain="general", mask_example=False):
    """
    Get generator functions for different modes
    """
    zh_knowledge = knowledge if knowledge else BASE_DIR/"data/knowledge/zh/domains.jsonl"
    en_knowledge = knowledge if knowledge else BASE_DIR/"data/knowledge/en/domains.jsonl"
    en_question = question if question else BASE_DIR/"data/knowledge/en/questions.jsonl"
    
    return {
        "zh_kb": lambda: run_prompt_generation("base", output_dir, lang or "zh", knowledge=zh_knowledge, repeats=num_repeats, domain=domain, mask_example=mask_example),
        "zh_base": lambda: run_prompt_generation("base", output_dir, lang or "zh", repeats=num_repeats, domain=domain, mask_example=mask_example),
        "en": lambda: run_prompt_generation("base", output_dir, lang or "en", knowledge=en_knowledge, repeats=num_repeats, domain=domain, mask_example=mask_example),
        "en_base": lambda: run_prompt_generation("base", output_dir, lang or "en", repeats=num_repeats, domain=domain, mask_example=mask_example),
        "en_ctx": lambda: run_prompt_generation("hop_range", output_dir, lang or "en", knowledge=en_knowledge, min_h=min_hops, max_h=max_hops, repeats=num_repeats, domain=domain, mask_example=mask_example),
        "en_q": lambda: run_prompt_generation("by_question", output_dir, lang or "en", question=en_question, repeats=num_repeats, domain=domain, mask_example=mask_example),
        "tax": lambda: run_prompt_generation("taxonomy", output_dir, lang or "zh", domain=domain or "real_estate", mask_example=mask_example, repeats=num_repeats),
    }


def get_output_map():
    """
    Output file mapping for each mode
    """
    return {
        "zh_base": "zh_base_prompts.jsonl",
        "zh_kb": "zh_kb_prompts.jsonl",
        "en": "en_base_prompts.jsonl",
        "en_base": "en_base_prompts.jsonl",
        "en_ctx": "en_hop_range_prompts.jsonl",
        "en_q": "en_by_question_prompts.jsonl",
        "tax": "zh_real_estate_taxonomy_taxonomy_prompts.jsonl",
    }


def main():
    parser = argparse.ArgumentParser(description="Step 01: Generate QA data prompts and run inference")
    parser.add_argument("--mode", type=str, required=True, 
                        choices=["zh_kb", "zh_base", "en", "en_base", "en_ctx", "en_q", "tax", "all"],
                        help="Generation mode")
    parser.add_argument("--domain", type=str, default="general",
                        help="Domain (default: general)")
    parser.add_argument("--model_name", type=str, required=True,
                        help="Model name for inference (required)")
    parser.add_argument("--output_dir", type=str, required=True,
                        help="Output directory for generated files")
    parser.add_argument("--num_workers", type=int, default=DEFAULT_NUM_WORKERS,
                        help=f"Number of workers for inference (default: {DEFAULT_NUM_WORKERS})")
    parser.add_argument("--batch_size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Batch size for inference (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--min_hops", type=int, default=DEFAULT_MIN_HOPS,
                        help=f"Minimum number of hops (default: {DEFAULT_MIN_HOPS})")
    parser.add_argument("--max_hops", type=int, default=DEFAULT_MAX_HOPS,
                        help=f"Maximum number of hops (default: {DEFAULT_MAX_HOPS})")
    parser.add_argument("--num_repeats", type=int, default=DEFAULT_NUM_REPEATS,
                        help=f"Number of repeats (default: {DEFAULT_NUM_REPEATS})")
    parser.add_argument("--lang", type=str, default=None,
                        help="Language (zh/en). If not specified, uses mode default")
    parser.add_argument("--knowledge_file", type=str, default=None,
                        help="Path to knowledge corpus file")
    parser.add_argument("--question_file", type=str, default=None,
                        help="Path to question file")
    parser.add_argument("--tool_document_file", type=str, default=None,
                        help="Path to tool document file")
    parser.add_argument("--mask_example", action="store_true",
                        help="Mask example in prompt (default: False)")
    
    args = parser.parse_args()
    
    mode = args.mode
    model_name = args.model_name
    output_dir = Path(args.output_dir)
    num_workers = args.num_workers
    batch_size = args.batch_size
    min_hops = args.min_hops
    max_hops = args.max_hops
    num_repeats = args.num_repeats
    lang = args.lang
    knowledge = Path(args.knowledge_file) if args.knowledge_file else None
    question = Path(args.question_file) if args.question_file else None
    tool_doc = Path(args.tool_document_file) if args.tool_document_file else None
    domain = args.domain
    mask_example = args.mask_example
    
    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Get generators
    generators = get_generators(output_dir, num_repeats, min_hops, max_hops, 
                               lang=lang, knowledge=knowledge, question=question, 
                               tool_doc=tool_doc, domain=domain, mask_example=mask_example)
    output_map = get_output_map()
    
    # Generate prompts
    if mode in generators:
        cmd, output = generators[mode]()
        # Set environment variable to pass PROMPT_DIR
        env = os.environ.copy()
        env["PROMPT_DIR"] = str(PROMPT_DIR.resolve())
        print(f"Running: {mode} -> {output}")
        subprocess.run(cmd, env=env)
    elif mode == "all":
        for m in ["zh_base", "zh_kb", "en", "en_base", "en_q", "en_ctx", "tax"]:
            cmd, output = generators[m]()
            # Set environment variable to pass PROMPT_DIR
            env = os.environ.copy()
            env["PROMPT_DIR"] = str(PROMPT_DIR.resolve())
            print(f"Running: {m} -> {output}")
            subprocess.run(cmd, env=env)
    else:
        print(f"Available modes: {', '.join(generators.keys())}, all")
        return
    
    # Get output files based on mode
    def get_output_files():
        """
        Get output files based on mode
        """
        if mode == "all":
            return [output_dir / f for f in output_map.values()]
        return [output_dir / output_map.get(mode, "")] if mode in output_map else []
    
    # Run inference
    for prompt_file in get_output_files():
        if prompt_file.exists():
            result_file = prompt_file.with_name(prompt_file.stem.replace("_prompts", "_results") + ".jsonl")
            print(f"Inference: {prompt_file.name} -> {result_file.name}")
            run_inference(
                input_file=str(prompt_file),
                output_file=str(result_file),
                model=model_name,
                num_workers=num_workers,
                batch_size=batch_size
            )


if __name__ == "__main__":
    main()
