import logging
import subprocess
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.types import ActContext, Executor

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
        ctx.fail(bus.get("acts.error.missingArgs", act_name="run_command", count=1, signature="[command_string]"))

    command = "\n".join(args)

    warning_msg = f"⚠️  即将执行系统命令:\n  $ {command}\n  (CWD: {ctx.root_dir})"
    ctx.request_confirmation(ctx.root_dir, "System State", warning_msg)

    bus.info("acts.shell.info.executing", command=command)

    try:
        result = subprocess.run(command, cwd=ctx.root_dir, shell=True, capture_output=True, text=True)
    except Exception as e:
        ctx.fail(bus.get("acts.shell.error.exception", error=e))
        return

    if result.stdout:
        bus.data(result.stdout.strip())
    if result.stderr:
        bus.warning("acts.shell.warning.stderrOutput", output=result.stderr.strip())

    if result.returncode != 0:
        ctx.fail(bus.get("acts.shell.error.failed", code=result.returncode))
