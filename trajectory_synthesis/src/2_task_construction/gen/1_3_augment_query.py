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
import argparse
import re
import os
import random
import sys
from tqdm import tqdm
from datasets import load_dataset

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, '../..'))
sys.path.insert(0, SRC_ROOT)
from utils.utils import multi_call


def load_personas(persona_dataset_path):
    """
    Load Arrow format persona dataset
    """
    try:
        dataset = load_dataset('arrow', data_files=persona_dataset_path)
        return dataset['train']
    except Exception as e:
        print(f"Failed to load persona dataset: {e}")
        return None


def extract_persona_fields(persona):
    """
    Extract common fields, excluding ethnicity, region and other non-applicable fields
    """
    
    skills_list = eval(persona['skills_and_expertise_list']) if isinstance(persona['skills_and_expertise_list'], str) else persona['skills_and_expertise_list']
    hobbies_list = eval(persona['hobbies_and_interests_list']) if isinstance(persona['hobbies_and_interests_list'], str) else persona['hobbies_and_interests_list']
    
    return {
        'age': persona['age'],
        'occupation': persona['occupation'].replace('_', ' ').title(),
        'education': persona['education_level'].replace('_', ' ').title(),
        'professional': persona['professional_persona'][:200] + '...',  
        'skills': ', '.join(skills_list[:5]) if skills_list else 'General skills',  
        'hobbies': ', '.join(hobbies_list[:5]) if hobbies_list else 'Various interests', 
    }


def clean_html_comments(text):
    """
    Remove HTML comment markers (compatible with unpaired occurrences)
    """
    if not text:
        return text
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    text = re.sub(r'<!--', '', text)
    text = re.sub(r'-->', '', text)
    return text.strip()


def extract_xml_content(text, tag):
    """
    Extract XML tag content, supports CDATA/case-insensitive/optional attributes
    """
    pattern_cdata = rf'<{tag}\b[^>]*>\s*<!\[CDATA\[(.*?)\]\]>\s*</{tag}>'
    match = re.search(pattern_cdata, text, re.DOTALL | re.IGNORECASE)
    if match:
        return clean_html_comments(match.group(1))
    pattern_plain = rf'<{tag}\b[^>]*>(.*?)</{tag}>'
    match = re.search(pattern_plain, text, re.DOTALL | re.IGNORECASE)
    if match:
        return clean_html_comments(match.group(1))
    return ""


def parse_all_variations(response_xml, mode):
    """
    Parse all <variation_X> from <variations>, return list[{index, question, context, constraints}]
    """
    variations_xml = extract_xml_content(response_xml, 'variations')
    if not variations_xml:
        variations_xml = response_xml

    pattern = r'<variation_\d+\b[^>]*>(.*?)</variation_\d+>'
    blocks = re.findall(pattern, variations_xml, re.DOTALL | re.IGNORECASE)

    parsed = []
    for idx, block in enumerate(blocks, start=1):
        question = extract_xml_content(block, 'question').strip()
        context = extract_xml_content(block, 'context').strip()
        constraints = extract_xml_content(block, 'constraints').strip()
        if question:
            parsed.append({
                "index": idx,
                "question": question,
                "context": context,
                "constraints": constraints,
                "mode": mode
            })
    if not parsed:
        qs = re.findall(r'<question\b[^>]*>(.*?)</question>', variations_xml, re.DOTALL | re.IGNORECASE)
        for idx, q in enumerate(qs, start=1):
            q_text = (q or '').strip()
            if q_text:
                parsed.append({
                    "index": idx,
                    "question": q_text,
                    "context": "",
                    "constraints": "",
                    "mode": mode
                })
    return parsed


def parse_augmentation_response(response_content, mode):
    """
    Parse augmentation task XML: tolerant handling of code blocks/case/missing <response> wrapper
    """
    try:
        if not response_content or not isinstance(response_content, str):
            return None
        text = response_content.strip()
        if text.startswith('```'):
            text = re.sub(r'^```[a-zA-Z]*\n', '', text)
            text = re.sub(r'\n```\s*$', '', text)
        first_lt = text.find('<')
        if first_lt > 0:
            text = text[first_lt:]

        response_match = re.search(r'<response\b[^>]*>([\s\S]*?)</response>', text, re.IGNORECASE)
        response_xml = response_match.group(1) if response_match else text

        analysis = extract_xml_content(response_xml, 'analysis').strip()
        variations = parse_all_variations(response_xml, mode)

        if not variations:
            return None
        return {
            "analysis": analysis,
            "variations": variations
        }
    except Exception as e:
        print(e)
        return None


def build_tool_descriptions(mcp_info, target_tools):
    """
    Extract tool descriptions from mcp_info
    """
    tool_desc_map = {}
    tool_list = mcp_info.get('base_info', {}).get('tool_list', [])
    for tool in tool_list:
        name = tool.get('name')
        if name:
            tool_desc_map[name] = tool.get('description', '')

    lines = []
    for i, t in enumerate(target_tools, 1):
        desc = tool_desc_map.get(t, '(no description)')
        lines.append(f"{i}. {t}: {desc}")
    return "\n".join(lines)


