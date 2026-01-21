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
import os
import random
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from multiprocessing import Pool, cpu_count
from functools import partial

import sys
# Get src directory (parent of utils)
SRC_ROOT = Path(__file__).resolve().parent.parent
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from utils.domain_config import get_domain_config

PROJECT_ROOT = SRC_ROOT.parent
PROMPT_DIR = Path(os.environ.get("PROMPT_DIR", PROJECT_ROOT / "data/prompt"))
ENV_DIR = Path(os.environ.get("ENV_DIR", PROJECT_ROOT / "data/env"))
from tqdm import tqdm


def load_prompt_template(prompt_type: str, lang: str = "zh") -> str:
    """
    Load prompt template
    """
    templates = {
        "base": "gen_QA_zh_no_parallel.md" if lang == "zh" else "gen_QA_en_no_parallel.md",
        "by_question": "gen_QA_zh_by_Q.md" if lang == "zh" else "gen_QA_en_by_Q.md",
        "hop_range": "gen_QA_zh_hop_range.md" if lang == "zh" else "gen_QA_en_hop_range.md",
        "aug_env_base": "aug_ENV_zh_base.md" if lang == "zh" else "aug_ENV_en_base.md",
        "aug_env_call_state": "aug_ENV_zh_call_state.md" if lang == "zh" else "aug_ENV_en_call_state.md",
        "aug_env_call_state_loose": "aug_ENV_zh_call_state_loose.md" if lang == "zh" else "aug_ENV_en_call_state_loose.md",
        "aug_env_tool_name": "aug_ENV_zh_tool_name.md" if lang == "zh" else "aug_ENV_en_tool_name.md",
    }
    filename = templates.get(prompt_type, templates["base"])
    filepath = PROMPT_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return f.read()


