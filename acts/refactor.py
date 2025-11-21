import shutil
import os
from pathlib import Path
from typing import List
import logging
from core.executor import Executor, ExecutionError

logger = logging.getLogger(__name__)

def register_refactor_acts(executor: Executor):
    """注册重构类操作"""
    executor.register("move_file", _move_file, arg_mode="hybrid")
    executor.register("delete_file", _delete_file, arg_mode="exclusive")

def _move_file(executor: Executor, args: List[str]):
    """
    Act: move_file
    Args: [src_path, dest_path]
    说明: 移动或重命名文件/目录。
    """
    if len(args) < 2:
        raise ExecutionError("move_file 需要两个参数: [src, dest]")
    
    src_raw, dest_raw = args[0], args[1]
    src_path = executor.resolve_path(src_raw)
    dest_path = executor.resolve_path(dest_raw)
    
    if not src_path.exists():
        raise ExecutionError(f"源文件不存在: {src_raw}")
    
    # 确认
    msg = f"Move: {src_raw} -> {dest_raw}"
    if not executor.request_confirmation(src_path, f"Source Exists", msg):
        logger.warning("❌ [Skip] 用户取消移动")
        return

    # 确保目标父目录存在
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    
    shutil.move(str(src_path), str(dest_path))
    logger.info(f"✅ [Move] 已移动/重命名: {src_raw} -> {dest_raw}")

def _delete_file(executor: Executor, args: List[str]):
    """
    Act: delete_file
    Args: [path]
    说明: 删除文件或目录（递归）。
    """
    if len(args) < 1:
        raise ExecutionError("delete_file 需要一个参数: [path]")
    
    raw_path = args[0]
    target_path = executor.resolve_path(raw_path)
    
    if not target_path.exists():
        logger.warning(f"⚠️  文件不存在，跳过删除: {raw_path}")
        return

    # 高危操作，确认信息加重
    file_type = "目录 (递归删除!)" if target_path.is_dir() else "文件"
    warning = f"🚨 正在删除{file_type}: {target_path}"
    
    if not executor.request_confirmation(target_path, "EXISTING CONTENT", warning):
        logger.warning("❌ [Skip] 用户取消删除")
        return

    if target_path.is_dir():
        shutil.rmtree(target_path)
    else:
        target_path.unlink()
        
    logger.info(f"🗑️  [Delete] 已删除: {raw_path}")