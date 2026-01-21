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


def _init_root_logger() -> logging.Logger:
    """
    Initialize the root logger used by this package.
    All logs will be written to a single rotating log file and stdout.
    """
    global _LOGGER_INITIALIZED

    root_logger = logging.getLogger("rl_verify")
    if _LOGGER_INITIALIZED and root_logger.handlers:
        return root_logger

    root_logger.setLevel(logging.INFO)

    # Log directory: <rl_root>/logs
    rl_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    log_dir = os.path.join(rl_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "rl_verify.log")

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    # Avoid adding duplicate handlers if called multiple times
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

    _LOGGER_INITIALIZED = True
    return root_logger


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger that is wired to the central RL verify logging setup.
    """
    root_logger = _init_root_logger()
    if not name:
        return root_logger
    return root_logger.getChild(name)

