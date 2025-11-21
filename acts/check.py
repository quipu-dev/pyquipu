import os
from pathlib import Path
from typing import List
import logging
from core.executor import Executor, ExecutionError

logger = logging.getLogger(__name__)

def register_check_acts(executor: Executor):
    """注册检查类操作"""
    # Exclusive 模式：要么在行内写文件名(不推荐)，要么在块里写列表(推荐)
    executor.register("check_files_exist", _check_files_exist, arg_mode="exclusive")
    executor.register("check_cwd_match", _check_cwd_match, arg_mode="exclusive")

def _check_files_exist(executor: Executor, args: List[str]):
    """
    Act: check_files_exist
    Args: [file_list_string]
    说明: 检查当前工作区内是否存在指定的文件。文件名通过换行符分隔。
    注意：本指令禁用混合模式。若在 act 行内提供了参数，后续的代码块将被忽略。
    """
    if len(args) < 1:
        raise ExecutionError("check_files_exist 需要至少一个参数: [file_list_string]")
    
    # 支持一次传入多个文件，按行分割
    raw_files = args[0].strip().split('\n')
    missing_files = []

    for raw_path in raw_files:
        clean_path = raw_path.strip()
        if not clean_path:
            continue
            
        target_path = executor.resolve_path(clean_path)
        if not target_path.exists():
            missing_files.append(clean_path)

    if missing_files:
        msg = f"❌ [Check] 以下文件在工作区中未找到:\n" + "\n".join(f"  - {f}" for f in missing_files)
        raise ExecutionError(msg)
    
    logger.info(f"✅ [Check] 所有 {len(raw_files)} 个文件均存在。")

def _check_cwd_match(executor: Executor, args: List[str]):
    """
    Act: check_cwd_match
    Args: [expected_absolute_path]
    说明: 检查当前运行的工作区根目录 (executor.root_dir) 是否与预期的绝对路径匹配。
    这通常用于防止 AI 在错误的机器或错误的文件夹下执行操作。
    """
    if len(args) < 1:
        raise ExecutionError("check_cwd_match 需要至少一个参数: [expected_absolute_path]")

    expected_path_str = args[0].strip()
    
    # 获取当前 executor 的根目录绝对路径
    current_root = executor.root_dir.resolve()
    
    # 解析传入的预期路径 (如果是 ~ 开头，展开它)
    expected_path = Path(os.path.expanduser(expected_path_str)).resolve()

    if current_root != expected_path:
        raise ExecutionError(
            f"❌ [Check] 工作区目录不匹配!\n"
            f"  预期: {expected_path}\n"
            f"  实际: {current_root}"
        )
        
    logger.info(f"✅ [Check] 工作区目录匹配: {current_root}")
