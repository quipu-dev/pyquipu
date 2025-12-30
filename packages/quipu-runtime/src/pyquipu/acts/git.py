import logging
import os
import subprocess
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    executor.register("git_init", _git_init, arg_mode="exclusive")
    executor.register("git_add", _git_add, arg_mode="exclusive")
    executor.register("git_commit", _git_commit, arg_mode="block_only", summarizer=_summarize_commit)
    executor.register("git_status", _git_status, arg_mode="exclusive")


def _summarize_commit(args: List[str], contexts: List[str]) -> str:
    msg = contexts[0] if contexts else "No message"
    summary = (msg[:50] + "...") if len(msg) > 50 else msg
    return f"Git Commit: {summary}"


def _run_git_cmd(ctx: ActContext, cmd_args: List[str]) -> str:
    env = os.environ.copy()
    env["LC_ALL"] = "C"

    try:
        result = subprocess.run(
            ["git"] + cmd_args, cwd=ctx.root_dir, capture_output=True, text=True, check=True, env=env
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        ctx.fail(bus.get("acts.git.error.cmdFailed", args=" ".join(cmd_args), error=error_msg))
    except FileNotFoundError:
        ctx.fail(bus.get("acts.git.error.gitNotFound"))
    return ""


def _git_init(ctx: ActContext, args: List[str]):
    if (ctx.root_dir / ".git").exists():
        bus.warning("acts.git.warning.repoExists")
        return
    _run_git_cmd(ctx, ["init"])
    bus.success("acts.git.success.initialized", path=ctx.root_dir)


def _git_add(ctx: ActContext, args: List[str]):
    targets = []
    if not args:
        targets = ["."]
    else:
        for arg in args:
            targets.extend(arg.split())
    if not targets:
        targets = ["."]
    _run_git_cmd(ctx, ["add"] + targets)
    bus.success("acts.git.success.added", targets=targets)


def _git_commit(ctx: ActContext, args: List[str]):
    if len(args) < 1:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="git_commit", count=1, signature="[message]"))

    message = args[0]

    status = _run_git_cmd(ctx, ["status", "--porcelain"])
    if not status:
        bus.warning("acts.git.warning.commitSkipped")
        return

    ctx.request_confirmation(ctx.root_dir / ".git", "Staged Changes", f"Commit Message: {message}")

    _run_git_cmd(ctx, ["commit", "-m", message])
    bus.success("acts.git.success.committed", message=message)


def _git_status(ctx: ActContext, args: List[str]):
    status = _run_git_cmd(ctx, ["status"])
    bus.data(status)
