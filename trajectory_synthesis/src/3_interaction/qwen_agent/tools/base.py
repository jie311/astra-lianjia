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

import json
import os
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union

from qwen_agent.llm.schema import ContentItem
from qwen_agent.settings import DEFAULT_WORKSPACE
from qwen_agent.utils.utils import has_chinese_chars, json_loads, logger, print_traceback, save_url_to_local_work_dir

TOOL_REGISTRY = {}


class ToolServiceError(Exception):

    def __init__(self,
                 exception: Optional[Exception] = None,
                 code: Optional[str] = None,
                 message: Optional[str] = None,
                 extra: Optional[dict] = None):
        if exception is not None:
            super().__init__(exception)
        else:
            super().__init__(f'\nError code: {code}. Error message: {message}')
        self.exception = exception
        self.code = code
        self.message = message
        self.extra = extra


def register_tool(name, allow_overwrite=False):

    def decorator(cls):
        if name in TOOL_REGISTRY:
            if allow_overwrite:
                logger.warning(f'Tool `{name}` already exists! Overwriting with class {cls}.')
            else:
                raise ValueError(f'Tool `{name}` already exists! Please ensure that the tool name is unique.')
        if cls.name and (cls.name != name):
            raise ValueError(f'{cls.__name__}.name="{cls.name}" conflicts with @register_tool(name="{name}").')
        cls.name = name
        TOOL_REGISTRY[name] = cls

        return cls

    return decorator


def is_tool_schema(obj: dict) -> bool:
    """
    Check if obj is a valid JSON schema describing a tool compatible with OpenAI's tool calling.
    Example valid schema:
    {
      "name": "get_current_weather",
      "description": "Get the current weather in a given location",
      "parameters": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "The city and state, e.g. San Francisco, CA"
          },
          "unit": {
            "type": "string",
            "enum": ["celsius", "fahrenheit"]
          }
        },
        "required": ["location"]
      }
    }
    """
    import jsonschema
    try:
        assert set(obj.keys()) == {'name', 'description', 'parameters'}, f"obj keys must be exactly {{'name', 'description', 'parameters'}}, got {set(obj.keys())}"
        assert isinstance(obj['name'], str), f"obj['name'] must be str, got {type(obj['name'])}"
        assert obj['name'].strip(), f"obj['name'] cannot be empty or whitespace"
        assert isinstance(obj['description'], str), f"obj['description'] must be str, got {type(obj['description'])}"
        assert isinstance(obj['parameters'], dict), f"obj['parameters'] must be dict, got {type(obj['parameters'])}"

        assert set(obj['parameters'].keys()) == {'type', 'properties', 'required'}, f"obj['parameters'] keys must be exactly {{'type', 'properties', 'required'}}, got {set(obj['parameters'].keys())}"
        assert obj['parameters']['type'] == 'object', f"obj['parameters']['type'] must be 'object', got {obj['parameters']['type']}"
        assert isinstance(obj['parameters']['properties'], dict), f"obj['parameters']['properties'] must be dict, got {type(obj['parameters']['properties'])}"
        assert isinstance(obj['parameters']['required'], list), f"obj['parameters']['required'] must be list, got {type(obj['parameters']['required'])}"
        assert set(obj['parameters']['required']).issubset(set(obj['parameters']['properties'].keys())), f"obj['parameters']['required'] must be subset of properties keys, got required={obj['parameters']['required']}, properties={list(obj['parameters']['properties'].keys())}"
    except AssertionError as e:
        print(f"AssertionError: {e}")
        return False
    # try:
    #     jsonschema.validate(instance={}, schema=obj['parameters'])
    # except jsonschema.exceptions.SchemaError as e:
    #     print(f"jsonschema.exceptions.SchemaError: {e}")
    #     return False
    except jsonschema.exceptions.ValidationError:
        pass
    return True


