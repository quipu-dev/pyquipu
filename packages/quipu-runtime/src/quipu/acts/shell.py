import subprocess
import logging
from typing import List
from quipu.core.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册 Shell 相关操作"""
    executor.register("run_command", _run_command, arg_mode="exclusive")


def _run_command(ctx: ActContext, args: List[str]):
    """
    Act: run_command
    Args: [command_string]
    """
    if len(args) < 1:
        ctx.fail("run_command 需要至少一个参数: [command_string]")

    command = " ".join(args)

    warning_msg = f"⚠️  即将执行系统命令:\n  $ {command}\n  (CWD: {ctx.root_dir})"
    if not ctx.request_confirmation(ctx.root_dir, "System State", warning_msg):
        logger.warning(f"❌ [Skip] 用户取消执行命令: {command}")
        return

    logger.info(f"🚀 [Shell] Executing: {command}")

    try:
        result = subprocess.run(command, cwd=ctx.root_dir, shell=True, capture_output=True, text=True)

        if result.stdout:
            # 结果数据打印到 stdout
            print(result.stdout.strip())
        if result.stderr:
            # 错误/状态信息打印到 stderr
            logger.warning(f"⚠️  [Stderr]:\n{result.stderr.strip()}")

        if result.returncode != 0:
            ctx.fail(f"命令执行失败 (Code {result.returncode})")

    except Exception as e:
        ctx.fail(f"Shell 执行异常: {e}")