def load_template_text(mode):
    """
    Load augmentation template text
    """
    if mode == 'diverse':
        filename = 'gen_augmented_questions_diverse.md'
    elif mode == 'complicate':
        filename = 'gen_augmented_questions_complicate.md'
    elif mode == 'add_ug':
        filename = 'gen_augmented_questions_by_ug.md'
    else:
        raise ValueError(f"Unsupported augmentation mode: {mode}")
    
    base_dir = os.path.dirname(os.path.dirname(__file__))
    path = os.path.join(base_dir, 'prompts', filename)
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def build_augmentation_prompt(original_question, target_tools, tool_descriptions, mode, variations_count, persona_fields=None):
    """
    Build augmentation prompt based on template
    """
    template = load_template_text(mode)

    target_tools_str = ", ".join(target_tools)
    prompt = template
    prompt = prompt.replace('{ORIGINAL_QUESTION}', original_question)
    prompt = prompt.replace('{TARGET_TOOLS}', target_tools_str)
    prompt = prompt.replace('{TOOL_DESCRIPTIONS}', tool_descriptions)
    prompt = prompt.replace('{VARIATIONS_COUNT}', str(variations_count))
    
    if mode == 'add_ug' and persona_fields:
        prompt = prompt.replace('{PERSONA_AGE}', str(persona_fields['age']))
        prompt = prompt.replace('{PERSONA_OCCUPATION}', persona_fields['occupation'])
        prompt = prompt.replace('{PERSONA_EDUCATION}', persona_fields['education'])
        prompt = prompt.replace('{PERSONA_PROFESSIONAL}', persona_fields['professional'])
        prompt = prompt.replace('{PERSONA_SKILLS}', persona_fields['skills'])
        prompt = prompt.replace('{PERSONA_HOBBIES}', persona_fields['hobbies'])
    elif mode == 'add_ug':
        raise ValueError("add_ug mode requires persona_fields parameter")
    
    return prompt


def derive_original_question_and_tools(data):
    """
    Extract original question and target tool list from new format data
    """
    query_info = data.get('query_info', {})
    
    original_question = query_info.get('generated_question', '').strip()
    
    target_tools = query_info.get('target_tools', [])
    
    return original_question, target_tools


def parse_augmentation_to_results(response):
    """
    Parse augmentation response and return result list
    """
    response_content = response.get("response", "")
    mode_for_resp = response.get("augmentation_mode", "")
    original_data = response.get("original_data", {})
    original_question = response.get("original_question", "")
    
    parsed = parse_augmentation_response(response_content, mode_for_resp)
    if not parsed:
        return None
    
    results = []
    
    # 1. First save original query (augmented_query_info as empty dict)
    original_result = {
        "query_info": {
            **original_data.get("query_info", {}),
            "augmented_query_info": {}
        },
        "mcp_info": original_data.get("mcp_info", {}),
        "graph": original_data.get("graph", {}),
        "chain_info": original_data.get("chain_info", {})
    }
    results.append(original_result)
    
    # 2. Save augmented queries (augmented_query_info placed in query_info)
    for var in parsed["variations"]:
        augmented_question = var.get("question", "")
        
        result = {
            "query_info": {
                **original_data.get("query_info", {}),
                "augmented_query_info": {
                    "mode": mode_for_resp,
                    "augmented_question": augmented_question
                }
            },
            "mcp_info": original_data.get("mcp_info", {}),
            "graph": original_data.get("graph", {}),
            "chain_info": original_data.get("chain_info", {})
        }
        results.append(result)
    
    return results


def gen(inp_file, out_file_raw, out_file_parsed, n_sample, pool_size, mode, variations_count, 
        model, persona_dataset_path=None, n_persona_per_query=1):
    """
    Generate augmentation queries
    """
    persona_dataset = None
    if mode in ['add_ug', 'all'] and persona_dataset_path:
        print(f"Loading Persona dataset: {persona_dataset_path}")
        persona_dataset = load_personas(persona_dataset_path)
        if persona_dataset:
            print(f"✅ Successfully loaded {len(persona_dataset)} personas")
        else:
            print("⚠️ Persona loading failed, add_ug mode will be unavailable")
            if mode == 'add_ug':
                raise ValueError("add_ug mode requires successful loading of persona dataset")
    elif mode == 'add_ug':
        raise ValueError("add_ug mode requires --persona_dataset_path parameter")
    
    inp_list = []
    with open(inp_file, 'r', encoding='utf-8') as f:
        for line in tqdm(f, desc='Loading input file'):
            data = json.loads(line)

            original_question, target_tools = derive_original_question_and_tools(data)
            if not original_question or not target_tools:
                continue

            tool_descriptions = build_tool_descriptions(data.get('mcp_info', {}), target_tools)

            # all mode optional: includes all 3 types or only diverse+complicate
            modes_to_build = ['diverse', 'complicate', 'add_ug'] if mode == 'all' else [mode]
            for run_mode in modes_to_build:
                persona_samples = n_persona_per_query if run_mode == 'add_ug' else 1
                
                for persona_idx in range(persona_samples):
                    persona_fields = None
                    if run_mode == 'add_ug' and persona_dataset:
                        random_idx = random.randint(0, len(persona_dataset) - 1)
                        persona = persona_dataset[random_idx]
                        persona_fields = extract_persona_fields(persona)
                    
                    prompt_text = build_augmentation_prompt(
                        original_question=original_question,
                        target_tools=target_tools,
                        tool_descriptions=tool_descriptions,
                        mode=run_mode,
                        variations_count=variations_count,
                        persona_fields=persona_fields
                    )

                    base_item = {
                        "messages": [{"role": "user", "content": prompt_text}],
                        "augmentation_mode": run_mode,
                        "original_data": data,
                        "original_question": original_question
                    }

                    for _ in range(max(1, n_sample)):
                        inp_list.append(base_item.copy())

    stats = multi_call(
        inp_list=inp_list,
        out_file_raw=out_file_raw,
        out_file_parsed=out_file_parsed,
        pool_size=pool_size,
        model=model,
        parse_func=parse_augmentation_to_results
    )
    print(f"Parse result - Responses: {stats['total']}, Total variations: {stats['success']}")


