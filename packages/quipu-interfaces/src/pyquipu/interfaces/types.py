from __future__ import annotations

from pathlib import Path
from typing import Callable, List, TypedDict

from .exceptions import ExecutionError


# --- Forward declaration to avoid circular imports ---
class Executor: ...


class ActContext:
    def __init__(self, executor: Executor):
        self._executor = executor

    @property
    def root_dir(self) -> Path:
        return self._executor.root_dir

    def resolve_path(self, rel_path: str) -> Path:
        return self._executor.resolve_path(rel_path)

    def request_confirmation(self, file_path: Path, old_content: str, new_content: str) -> bool:
        return self._executor.request_confirmation(file_path, old_content, new_content)

    def fail(self, message: str):
        raise ExecutionError(message)


# --- Type definitions for core components ---

# Act 函数签名定义: (context, args) -> None
ActFunction = Callable[[ActContext, List[str]], None]

# Summarizer 函数签名定义: (args, context_blocks) -> str
# 用于根据指令参数生成单行摘要
Summarizer = Callable[[List[str], List[str]], str]


class Statement(TypedDict):
    act: str
    contexts: List[str]
