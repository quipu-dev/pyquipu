import subprocess
import logging
import shlex
from typing import List
from core.executor import Executor, ExecutionError

logger = logging.getLogger(__name__)

def register_shell_acts(executor: Executor):
    """注册 Shell 相关操作"""
    executor.register("run_command", _run_command, arg_mode="exclusive")

def _run_command(executor: Executor, args: List[str]):
    """
    Act: run_command
    Args: [command_string]
    说明: 在当前工作区根目录下执行 Shell 命令。
    """
    if len(args) < 1:
        raise ExecutionError("run_command 需要至少一个参数: [command_string]")

    # 如果参数被分散在多个 args 中（例如没有用引号包围），尝试合并它们
    # 但推荐用户使用引号包裹整个命令
    command = " ".join(args)
    
    # 安全确认
    warning_msg = f"⚠️  即将执行系统命令:\n  $ {command}\n  (CWD: {executor.root_dir})"
    if not executor.request_confirmation(executor.root_dir, "System State", warning_msg):
        logger.warning(f"❌ [Skip] 用户取消执行命令: {command}")
        return

    logger.info(f"🚀 [Shell] Executing: {command}")
    
    try:
        # 使用 shell=True 允许管道和重定向，但这有安全风险，依赖于 request_confirmation 拦截
        result = subprocess.run(
            command,
            cwd=executor.root_dir,
            shell=True,
            capture_output=True,
            text=True
        )
        
        # 打印输出
        if result.stdout:
            logger.info(f"📤 [Stdout]:\n{result.stdout.strip()}")
        if result.stderr:
            logger.warning(f"⚠️  [Stderr]:\n{result.stderr.strip()}")
            
        if result.returncode != 0:
            raise ExecutionError(f"命令执行失败 (Code {result.returncode})")
            
    except Exception as e:
        raise ExecutionError(f"Shell 执行异常: {e}")