def parse_raw_file(raw_file, out_file_parsed):
    """
    Offline parse raw file
    """
    total = 0
    success = 0
    with open(raw_file, 'r', encoding='utf-8') as f_in, \
         open(out_file_parsed, 'w', encoding='utf-8') as f_out:
        for line in tqdm(f_in, desc='Parsing augmentation results'):
            try:
                data = json.loads(line)
            except Exception:
                continue
            total += 1
            
            response_content = data.get('response', '')
            mode_for_resp = data.get('augmentation_mode', '')
            original_data = data.get('original_data', {})

            parsed = parse_augmentation_response(response_content, mode_for_resp)
            if not parsed:
                continue

            # 1. First save original query
            original_result = {
                "query_info": {
                    **original_data.get("query_info", {}),
                    "augmented_query_info": {}
                },
                "mcp_info": original_data.get("mcp_info", {}),
                "graph": original_data.get("graph", {}),
                "chain_info": original_data.get("chain_info", {})
            }
            f_out.write(json.dumps(original_result, ensure_ascii=False) + '\n')
            success += 1

            # 2. Save augmented queries
            for var in parsed['variations']:
                augmented_question = var.get('question', '')
                result = {
                    "query_info": {
                        **original_data.get("query_info", {}),
                        "augmented_query_info": {
                            "mode": mode_for_resp,
                            "augmented_question": augmented_question
                        }
                    },
                    "mcp_info": original_data.get("mcp_info", {}),
                    "graph": original_data.get("graph", {}),
                    "chain_info": original_data.get("chain_info", {})
                }
                f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
                success += 1

    print(f"Parse complete: Read {total} responses, generated {success} entries")

def main():
    parser = argparse.ArgumentParser(description='Augment generated queries or parse existing raw output')
    parser.add_argument('--model', required=False, help='Model name (configured in api_config.py)')
    parser.add_argument('--inp_file', required=False, help='Input file path (generated queries, recommend using parsed.jsonl)')
    parser.add_argument('--out_file', required=False, help='Output file path (without extension)')
    parser.add_argument('--pool_size', type=int, default=128, help='Concurrency')
    parser.add_argument('--n_sample', type=int, default=1, help='Number of samples per augmentation prompt')
    parser.add_argument('--augmentation_mode', choices=['diverse', 'complicate', 'add_ug', 'all'], default='diverse', help='Augmentation mode: diverse/complicate/add_ug/all')
    parser.add_argument('--variations_count', type=int, default=1, help='Number of variations per augmentation')
    parser.add_argument('--persona_dataset_path', type=str, default=None, help='Persona dataset path (Arrow format), only needed in add_ug mode')
    parser.add_argument('--n_persona_per_query', type=int, default=1, help='Number of different personas to sample per query (only effective in add_ug mode)')
    parser.add_argument('--parse_only', action='store_true', help='Parse only: generate *_parsed.jsonl from *_raw.jsonl')
    parser.add_argument('--raw_file', required=False, help='Raw result file path (*_raw.jsonl)')

    args = parser.parse_args()

    if args.parse_only:
        raw_file = f"{args.out_file}_raw.jsonl"
        parsed_file = raw_file.replace("_raw.jsonl", "_parsed.jsonl")
        parse_raw_file(raw_file, parsed_file)
    else:
        required_fields = ['model', 'inp_file', 'out_file']
        for f_name in required_fields:
            if getattr(args, f_name, None) in (None, ''):
                raise ValueError(f"Missing required parameter: --{f_name}")

        out_file_raw = f"{args.out_file}_raw.jsonl"
        out_file_parsed = f"{args.out_file}_parsed.jsonl"

        gen(args.inp_file, out_file_raw, out_file_parsed, args.n_sample, args.pool_size, 
            args.augmentation_mode, args.variations_count, args.model,
            args.persona_dataset_path, args.n_persona_per_query)

if __name__ == '__main__':
    main()
