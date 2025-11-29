import os
from pathlib import Path
from typing import List
import logging
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册基础文件系统操作"""
    executor.register("write_file", _write_file, arg_mode="hybrid", summarizer=_summarize_write)
    executor.register("patch_file", _patch_file, arg_mode="hybrid", summarizer=_summarize_patch_file)
    executor.register("append_file", _append_file, arg_mode="hybrid", summarizer=_summarize_append)
    executor.register("end", _end, arg_mode="hybrid")
    executor.register("echo", _echo, arg_mode="hybrid")


def _summarize_write(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"Write: {path}"


def _summarize_patch_file(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"patch_file in: {path}"


def _summarize_append(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"Append to: {path}"


def _end(ctx: ActContext, args: List[str]):
    """
    Act: end
    Args: [ignored_contexts...]
    说明: 这是一个空操作。
    它的作用是显式结束上一个指令的参数收集。
    解析器会将后续的 block 视为 end 的参数，而 end 函数会忽略它们。
    """
    pass


def _echo(ctx: ActContext, args: List[str]):
    """
    Act: echo
    Args: [content]
    """
    if len(args) < 1:
        ctx.fail("echo 需要至少一个参数: [content]")

    bus.data(args[0])


def _write_file(ctx: ActContext, args: List[str]):
    """
    Act: write_file
    Args: [path, content]
    """
    if len(args) < 2:
        ctx.fail("write_file 需要至少两个参数: [path, content]")

    raw_path = args[0]
    content = args[1]

    target_path = ctx.resolve_path(raw_path)

    old_content = ""
    if target_path.exists():
        try:
            old_content = target_path.read_text(encoding="utf-8")
        except Exception:
            old_content = "[Binary or Unreadable]"

    ctx.request_confirmation(target_path, old_content, content)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
    except PermissionError:
        ctx.fail(f"写入文件失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"写入文件时发生未知错误: {e}")

    bus.success("acts.basic.success.fileWritten", path=target_path.relative_to(ctx.root_dir))


def _patch_file(ctx: ActContext, args: List[str]):
    """
    Act: patch_file
    Args: [path, old_string, new_string]
    """
    if len(args) < 3:
        ctx.fail("patch_file 需要至少三个参数: [path, old_string, new_string]")

    raw_path, old_str, new_str = args[0], args[1], args[2]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        ctx.fail(f"文件未找到: {raw_path}")

    try:
        content = target_path.read_text(encoding="utf-8")
    except Exception as e:
        ctx.fail(f"读取文件 {raw_path} 失败: {e}")

    if old_str not in content:
        ctx.fail(f"在文件 {raw_path} 中未找到指定的旧文本。\n请确保 Markdown 块中的空格和换行完全匹配。")

    new_content = content.replace(old_str, new_str, 1)

    ctx.request_confirmation(target_path, content, new_content)

    try:
        target_path.write_text(new_content, encoding="utf-8")
    except PermissionError:
        ctx.fail(f"替换文件内容失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"更新文件时发生未知错误: {e}")

    bus.success("acts.basic.success.filePatched", path=target_path.relative_to(ctx.root_dir))


def _append_file(ctx: ActContext, args: List[str]):
    """
    Act: append_file
    Args: [path, content]
    """
    if len(args) < 2:
        ctx.fail("append_file 需要至少两个参数: [path, content]")

    raw_path, content_to_append = args[0], args[1]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        ctx.fail(f"文件不存在，无法追加: {raw_path}")

    old_content = ""
    try:
        old_content = target_path.read_text(encoding="utf-8")
    except Exception:
        old_content = "[Binary or Unreadable]"

    new_content = old_content + content_to_append

    ctx.request_confirmation(target_path, old_content, new_content)

    try:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(content_to_append)
    except PermissionError:
        ctx.fail(f"追加文件内容失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"追加文件时发生未知错误: {e}")

    bus.success("acts.basic.success.fileAppended", path=target_path.relative_to(ctx.root_dir))