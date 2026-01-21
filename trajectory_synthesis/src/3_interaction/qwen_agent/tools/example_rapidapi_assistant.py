#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Example: Create an intelligent assistant integrated with RapidAPI tools using RapidAPIManager

This example demonstrates how to:
1. Load RapidAPI tools from JSON file
2. Integrate these tools into Qwen-Agent's Assistant
3. Let LLM automatically call these tools to answer user questions
"""

import os
import sys
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qwen_agent.agents import Assistant
from rapidapi_manager import RapidAPIManager


def main():
    """Main function"""
    
    print("=" * 80)
    print("RapidAPI + Qwen-Agent Integration Example")
    print("=" * 80)
    
    # ========== 1. Configure LLM ==========
    llm_cfg = {
        # Use model service provided by DashScope
        # 'model': 'qwen-max',
        # 'model_type': 'qwen_dashscope',
        # If DASHSCOPE_API_KEY is not set in environment variables, set it here
        # 'api_key': 'YOUR_DASHSCOPE_API_KEY',
        
        # Or use locally deployed model (via vLLM or Ollama)
        'model': 'your_model',
        'model_server': 'your_model_server',
        'api_key': 'your_api_key',
        
        'generate_cfg': {
            'top_p': 0.8,
            'temperature': 0.7,
        }
    }
    
    # ========== 2. Initialize RapidAPI Manager ==========
    print("\n[1] Initializing RapidAPI Manager...")
    
    # Read API Key from environment variable, or pass directly
    rapidapi_key = os.environ.get('RAPIDAPI_KEY', '')
    if not rapidapi_key:
        print("⚠️  Warning: RAPIDAPI_KEY environment variable not found")
        print("   Please set environment variable: export RAPIDAPI_KEY='your-key'")
        print("   Or modify code to pass API Key directly")
        # rapidapi_key = 'your-rapidapi-key-here'
    
    manager = RapidAPIManager(api_key=rapidapi_key)
    
    # ========== 3. Load RapidAPI Tools ==========
    print("\n[2] Loading RapidAPI tools from JSON file...")
    
    json_path = "../data/ex.json"
    tools = manager.load_tools_from_json(json_path)
    
    print(f"\n✓ Successfully loaded {len(tools)} tools:")
    for i, tool in enumerate(tools, 1):
        print(f"  {i}. {tool.name}")
    
    # ========== 4. Create Assistant ==========
    print("\n[3] Creating Assistant integrated with RapidAPI tools...")
    
    system_instruction = """You are a professional League of Legends esports assistant.

You can use the following tools to query League of Legends esports information:
- Query league information
- Query tournament information
- Query match replays (VODs)
- Query match details
- Query team and player information
- Query standings

When users ask for related information, you should:
1. Understand user's needs
2. Select appropriate tools
3. Call tools in correct order (e.g., first query league, then query tournaments for that league)
4. Format results in a user-friendly way

Please respond in the same language as the user."""
    
    bot = Assistant(
        llm=llm_cfg,
        system_message=system_instruction,
        function_list=tools,  # Use RapidAPI tools
        name="LOL_Esports_Assistant",
        description="League of Legends esports data query assistant"
    )
    
    print("✓ Assistant created successfully!")
    
    # ========== 5. Run Conversation ==========
    print("\n[4] Starting conversation...")
    print("=" * 80)
    print("Tip: Enter 'quit' or 'exit' to exit the program")
    print("=" * 80)
    
    # Example questions
    example_questions = [
        "Help me query all League of Legends league information",
        "What tournaments does LPL have?",
        "Query recent match replays",
        "Tell me about LNG Esports team and players"
    ]
    
    print("\n💡 Example questions:")
    for i, q in enumerate(example_questions, 1):
        print(f"  {i}. {q}")
    print()
    
    messages = []  # Conversation history
    
    while True:
        try:
            # Get user input
            user_input = input("\nUser: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("Goodbye!")
                break
            
            # Add user message to history
            messages.append({'role': 'user', 'content': user_input})
            
            # Call Agent
            print("\nAssistant: ", end='', flush=True)
            response_text = ''
            processed_msg_count = 0  # Track already processed message count
            
            for response in bot.run(messages=messages):
                # Streaming output
                if response:
                    # Only process new messages (starting from processed_msg_count)
                    new_messages = response[processed_msg_count:]
                    
                    for msg in new_messages:
                        if isinstance(msg, dict):
                            # Display tool call status code
                            if msg.get('role') == 'function':
                                tool_name = msg.get('name', 'Unknown Tool')
                                content = msg.get('content', '')
                                try:
                                    # Parse JSON result returned by tool
                                    result = json.loads(content) if isinstance(content, str) else content
                                    status_code = result.get('code', 'N/A')
                                    print(f"\n[Tool call: {tool_name} | Status code: {status_code}]", flush=True)
                                except:
                                    print(f"\n[Tool call: {tool_name}]", flush=True)
                    
                    # Update processed message count
                    processed_msg_count = len(response)
                    
                    # Process assistant's streaming output (need to iterate all messages to get complete content)
                    for msg in response:
                        if isinstance(msg, dict) and msg.get('role') == 'assistant':
                            content = msg.get('content', '')
                            if isinstance(content, str) and content:
                                # Only print new content
                                new_content = content[len(response_text):]
                                print(new_content, end='', flush=True)
                                response_text = content
            
            print()  # Newline
            
            # Add assistant response to history
            messages.extend(response)
            
        except KeyboardInterrupt:
            print("\n\nProgram interrupted, goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error occurred: {e}")
            import traceback
            traceback.print_exc()


def test_single_tool():
    """Test single tool call"""
    print("\n" + "=" * 80)
    print("Test single tool call")
    print("=" * 80)
    
    # Initialize manager
    rapidapi_key = os.environ.get('RAPIDAPI_KEY', 'your-key-here')
    manager = RapidAPIManager(api_key=rapidapi_key)
    
    # Load tools
    json_path = "../data/ex.json"
    tools = manager.load_tools_from_json(json_path)
    
    # Test Get_Leagues tool
    print("\nTesting tool: Get_Leagues")
    get_leagues_tool = None
    for tool in tools:
        if 'Get_Leagues' in tool.name:
            get_leagues_tool = tool
            break
    
    if get_leagues_tool:
        print(f"Tool name: {get_leagues_tool.name}")
        print(f"Tool description: {get_leagues_tool.description}")
        print("\nCalling tool...")
        
        # Call tool (Get_Leagues doesn't need parameters)
        result = get_leagues_tool.call({})
        print("\nResult:")
        print(result)
    else:
        print("Get_Leagues tool not found")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="RapidAPI + Qwen-Agent Example")
    parser.add_argument(
        '--test-tool',
        action='store_true',
        help='Only test single tool call, do not start conversation'
    )
    
    args = parser.parse_args()
    
    if args.test_tool:
        test_single_tool()
    else:
        main()
