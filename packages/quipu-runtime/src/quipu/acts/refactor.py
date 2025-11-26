import shutil
from typing import List
import logging
from quipu.core.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册重构类操作"""
    executor.register("move_file", _move_file, arg_mode="hybrid")
    executor.register("delete_file", _delete_file, arg_mode="exclusive")


def _move_file(ctx: ActContext, args: List[str]):
    """
    Act: move_file
    Args: [src_path, dest_path]
    """
    if len(args) < 2:
        ctx.fail("move_file 需要两个参数: [src, dest]")

    src_raw, dest_raw = args[0], args[1]
    src_path = ctx.resolve_path(src_raw)
    dest_path = ctx.resolve_path(dest_raw)

    if not src_path.exists():
        ctx.fail(f"源文件不存在: {src_raw}")

    msg = f"Move: {src_raw} -> {dest_raw}"
    if not ctx.request_confirmation(src_path, f"Source Exists", msg):
        logger.warning("❌ [Skip] 用户取消移动")
        return

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dest_path))
    except PermissionError:
        ctx.fail(f"移动/重命名失败: 权限不足。源: '{src_raw}', 目标: '{dest_raw}'")
    except Exception as e:
        ctx.fail(f"移动/重命名时发生未知错误: {e}")
    logger.info(f"✅ [Move] 已移动/重命名: {src_raw} -> {dest_raw}")


def _delete_file(ctx: ActContext, args: List[str]):
    """
    Act: delete_file
    Args: [path]
    """
    if len(args) < 1:
        ctx.fail("delete_file 需要一个参数: [path]")

    raw_path = args[0]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        logger.warning(f"⚠️  文件不存在，跳过删除: {raw_path}")
        return

    file_type = "目录 (递归删除!)" if target_path.is_dir() else "文件"
    warning = f"🚨 正在删除{file_type}: {target_path}"

    if not ctx.request_confirmation(target_path, "EXISTING CONTENT", warning):
        logger.warning("❌ [Skip] 用户取消删除")
        return

    try:
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()
    except PermissionError:
        ctx.fail(f"删除失败: 对 '{raw_path}' 的访问权限不足。")
    except Exception as e:
        ctx.fail(f"删除时发生未知错误: {e}")

    logger.info(f"🗑️  [Delete] 已删除: {raw_path}")