def load_repeat_weight_dict(weight_file: Optional[str] = None) -> Dict[int, int]:
    """
    Load repeat_weight configuration
    """
    if weight_file is None:
        weight_file = str(ENV_DIR / "repeat_weight.txt")
    
    weight_dict = {}
    with open(weight_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split()
                if len(parts) >= 2:
                    weight_dict[int(parts[0])] = int(parts[1])
    return weight_dict


def _extract_leaves(node: Any, path: List[str]) -> List[Dict[str, Any]]:
    """
    Recursively extract leaf nodes
    """
    leaves = []
    if isinstance(node, dict):
        if "description" in node and "examples" in node:
            leaves.append({
                "path": path,
                "description": node.get("description", ""),
                "examples": node.get("examples", []),
            })
        else:
            for key, value in node.items():
                if isinstance(value, dict):
                    leaves.extend(_extract_leaves(value, path + [key]))
                elif isinstance(value, list):
                    for item in value:
                        if isinstance(item, dict):
                            leaves.extend(_extract_leaves(item, path + [key]))
    return leaves


def load_taxonomy_leaves(taxonomy_path: Optional[str]) -> List[Dict[str, Any]]:
    """
    Load taxonomy and return list of leaf nodes
    """
    if not taxonomy_path:
        return []
    try:
        with open(taxonomy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _extract_leaves(data, [])
    except Exception as e:
        print(f"[WARNING] Failed to load taxonomy: {e}")
        return []


def _format_leaf_info(base_domain: str, leaf: Dict[str, Any], mask_example: bool = False) -> Tuple[str, str]:
    """
    Build Domain and Knowledge_Corpus based on leaf node
    """
    domain_path = "-".join([base_domain] + leaf.get("path", []))
    examples = leaf.get("examples") or []
    example_query = ""
    
    if not mask_example or random.random() >= 0.5:
        if examples:
            sampled = random.choice(examples)
            example_query = sampled.get("query", "") if isinstance(sampled, dict) else sampled
    
    corpus_dict = {
        "description": leaf.get("description", ""),
        "example_query": example_query,
    }
    return domain_path, json.dumps(corpus_dict, ensure_ascii=False)


def build_prompt(params: Dict[str, Any]) -> str:
    """
    Build a single prompt
    """
    template = load_prompt_template(params["prompt_type"], params.get("lang", "zh"))
    
    prompt = template.replace("{{Domain}}", params["domain"])
    prompt = prompt.replace("{{Knowledge_Corpus}}", params.get("knowledge_corpus", ""))
    if params.get("num_hops", 2) != -1:
        prompt = prompt.replace("{{num_hops}}", str(params.get("num_hops", 2)))
    # Generate 1 sample each time
    prompt = prompt.replace("{{num_samples}}", "1")
    
    if params["prompt_type"] == "by_question":
        prompt = prompt.replace("{{Question}}", params.get("question", ""))
    
    if params["prompt_type"] == "hop_range":
        prompt = prompt.replace("{{min_num_hops}}", str(params.get("min_num_hops", 2)))
        prompt = prompt.replace("{{max_num_hops}}", str(params.get("max_num_hops", 8)))
    
    return prompt


def build_prompt_for_env_aug(params: Dict[str, Any]) -> str:
    """
    Build a single prompt for environment augmentation
    """

    template = load_prompt_template(params["prompt_type"], params.get("lang", "zh"))
    
    domain = str(params["domain"]) if params.get("domain") else ""
    knowledge_corpus = str(params.get("knowledge_corpus", "")) if params.get("knowledge_corpus") else ""
    
    tool_documents = params.get("tool_document", "")
    if isinstance(tool_documents, tuple):
        tool_documents = list(tool_documents)
    if isinstance(tool_documents, (dict, list)):
        tool_doc_str = json.dumps(tool_documents, ensure_ascii=False, indent=2)
    elif isinstance(tool_documents, str):
        tool_doc_str = tool_documents
    else:
        tool_doc_str = ""
    
    prompt = template.replace("{{Domain}}", domain)
    prompt = prompt.replace("{{Knowledge_Corpus}}", knowledge_corpus)

    if params["prompt_type"] == "aug_env_call_state_loose":
        prompt = prompt.replace("{{min_num_hops}}", str(params.get("min_num_hops", 3)))
        prompt = prompt.replace("{{max_num_hops}}", str(params.get("max_num_hops", 10)))
    else:
        prompt = prompt.replace("{{num_hops}}", str(params.get("num_hops", 2)))
    prompt = prompt.replace("{{num_samples}}", "1")
    prompt = prompt.replace("{{Tool_Document}}", tool_doc_str)
    return prompt


def prepare_prompts_for_env_aug_base(
    prompt_type: str,
    domain: str,
    num_hops: int,
    num_repeats: int,
    repeat_weight_dict: Dict[int, int],
    knowledge_corpus: str = "",
    tool_documents: Optional[List[Dict[str, Any]]] = None,
    tool_document_file: str = "",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts for environment augmentation base
    """
    prompts = []
    
    if tool_document_file:
        tool_documents = []
        with open(tool_document_file, "r", encoding="utf-8") as f:
            for line in tqdm(f):
                line = line.strip()
                if line:
                    tool_documents.append(json.loads(line))
    
    if not tool_documents:
        return prompts
    
    for tool_doc_item in tqdm(tool_documents):
        doc_domain = tool_doc_item.get("domain", domain)
        tool_docs = tool_doc_item.get("tool_documents", [])
        tool_docs_len = tool_doc_item.get("tool_documents_len", len(tool_docs))
        
        dynamic_repeats = repeat_weight_dict.get(tool_docs_len, num_repeats)
        
        for lang in ["zh", "en"]:
            for i in range(dynamic_repeats):
                params = {
                    "prompt_type": prompt_type,
                    "domain": doc_domain,
                    "knowledge_corpus": knowledge_corpus,
                    "num_hops": num_hops,
                    "lang": lang,
                    "tool_document": tool_docs,
                }
                prompt = build_prompt_for_env_aug(params)
                prompts.append({
                    "prompt": prompt,
                    "params": params,
                    "index": i + 1,
                })
    return prompts


def prepare_prompts_for_env_aug_call_state(
    prompt_type: str,
    domain: str,
    num_hops: int,
    num_repeats: int,
    repeat_weight_dict: Dict[int, int],
    knowledge_corpus: str = "",
    tool_documents: Optional[List[Dict[str, Any]]] = None,
    tool_document_file: str = "",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts for environment augmentation call state
    """
    prompts = []
    
    if tool_document_file:
        tool_documents = []
        with open(tool_document_file, "r", encoding="utf-8") as f:
            for line in tqdm(f):
                line = line.strip()
                if line:
                    tool_documents.append(json.loads(line))
    
    if not tool_documents:
        return prompts
    
    for tool_doc_item in tqdm(tool_documents):
        doc_domain = tool_doc_item.get("domain", domain)
        tool_docs = tool_doc_item.get("tool_documents", [])
        tool_docs_len = tool_doc_item.get("tool_documents_len", len(tool_docs))
        
        dynamic_repeats = repeat_weight_dict.get(tool_docs_len, num_repeats)
        
        for lang in ["zh", "en"]:
            for i in range(dynamic_repeats):
                params = {
                    "prompt_type": prompt_type,
                    "domain": doc_domain,
                    "knowledge_corpus": knowledge_corpus,
                    "num_hops": num_hops,
                    "lang": lang,
                    "tool_document": tool_docs,
                }
                prompt = build_prompt_for_env_aug(params)
                prompts.append({
                    "prompt": prompt,
                    "params": params,
                    "index": i + 1,
                })
    return prompts


def prepare_prompts_for_env_aug_call_state_loose(
    prompt_type: str,
    domain: str,
    min_hops: int,
    max_hops: int,
    num_repeats: int,
    repeat_weight_dict: Dict[int, int],
    knowledge_corpus: str = "",
    tool_documents: Optional[List[Dict[str, Any]]] = None,
    tool_document_file: str = "",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts for environment augmentation call state loose
    """
    prompts = []
    
    if tool_document_file:
        tool_documents = []
        with open(tool_document_file, "r", encoding="utf-8") as f:
            for line in tqdm(f):
                line = line.strip()
                if line:
                    tool_documents.append(json.loads(line))
    
    if not tool_documents:
        return prompts
    
    for tool_doc_item in tqdm(tool_documents):
        doc_domain = tool_doc_item.get("domain", domain)
        tool_docs = tool_doc_item.get("tool_documents", [])
        tool_docs_len = tool_doc_item.get("tool_documents_len", len(tool_docs))
        
        dynamic_repeats = repeat_weight_dict.get(tool_docs_len, num_repeats)
        
        for i in range(dynamic_repeats*num_repeats):
            # Randomly sample language, zh to en ratio is 2:8
            lang = random.choices(["zh", "en"], weights=[0.2, 0.8], k=1)[0]
            params = {
                "prompt_type": prompt_type,
                "domain": doc_domain,
                "knowledge_corpus": knowledge_corpus,
                "min_num_hops": min_hops,
                "max_num_hops": max_hops,
                "lang": lang,
                "tool_document": tool_docs,
            }
            prompt = build_prompt_for_env_aug(params)
            prompts.append({
                "prompt": prompt,
                "params": params,
                "index": i + 1,
            })
    return prompts


def prepare_prompts_for_env_aug_tool_name(
    prompt_type: str,
    domain: str,
    num_hops: int,
    num_repeats: int,
    repeat_weight_dict: Dict[int, int],
    knowledge_corpus: str = "",
    tool_documents: Optional[List[Dict[str, Any]]] = None,
    tool_document_file: str = "",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts for environment augmentation tool name
    """
    prompts = []
    
    if tool_document_file:
        tool_documents = []
        with open(tool_document_file, "r", encoding="utf-8") as f:
            for line in tqdm(f):
                line = line.strip()
                if line:
                    tool_documents.append(json.loads(line))
    
    if not tool_documents:
        return prompts
    
    for tool_doc_item in tqdm(tool_documents):
        doc_domain = tool_doc_item.get("domain", domain)
        tool_docs = tool_doc_item.get("tool_documents", [])
        tool_docs_len = tool_doc_item.get("tool_documents_len", len(tool_docs))
        
        dynamic_repeats = repeat_weight_dict.get(tool_docs_len, num_repeats)
        
        for lang in ["zh", "en"]:
            for i in range(dynamic_repeats):
                params = {
                    "prompt_type": prompt_type,
                    "domain": doc_domain,
                    "knowledge_corpus": knowledge_corpus,
                    "num_hops": num_hops,
                    "lang": lang,
                    "tool_document": tool_docs,
                }
                prompt = build_prompt_for_env_aug(params)
                prompts.append({
                    "prompt": prompt,
                    "params": params,
                    "index": i + 1,
                })
    return prompts


def prepare_prompts_with_taxonomy(
    prompt_type: str,
    domain: str,
    knowledge_corpus: str = "",
    num_hops: int = 2,
    num_repeats: int = 1,
    lang: str = "zh",
    question: str = "",
    taxonomy_path: Optional[str] = None,
    mask_example: bool = False,
) -> List[Dict[str, Any]]:
    """
    Prepare prompts (using taxonomy)
    """
    # Load taxonomy
    taxonomy_leaves = load_taxonomy_leaves(taxonomy_path) if taxonomy_path and not knowledge_corpus else []
    
    if taxonomy_leaves:
        print(f"[INFO] Loaded taxonomy leaf nodes: {len(taxonomy_leaves)}")
    
    print(f"[INFO] Repeat generation {num_repeats} times")
    
    prompts = []
    
    for i in range(num_repeats):
        # Determine domain and corpus
        if taxonomy_leaves:
            for leaf in taxonomy_leaves:
                final_domain, final_corpus = _format_leaf_info(domain, leaf, mask_example)
                params = {
                    "prompt_type": prompt_type,
                    "domain": final_domain,
                    "knowledge_corpus": final_corpus,
                    "num_hops": num_hops,
                    "lang": lang,
                }
                
                if prompt_type == "by_question":
                    params["question"] = question
                
                # Build prompt
                prompt = build_prompt(params)
                
                prompts.append({
                    "prompt": prompt,
                    "params": params,
                    "index": i + 1,
                })
        else:
            final_domain = domain
            final_corpus = knowledge_corpus
            
            # Build parameters
            params = {
                "prompt_type": prompt_type,
                "domain": final_domain,
                "knowledge_corpus": final_corpus,
                "num_hops": num_hops,
                "lang": lang,
            }

            # Build prompt
            prompt = build_prompt(params)
            
            prompts.append({
                "prompt": prompt,
                "params": params,
                "index": i + 1,
            })
    
    return prompts


def prepare_prompts_base(
    prompt_type: str,
    domain: str,
    knowledge_corpus: str = "",
    num_hops: int = 2,
    num_repeats: int = 1,
    knowledge_corpus_file: str = "",
    lang: str = "zh",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts (no taxonomy version)
    """
    print(f"[INFO] Not using taxonomy, using domain directly: {domain}")
    print(f"[INFO] Repeat generation {num_repeats} times")
    print(f"[INFO] Number of hops: {num_hops}")
    
    prompts = []
    if not knowledge_corpus_file:
        for i in range(num_repeats):
            # Build parameters
            params = {
                "prompt_type": prompt_type,
                "domain": domain,
                "knowledge_corpus": knowledge_corpus,
                "num_hops": num_hops,
                "lang": lang,
            }
            
            # Build prompt
            prompt = build_prompt(params)
            
            prompts.append({
                "prompt": prompt,
                "params": params,
                "index": i + 1,
            })
    else:
        with open(knowledge_corpus_file, "r", encoding="utf-8") as f:
            knowledge_corpus_list = [json.loads(x) for x in f.readlines()]
        for knowledge_corpus_data in knowledge_corpus_list:
            knowledge_corpus = knowledge_corpus_data["knowledge_corpus"]
            domain = knowledge_corpus_data["domain"]
            for i in range(num_repeats):
                params = {
                    "prompt_type": prompt_type,
                    "domain": domain,
                    "knowledge_corpus": knowledge_corpus,
                    "num_hops": num_hops,
                    "lang": lang,
                }
                
                # Build prompt
                prompt = build_prompt(params)
                
                prompts.append({
                    "prompt": prompt,
                    "params": params,
                    "index": i + 1,
                })
    
    return prompts


def prepare_prompts_with_question(
    domain: str,
    knowledge_corpus: str = "",
    num_repeats: int = 1,
    lang: str = "zh",
    question: str = "",
    question_file: str = "",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts based on specific questions (by_question mode)
    """
    if not question and not question_file:
        return []
    
    print(f"[INFO] Using by_question mode, question: {question[:50]}...")
    print(f"[INFO] Repeat generation {num_repeats} times")
    
    prompts = []
    question_list = []
    if not question_file:
        question_list = [question]
    else:
        with open(question_file, "r", encoding="utf-8") as f:
            question_list = [json.loads(x) for x in f.readlines()]
    for question_data in question_list:
        if isinstance(question_data, dict):
            question = question_data["question"]
            domain = question_data["domain"]
        else:
            question = question_data
        for i in range(num_repeats):
            # Build parameters (by_question mode does not use num_hops, determined by model)
            params = {
                "prompt_type": "by_question",  # Force use by_question mode
                "domain": domain,
                "knowledge_corpus": knowledge_corpus,
                "num_hops": -1,  # Mark as not used
                "lang": lang,
                "question": question,
            }
            
            # Build prompt
            prompt = build_prompt(params)
            
            prompts.append({
                "prompt": prompt,
                "params": params,
                "index": i + 1,
            })
    
    return prompts


def prepare_prompts_with_hop_range(
    min_num_hops: int = 3,
    max_num_hops: int = 8,
    knowledge_corpus_file: str = "",
    num_repeats: int = 1,
    lang: str = "zh",
) -> List[Dict[str, Any]]:
    """
    Prepare prompts based on hop_range mode
    """
    if not knowledge_corpus_file:
        print("[WARNING] hop_range mode requires knowledge_corpus_file")
        return []
    
    print(f"[INFO] Using hop_range mode, hop range: {min_num_hops}-{max_num_hops}")
    print(f"[INFO] Repeat generation {num_repeats} times")
    
    prompts = []
    with open(knowledge_corpus_file, "r", encoding="utf-8") as f:
        knowledge_corpus_list = [json.loads(x) for x in f.readlines()]
    
    for knowledge_corpus_data in knowledge_corpus_list:
        knowledge_corpus = knowledge_corpus_data.get("knowledge_corpus", "")
        domain = knowledge_corpus_data.get("domain", "")
        
        for i in range(num_repeats):
            params = {
                "prompt_type": "hop_range",
                "domain": domain,
                "knowledge_corpus": knowledge_corpus,
                "min_num_hops": min_num_hops,
                "max_num_hops": max_num_hops,
                "lang": lang,
            }
            
            prompt = build_prompt(params)
            
            prompts.append({
                "prompt": prompt,
                "params": params,
                "index": i + 1,
            })
    
    return prompts


def process_single_hop(num_hop: int, prompt_type: str, domain: str, 
                       knowledge_corpus: str, num_repeats: int, 
                       tool_document_file: str) -> List[str]:
    """
    Process prompt generation task for single num_hop
    Used for multi-process parallel processing
    """
    print(f"  [Worker] Processing num_hop={num_hop}")
    weight_dict = load_repeat_weight_dict()
    
    result = []
    if prompt_type == "aug_env_base":
        result = prepare_prompts_for_env_aug_base(
            prompt_type=prompt_type,
            domain=domain,
            knowledge_corpus=knowledge_corpus,
            num_hops=num_hop,
            num_repeats=num_repeats,
            repeat_weight_dict=weight_dict,
            tool_document_file=tool_document_file,
        )
    elif prompt_type == "aug_env_call_state":
        result = prepare_prompts_for_env_aug_call_state(
            prompt_type=prompt_type,
            domain=domain,
            knowledge_corpus=knowledge_corpus,
            num_hops=num_hop,
            num_repeats=num_repeats,
            repeat_weight_dict=weight_dict,
            tool_document_file=tool_document_file,
        )
    elif prompt_type == "aug_env_tool_name":
        result = prepare_prompts_for_env_aug_tool_name(
            prompt_type=prompt_type,
            domain=domain,
            knowledge_corpus=knowledge_corpus,
            num_hops=num_hop,
            num_repeats=num_repeats,
            repeat_weight_dict=weight_dict,
            tool_document_file=tool_document_file,
        )
    
    print(f"  [Worker] num_hop={num_hop} completed, generated {len(result)} prompts")
    return result


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Prompt Preparation System")
    parser.add_argument("--prompt_type", type=str, default="base", choices=["base", "by_question","hop_range","aug_env_base","aug_env_call_state","aug_env_tool_name","taxonomy"])
    parser.add_argument("--domain", type=str, default="finance")
    parser.add_argument("--knowledge_corpus", type=str, default="")
    parser.add_argument("--num_hops", type=int, default=2)
    parser.add_argument("--num_repeats", type=int, default=1, help="Number of times to repeat generation for each configuration")
    parser.add_argument("--lang", type=str, default="zh")
    parser.add_argument("--question", type=str, default="")
    parser.add_argument("--question_file", type=str, default="")
    parser.add_argument("--knowledge_file", type=str, default="")
    parser.add_argument("--tool_document_file", type=str, default="")
    parser.add_argument("--mask_example", action="store_true", default=False)
    parser.add_argument("--min_num_hops", type=int, default=3, help="Minimum number of hops")
    parser.add_argument("--max_num_hops", type=int, default=10, help="Maximum number of hops")
    parser.add_argument("--output", type=str, default="", help="Output file path (optional)")
    parser.add_argument("--num_workers", type=int, default=32, help="Number of multi-process workers, -1 means auto use cpu_count(), 0 means no multi-process")
    
    args = parser.parse_args()
    num_hops_range = range(args.min_num_hops, args.max_num_hops + 1)
    
    taxonomy_path=get_domain_config(args.domain)
    prompts = []

    if args.prompt_type == "hop_range":
        prompts += prepare_prompts_with_hop_range(
            min_num_hops=args.min_num_hops,
            max_num_hops=args.max_num_hops,
            knowledge_corpus_file=args.knowledge_file,
            num_repeats=args.num_repeats,
            lang=args.lang
        )
    elif args.prompt_type == "taxonomy":
        prompts += prepare_prompts_with_taxonomy(
            prompt_type=args.prompt_type,
            domain=args.domain,
            knowledge_corpus=args.knowledge_corpus,
            num_hops=args.num_hops,
            num_repeats=args.num_repeats,
            lang=args.lang,
            taxonomy_path=taxonomy_path,
            mask_example=args.mask_example
        )
    if not args.question and not args.question_file and args.prompt_type != "hop_range" and args.prompt_type != "taxonomy":       # No question, free generation branch
        for hop in num_hops_range:
            print("base branch")
            prompts += prepare_prompts_base(
                prompt_type=args.prompt_type,
                domain=args.domain,
                knowledge_corpus=args.knowledge_corpus,
                knowledge_corpus_file=args.knowledge_file,
                num_hops=hop,
                num_repeats=args.num_repeats,
                lang=args.lang,
            )
    if args.question or args.question_file:   # Has question, decomposition branch
        prompts += prepare_prompts_with_question(
            domain=args.domain,
            knowledge_corpus=args.knowledge_corpus,
            num_repeats=args.num_repeats,
            lang=args.lang,
            question=args.question,
            question_file = args.question_file
        )

    
    print(f"\n[INFO] Successfully prepared {len(prompts)} prompts")
    
    if prompts:
        print("\n[Example] First prompt:")
        print("=" * 80)
        print(prompts[0]["prompt"][:50000])
        print("..." if len(prompts[0]["prompt"]) > 50000 else "")
        print("=" * 80)
    
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for prompt in prompts:
                f.write(json.dumps(prompt, ensure_ascii=False) + "\n")
        print(f"\n[INFO] Prompts saved to: {output_path}")


if __name__ == "__main__":
    main()