class MockToolWrapper:
    """A wrapper class for mock tool dictionaries to provide a unified interface with BaseTool."""
    
    def __init__(self, tool_dict: dict, server_description: str):
        """Initialize with a tool dictionary containing name, description, parameters."""
        self._tool_dict = tool_dict
        self.name = tool_dict.get('name', '')
        self.description = tool_dict.get('description', '')
        self.parameters = tool_dict.get('parameters', [])
        self.server_description = server_description
        self.cfg = {}
    
    @property
    def function(self) -> dict:
        """Return tool function info in the same format as BaseTool."""
        return {
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
        }
    
    @property
    def file_access(self) -> bool:
        return self._tool_dict.get('file_access', False)
    
    def call(self, params: Union[str, dict], **kwargs) -> Union[str, list, dict]:
        """Mock tools don't actually execute, return a placeholder response."""
        return f"[Mock tool '{self.name}' called with params: {params}]"


class BaseTool(ABC):
    name: str = ''
    description: str = ''
    parameters: Union[List[dict], dict] = []

    def __init__(self, cfg: Optional[dict] = None):
        self.cfg = cfg or {}
        if not self.name:
            raise ValueError(
                f'You must set {self.__class__.__name__}.name, either by @register_tool(name=...) or explicitly setting {self.__class__.__name__}.name'
            )
        if isinstance(self.parameters, dict):
            if not is_tool_schema({'name': self.name, 'description': self.description, 'parameters': self.parameters}):
                raise ValueError(
                    'The parameters, when provided as a dict, must confirm to a valid openai-compatible JSON schema.')

    @abstractmethod
    def call(self, params: Union[str, dict], **kwargs) -> Union[str, list, dict, List[ContentItem]]:
        """The interface for calling tools.

        Each tool needs to implement this function, which is the workflow of the tool.

        Args:
            params: The parameters of func_call.
            kwargs: Additional parameters for calling tools.

        Returns:
            The result returned by the tool, implemented in the subclass.
        """
        raise NotImplementedError

    def _verify_json_format_args(self, params: Union[str, dict], strict_json: bool = False) -> dict:
        """Verify the parameters of the function call"""
        if isinstance(params, str):
            try:
                if strict_json:
                    params_json: dict = json.loads(params)
                else:
                    params_json: dict = json_loads(params)
            except json.decoder.JSONDecodeError:
                raise ValueError('Parameters must be formatted as a valid JSON!')
        else:
            params_json: dict = params
        if isinstance(self.parameters, list):
            for param in self.parameters:
                if 'required' in param and param['required']:
                    if param['name'] not in params_json:
                        raise ValueError('Parameters %s is required!' % param['name'])
        elif isinstance(self.parameters, dict):
            import jsonschema
            jsonschema.validate(instance=params_json, schema=self.parameters)
        else:
            raise ValueError
        return params_json

    @property
    def function(self) -> dict:  # Bad naming. It should be `function_info`.
        return {
            # 'name_for_human': self.name_for_human,
            'name': self.name,
            'description': self.description,
            'parameters': self.parameters,
            # 'args_format': self.args_format
        }

    @property
    def name_for_human(self) -> str:
        return self.cfg.get('name_for_human', self.name)

    @property
    def args_format(self) -> str:
        fmt = self.cfg.get('args_format')
        if fmt is None:
            if has_chinese_chars([self.name_for_human, self.name, self.description, self.parameters]):
                fmt = '此工具的输入应为JSON对象。'
            else:
                fmt = 'Format the arguments as a JSON object.'
        return fmt

    @property
    def file_access(self) -> bool:
        return False


class BaseToolWithFileAccess(BaseTool, ABC):

    def __init__(self, cfg: Optional[Dict] = None):
        super().__init__(cfg)
        assert self.name
        default_work_dir = os.path.join(DEFAULT_WORKSPACE, 'tools', self.name)
        self.work_dir: str = self.cfg.get('work_dir', default_work_dir)

    @property
    def file_access(self) -> bool:
        return True

    def call(self, params: Union[str, dict], files: List[str] = None, **kwargs) -> str:
        # Copy remote files to the working directory:
        if files:
            os.makedirs(self.work_dir, exist_ok=True)
            for file in files:
                try:
                    save_url_to_local_work_dir(file, self.work_dir)
                except Exception:
                    print_traceback()

        # Then do something with the files:
        # ...
