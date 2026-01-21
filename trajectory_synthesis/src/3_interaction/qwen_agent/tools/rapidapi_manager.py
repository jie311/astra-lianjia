# Copyright 2023 The Qwen team, Alibaba Group. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
RapidAPI Manager - Manager for RapidAPI tools
Designed following MCPManager pattern, specifically for loading and managing RapidAPI tools
"""

import json
import os
import re
import time
from typing import Dict, List, Optional, Union

import requests

from qwen_agent.log import logger
from qwen_agent.tools.base import BaseTool


class RapidAPIManager:
    """Manager class for RapidAPI tools
    
    Usage:
        # 1. Initialize manager
        manager = RapidAPIManager(api_key="your-rapidapi-key")
        
        # 2. Load tools from JSON file
        tools = manager.load_tools_from_json("ex.json")
        
        # 3. Use these tools in Agent
        agent = Assistant(function_list=tools, llm=llm_cfg)
    """
    
    _instance = None  # Singleton pattern
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(RapidAPIManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, api_key: Optional[str] = None, timeout: int = 60, max_retries: int = 3):
        """Initialize RapidAPI Manager
        
        Args:
            api_key: RapidAPI API Key, reads from RAPIDAPI_KEY environment variable if not provided
            timeout: Request timeout (seconds), default 60 seconds
            max_retries: Maximum retry count, default 3 times
        """
        if not hasattr(self, 'initialized'):  # Ensure singleton is only initialized once
            self.api_key = api_key or os.environ.get('RAPIDAPI_KEY', '')
            if not self.api_key:
                logger.warning("RapidAPI key not provided. Please set RAPIDAPI_KEY environment variable or pass api_key parameter.")
            
            self.timeout = timeout
            self.max_retries = max_retries
            self.tools_registry = {}  # Store loaded tools
            self.initialized = True
            logger.info(f"RapidAPIManager initialized (timeout={timeout}s, max_retries={max_retries})")
    
    def load_tools_from_json(self, json_file_path: str) -> List[BaseTool]:
        """Load RapidAPI tools from JSON file
        
        Args:
            json_file_path: JSON configuration file path
            
        Returns:
            List of tools
        """
        logger.info(f"Loading RapidAPI tools from: {json_file_path}")
        
        with open(json_file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return self.load_tools_from_config(config)
    
    def load_tools_from_config(self, config: Dict) -> List[BaseTool]:
        """Load RapidAPI tools from configuration dictionary
        
        Args:
            config: Tool configuration dictionary, format see ex.json
            
        Returns:
            List of tools
        """
        tools = []
        
        # Get tool group info
        group_info = config.get('group_info', {})
        group_name = group_info.get('tool_name', 'Unknown')
        group_description = group_info.get('tool_description', '')
        
        logger.info(f"Loading tool group: {group_name}")
        logger.info(f"Description: {group_description}")
        
        # Load each tool
        tool_list = config.get('tool_list', [])
        for tool_config in tool_list:
            try:
                tool = self._create_tool_from_config(tool_config, group_name)
                tools.append(tool)
                self.tools_registry[tool.name] = tool
                logger.info(f"  ✓ Loaded tool: {tool.name}")
            except Exception as e:
                logger.error(f"  ✗ Failed to load tool {tool_config.get('name')}: {e}")
        
        logger.info(f"Successfully loaded {len(tools)} tools from {group_name}")
        return tools
    
    def _create_tool_from_config(self, tool_config: Dict, group_name: str) -> BaseTool:
        """Create tool instance from configuration
        
        Args:
            tool_config: Tool configuration
            group_name: Tool group name
            
        Returns:
            Tool instance
        """
        tool_name = tool_config['name']
        tool_description = tool_config['description']
        tool_parameters = tool_config.get('parameters', {})
        api_url = tool_config['api']
        
        # Convert parameter format: ensure compliance with OpenAI function calling standard
        if 'required' not in tool_parameters:
            tool_parameters['required'] = []
        
        # Clean parameters, keep only necessary fields
        cleaned_parameters = {
            'type': tool_parameters.get('type', 'object'),
            'properties': tool_parameters.get('properties', {}),
            'required': tool_parameters.get('required', [])
        }
        
        # Dynamically create tool class
        tool_class = self._create_tool_class(
            tool_name=tool_name,
            tool_description=tool_description,
            tool_parameters=cleaned_parameters,
            api_url=api_url,
            group_name=group_name
        )
        
        return tool_class
    
    def _create_tool_class(
        self,
        tool_name: str,
        tool_description: str,
        tool_parameters: Dict,
        api_url: str,
        group_name: str
    ) -> BaseTool:
        """Dynamically create tool class
        
        Args:
            tool_name: Tool name
            tool_description: Tool description
            tool_parameters: Tool parameters
            api_url: API URL
            group_name: Tool group name
            
        Returns:
            Tool instance
        """
        manager = self  # Capture manager reference
        
        class RapidAPITool(BaseTool):
            name = f"{group_name}_{tool_name}"
            description = tool_description
            parameters = tool_parameters
            
            def __init__(self):
                super().__init__()
                self.api_url = api_url
                self.tool_name = tool_name
                self.group_name = group_name
                self.manager = manager
            
            def call(self, params: Union[str, dict], **kwargs) -> str:
                """Call RapidAPI tool
                
                Args:
                    params: Parameters (JSON string or dictionary)
                    
                Returns:
                    API response result (including code and data)
                """
                # Parse parameters
                if isinstance(params, str):
                    try:
                        params_dict = json.loads(params)
                    except json.JSONDecodeError:
                        return json.dumps({
                            "code": 400,
                            "error": "Invalid JSON parameters",
                            "data": None
                        }, ensure_ascii=False)
                else:
                    params_dict = params
                
                # Build request URL (replace path parameters)
                url = self._build_url(self.api_url, params_dict)
                
                # Prepare request headers
                headers = self._build_headers()
                
                # Prepare query parameters
                query_params = self._build_query_params(params_dict)
                
                # Retry mechanism
                last_error = None
                for attempt in range(self.manager.max_retries):
                    try:
                        # Send GET request (most RapidAPI use GET)
                        if attempt > 0:
                            logger.info(f"Retry attempt {attempt + 1}/{self.manager.max_retries}")
                        
                        logger.info(f"Calling RapidAPI: {url}")
                        logger.info(f"Query params: {query_params}")
                        
                        response = requests.get(
                            url,
                            headers=headers,
                            params=query_params,
                            timeout=self.manager.timeout
                        )
                        
                        # If successful, break out of retry loop
                        break
                        
                    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                        last_error = e
                        if attempt < self.manager.max_retries - 1:
                            wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s...
                            logger.warning(f"Request failed (attempt {attempt + 1}), retrying in {wait_time}s...")
                            time.sleep(wait_time)
                            continue
                        else:
                            # Last retry failed, raise exception
                            raise
                
                try:
                    
                    # Get status code
                    status_code = response.status_code
                    
                    # Check if successful
                    if response.ok:  # 2xx status code
                        try:
                            result_data = response.json()
                            return json.dumps({
                                "code": status_code,
                                "data": result_data,
                                "message": "Success"
                            }, ensure_ascii=False, indent=2)
                        except json.JSONDecodeError:
                            # If response is not JSON, return text
                            return json.dumps({
                                "code": status_code,
                                "data": response.text,
                                "message": "Success (non-JSON response)"
                            }, ensure_ascii=False, indent=2)
                    else:
                        # Non-2xx status code
                        error_detail = response.text[:500] if response.text else "No error details"
                        return json.dumps({
                            "code": status_code,
                            "error": f"HTTP {status_code} error",
                            "detail": error_detail,
                            "data": None
                        }, ensure_ascii=False, indent=2)
                    
                except requests.exceptions.Timeout:
                    error_msg = f"Request timeout after {self.manager.timeout} seconds"
                    logger.error(error_msg)
                    return json.dumps({
                        "code": 408,
                        "error": "Request Timeout",
                        "message": error_msg,
                        "data": None
                    }, ensure_ascii=False, indent=2)
                    
                except requests.exceptions.ConnectionError as e:
                    error_msg = f"Connection error: {str(e)}"
                    logger.error(error_msg)
                    return json.dumps({
                        "code": 503,
                        "error": "Connection Error",
                        "message": error_msg,
                        "data": None
                    }, ensure_ascii=False, indent=2)
                    
                except requests.exceptions.RequestException as e:
                    error_msg = f"Request failed: {str(e)}"
                    logger.error(error_msg)
                    status_code = e.response.status_code if hasattr(e, 'response') and e.response is not None else 500
                    return json.dumps({
                        "code": status_code,
                        "error": "Request Exception",
                        "message": error_msg,
                        "data": None
                    }, ensure_ascii=False, indent=2)
                    
                except Exception as e:
                    error_msg = f"Unexpected error: {str(e)}"
                    logger.error(error_msg)
                    return json.dumps({
                        "code": 500,
                        "error": "Internal Error",
                        "message": error_msg,
                        "data": None
                    }, ensure_ascii=False, indent=2)
            
            def _build_url(self, url_template: str, params: Dict) -> str:
                """Build URL, replace path parameters
                
                Args:
                    url_template: URL template, e.g. "https://api.com/game/{gameid}"
                    params: Parameter dictionary
                    
                Returns:
                    Complete URL
                """
                url = url_template
                
                # Find all path parameters ({param})
                path_params = re.findall(r'\{(\w+)\}', url)
                
                for param_name in path_params:
                    # Find matching value in parameters (case-insensitive)
                    param_value = None
                    for key, value in params.items():
                        if key.lower() == param_name.lower():
                            param_value = value
                            break
                    
                    if param_value is not None:
                        url = url.replace(f'{{{param_name}}}', str(param_value))
                        url = url.replace(f'{{{param_name.lower()}}}', str(param_value))
                        url = url.replace(f'{{{param_name.upper()}}}', str(param_value))
                
                return url
            
            def _build_headers(self) -> Dict:
                """Build request headers
                
                Returns:
                    Request headers dictionary
                """
                # Extract host from URL
                host = self.api_url.split('/')[2]
                
                headers = {
                    'X-RapidAPI-Key': self.manager.api_key,
                    'X-RapidAPI-Host': host
                }
                
                return headers
            
            def _build_query_params(self, params: Dict) -> Dict:
                """Build query parameters (excluding path parameters)
                
                Args:
                    params: All parameters
                    
                Returns:
                    Query parameters dictionary
                """
                # Find path parameters
                path_params = re.findall(r'\{(\w+)\}', self.api_url)
                path_params_lower = [p.lower() for p in path_params]
                
                # Filter out path parameters, keep only query parameters
                query_params = {}
                for key, value in params.items():
                    if key.lower() not in path_params_lower:
                        query_params[key] = value
                
                return query_params
        
        # Set class name
        RapidAPITool.__name__ = f'{group_name}_{tool_name}_Tool'
        
        return RapidAPITool()
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get loaded tool
        
        Args:
            tool_name: Tool name
            
        Returns:
            Tool instance, or None if not found
        """
        return self.tools_registry.get(tool_name)
    
    def list_tools(self) -> List[str]:
        """List all loaded tool names
        
        Returns:
            List of tool names
        """
        return list(self.tools_registry.keys())


