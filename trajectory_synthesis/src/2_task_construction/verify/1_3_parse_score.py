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
import re
import argparse
from tqdm import tqdm


def extract_xml_content(text, tag):
    """
    Extract XML tag content
    """
    # Try CDATA
    pattern = f'<{tag}>\\s*<!\\[CDATA\\[(.*?)\\]\\]>\\s*</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    # Try plain tag
    pattern = f'<{tag}>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    # Try format with comments
    pattern = f'<{tag}>\\s*<!--.*?-->\\s*(.*?)\\s*</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    return ""


def convert_rating_to_score(rating_text, dimension_name):
    """
    Convert text rating to numeric score (1-5)
    """
    if not rating_text:
        return None
    
    rating = rating_text.strip().lower()
    
    rating_mappings = {
        'tool_selection_difficulty': {
            'very easy': 1, 'easy': 2, 'medium': 3, 'hard': 4, 'very hard': 5
        },
        'tool_selection_uniqueness': {
            'not unique': 1, 'somewhat unique': 2, 'moderately unique': 3, 
            'quite unique': 4, 'highly unique': 5
        },
        'question_quality': {
            'very poor': 1, 'poor': 2, 'average': 3, 'good': 4, 'excellent': 5
        },
        'scenario_realism': {
            'unrealistic': 1, 'somewhat unrealistic': 2, 'moderately realistic': 3, 
            'realistic': 4, 'highly realistic': 5
        }
    }
    
    if dimension_name not in rating_mappings:
        return None
    
    mapping = rating_mappings[dimension_name]
    
    # Exact match
    if rating in mapping:
        return mapping[rating]
    
    # Partial match
    for key, value in mapping.items():
        if key in rating or rating in key:
            return value
    
    return None


def extract_quality_dimension(text, dimension_name):
    """
    Extract reasoning and rating for a single quality dimension
    """
    dimension_pattern = f'<{dimension_name}>(.*?)</{dimension_name}>'
    dimension_match = re.search(dimension_pattern, text, re.DOTALL)
    
    # If normal match fails, use tolerant match: match up to next dimension tag
    if not dimension_match:
        # Define dimension order to determine next dimension
        next_dimension_map = {
            'tool_selection_difficulty': 'tool_selection_uniqueness',
            'tool_selection_uniqueness': 'question_quality',
            'question_quality': 'scenario_realism',
            'scenario_realism': None  # Last dimension
        }
        
        next_dim = next_dimension_map.get(dimension_name)
        if next_dim:
            # Match up to next dimension tag
            dimension_pattern = f'<{dimension_name}>(.*?)(?=<{next_dim}>)'
        else:
            # Last dimension, match up to </response>
            dimension_pattern = f'<{dimension_name}>(.*?)(?=</response>)'
        
        dimension_match = re.search(dimension_pattern, text, re.DOTALL)
    
    if not dimension_match:
        return None
    
    dimension_content = dimension_match.group(1)
    reasoning = extract_xml_content(dimension_content, 'reasoning')
    rating_text = extract_xml_content(dimension_content, 'rating').lower()
    score = convert_rating_to_score(rating_text, dimension_name)
    
    if not reasoning or score is None:
        return None
    
    return {
        "reasoning": reasoning.strip(),
        "rating_text": rating_text.strip(),
        "score": score
    }


def parse_quality_response(response_content):
    """
    Parse quality assessment response
    """
    try:
        response_content = response_content.strip()
        
        # Extract <response> block
        response_match = re.search(r'<response>(.*?)</response>', response_content, re.DOTALL)
        response_xml = response_match.group(1) if response_match else response_content
        
        # Extract 4 dimensions
        dimensions = [
            'tool_selection_difficulty',
            'tool_selection_uniqueness',
            'question_quality',
            'scenario_realism'
        ]
        
        result = {}
        for dim in dimensions:
            dim_data = extract_quality_dimension(response_xml, dim)
            if not dim_data:
                print(f"Failed to extract {dim} dimension data")
                print(response_content)
                return None
            result[dim] = dim_data
        
        return result
        
    except Exception as e:
        print(f"Error parsing score result: {e}")
        return None


def parse(inp_file, out_file_parsed):
    """
    Parse quality assessment response
    """
    total = 0
    success = 0
    
    with open(inp_file, 'r') as f_in, open(out_file_parsed, 'w') as f_out:
        for line in tqdm(f_in, desc="Parsing score results"):
            try:
                data = json.loads(line)
            except:
                continue
            
            total += 1
            response_content = data.get("response", "")
            
            # Keep all original fields
            query_info = data.get("query_info", {})
            mcp_info = data.get("mcp_info", {})
            graph = data.get("graph", {})
            chain_info = data.get("chain_info", {})
            
            parsed = parse_quality_response(response_content)
            
            if parsed:
                success += 1
                # Calculate total score
                total_score = sum([parsed[dim]["score"] for dim in parsed])
                avg_score = total_score / 4.0
                
                # Add score info to query_info
                query_info_with_score = query_info.copy()
                query_info_with_score["query_score_info"] = {
                    "quality_scores": {
                        "tool_selection_difficulty": parsed["tool_selection_difficulty"]["score"],
                        "tool_selection_uniqueness": parsed["tool_selection_uniqueness"]["score"],
                        "question_quality": parsed["question_quality"]["score"],
                        "scenario_realism": parsed["scenario_realism"]["score"],
                        "total_score": total_score,
                        "average_score": avg_score
                    },
                    "quality_reasoning": {
                        dim: parsed[dim]["reasoning"] for dim in parsed
                    }
                }
                
                # Keep all original fields
                result = {
                    "query_info": query_info_with_score,
                    "mcp_info": mcp_info
                }
                
                # Only add if exists in original data
                if graph:
                    result["graph"] = graph
                if chain_info:
                    result["chain_info"] = chain_info
                
                f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
    
    print(f"Parse complete - Total: {total}, Success: {success}, Failed: {total - success}")


def main():
    parser = argparse.ArgumentParser(description='Parse query quality scores')
    parser.add_argument('--inp_file', required=True, help='Input file path (*_raw.jsonl)')
    parser.add_argument('--out_file', required=True, help='Output file path (.jsonl)')
    
    args = parser.parse_args()
    
    parse(args.inp_file, args.out_file)


if __name__ == '__main__':
    main()