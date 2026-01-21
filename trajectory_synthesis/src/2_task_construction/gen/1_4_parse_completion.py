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

import argparse
import json
import re
from tqdm import tqdm


def extract_xml_content(text, tag):
    """
    Extract XML tag content, supports CDATA and plain format
    """
    # CDATA format
    pattern = f'<{tag}>\\s*<!\\[CDATA\\[(.*?)\\]\\]>\\s*</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    # Plain format
    pattern = f'<{tag}>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    
    return ""


def parse_target_tools(tools_str):
    """
    Parse tool string into list
    """
    if not tools_str:
        return []
    
    # Clean string
    tools_str = tools_str.strip()
    
    # Remove possible XML tags
    tools_str = re.sub(r'<[^>]*>', '', tools_str)
    
    # Split by comma or newline
    if ',' in tools_str:
        tools = [t.strip() for t in tools_str.split(',') if t.strip()]
    else:
        tools = [t.strip() for t in re.split(r'[\n\r]+', tools_str) if t.strip()]
    
    # If only one element after split and no space, likely a single tool
    if len(tools) == 1 and ' ' not in tools[0]:
        return tools
    
    # Filter empty values
    return [t for t in tools if t]


def parse_xml_response(response_content):
    """
    Parse XML format response content
    """
    try:
        # Find response tag
        response_match = re.search(r'<response>(.*?)</response>', response_content, re.DOTALL)
        response_xml = response_match.group(1) if response_match else response_content
        
        # Extract each component
        server_analysis = extract_xml_content(response_xml, 'server_analysis')
        target_tools_str = extract_xml_content(response_xml, 'target_tools')
        if not target_tools_str:
            target_tools_str = extract_xml_content(response_xml, 'target_tool')
        question = extract_xml_content(response_xml, 'question')
        
        # Validate required fields
        if not all([server_analysis, target_tools_str, question]):
            return None
        
        # Parse tool list
        target_tools = parse_target_tools(target_tools_str)
        
        if not target_tools:
            return None
            
        return {
            "server_analysis": server_analysis.strip(),
            "target_tools": target_tools,
            "question": question.strip()
        }
        
    except Exception as e:
        print(f"Parse error: {e}")
        return None


def process_file(input_file, output_file):
    """
    Process JSONL file, extract and parse all responses, and format to standard structure
    """
    total = 0
    success = 0
    
    with open(input_file, 'r', encoding='utf-8') as f_in, \
         open(output_file, 'w', encoding='utf-8') as f_out:
        
        for line in tqdm(f_in, desc="Parsing"):
            try:
                data = json.loads(line)
                response_content = data.get("response", "")
                metadata = data.get("metadata", {})
                
                total += 1
                
                # Parse response
                parsed = parse_xml_response(response_content)
                
                if not parsed:
                    continue
                
                success += 1
                
                # Build standard format: messages + metadata.query_info
                result = {
                    "messages": [
                        {"role": "user", "content": parsed["question"]}
                    ],
                    "metadata": {
                        **metadata,
                        "query_info": {
                            "server_analysis": parsed["server_analysis"],
                            "target_tools": parsed["target_tools"],
                            "question": parsed["question"]
                        }
                    }
                }
                
                f_out.write(json.dumps(result, ensure_ascii=False) + '\n')
                
            except Exception as e:
                print(f"Processing error: {e}")
                continue
    
    print(f"\nTotal: {total}, Success: {success}, Failed: {total - success}")


def main():
    parser = argparse.ArgumentParser(description='Parse completion')
    parser.add_argument('--input_file', required=True, help='Input file path')
    parser.add_argument('--output_file', required=True, help='Output file path')
    args = parser.parse_args()

    process_file(args.input_file, args.output_file)
    print(f"Output file: {args.output_file}")


if __name__ == "__main__":
    main()
