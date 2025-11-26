from __future__ import annotations
from typing import TypedDict, List, Callable, Optional, Union
from pathlib import Path
from .exceptions import ExecutionError


# --- Forward declaration to avoid circular imports ---
class Executor: ...


class ActContext:
    """
    提供给插件函数的上下文 API。
    这是插件与执行器核心之间的稳定接口。
    """

    def __init__(self, executor: Executor):
        self._executor = executor

    @property
    def root_dir(self) -> Path:
        """获取当前工作区的根目录"""
        return self._executor.root_dir

    def resolve_path(self, rel_path: str) -> Path:
        """将相对路径安全地解析为工作区内的绝对路径"""
        return self._executor.resolve_path(rel_path)

    def request_confirmation(self, file_path: Path, old_content: str, new_content: str) -> bool:
        """生成 diff 并请求用户确认"""
        return self._executor.request_confirmation(file_path, old_content, new_content)

    def fail(self, message: str):
        """
        向执行器报告一个可恢复的错误并终止当前 act。
        这会抛出一个 ExecutionError。
        """
        raise ExecutionError(message)


# --- Type definitions for core components ---

# Act 函数签名定义: (context, args) -> None
ActFunction = Callable[[ActContext, List[str]], None]

# Summarizer 函数签名定义: (args, context_blocks) -> str
# 用于根据指令参数生成单行摘要
Summarizer = Callable[[List[str], List[str]], str]


class Statement(TypedDict):
    """表示解析后的单个操作语句"""

    act: str
    contexts: List[str]
