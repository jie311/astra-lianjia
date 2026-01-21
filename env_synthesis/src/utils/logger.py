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

import logging
import os
from logging.handlers import RotatingFileHandler


_LOGGER_INITIALIZED = False
_LAST_LOG_FILE_NAME = None


def _init_root_logger() -> logging.Logger:
    """
    Initialize the root logger used by this package.
    All logs will be written to a single rotating log file and stdout.
    Log file name can be specified via LOG_FILE_NAME environment variable.
    """
    global _LOGGER_INITIALIZED, _LAST_LOG_FILE_NAME

    log_file_name = os.environ.get("LOG_FILE_NAME", "rl_verify.log")
    
    logger_name = log_file_name.replace(".log", "") if log_file_name.endswith(".log") else log_file_name
    
    root_logger = logging.getLogger(logger_name)
    
    if _LOGGER_INITIALIZED and root_logger.handlers and _LAST_LOG_FILE_NAME == log_file_name:
        return root_logger
    
    if root_logger.handlers:
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()

    root_logger.setLevel(logging.INFO)

    src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_root = os.path.dirname(src_dir)
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    
    log_file = os.path.join(log_dir, log_file_name)

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Add handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    _LOGGER_INITIALIZED = True
    _LAST_LOG_FILE_NAME = log_file_name
    return root_logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger that is wired to the central RL verify logging setup.
    """
    root_logger = _init_root_logger()
    if not name:
        return root_logger
    return root_logger.getChild(name)
