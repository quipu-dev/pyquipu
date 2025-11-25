import subprocess
import logging
import os
from typing import List
from quipu.core.types import ActContext, Executor
from quipu.core.exceptions import ExecutionError

logger = logging.getLogger(__name__)

def register(executor: Executor):
    """注册 Git 相关操作"""
    executor.register("git_init", _git_init, arg_mode="exclusive")
    executor.register("git_add", _git_add, arg_mode="exclusive")
    executor.register("git_commit", _git_commit, arg_mode="block_only", summarizer=_summarize_commit)
    executor.register("git_status", _git_status, arg_mode="exclusive")

def _summarize_commit(args: List[str], contexts: List[str]) -> str:
    msg = contexts[0] if contexts else "No message"
    # Keep it short
    summary = (msg[:50] + '...') if len(msg) > 50 else msg
    return f"Git Commit: {summary}"

def _run_git_cmd(ctx: ActContext, cmd_args: List[str]) -> str:
    """在工作区根目录执行 git 命令的辅助函数。"""
    env = os.environ.copy()
    env['LC_ALL'] = 'C'
    
    try:
        result = subprocess.run(
            ["git"] + cmd_args,
            cwd=ctx.root_dir,
            capture_output=True,
            text=True,
            check=True,
            env=env
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        # 使用 ctx.fail 来抛出标准化的异常
        ctx.fail(f"Git 命令执行失败: git {' '.join(cmd_args)}\n错误信息: {error_msg}")
    except FileNotFoundError:
        ctx.fail("未找到 git 命令，请确保系统已安装 Git。")
    # 确保函数总有返回值，即使 ctx.fail 会抛异常
    return ""

def _git_init(ctx: ActContext, args: List[str]):
    """
    Act: git_init
    Args: []
    """
    if (ctx.root_dir / ".git").exists():
        logger.info("⚠️  Git 仓库已存在，跳过初始化。")
        return
    _run_git_cmd(ctx, ["init"])
    logger.info(f"✅ [Git] 已初始化仓库: {ctx.root_dir}")

def _git_add(ctx: ActContext, args: List[str]):
    """
    Act: git_add
    Args: [files]
    """
    targets = []
    if not args:
        targets = ["."]
    else:
        for arg in args:
            targets.extend(arg.split())
    if not targets:
        targets = ["."]
    _run_git_cmd(ctx, ["add"] + targets)
    logger.info(f"✅ [Git] 已添加文件: {targets}")

def _git_commit(ctx: ActContext, args: List[str]):
    """
    Act: git_commit
    Args: [message]
    """
    if len(args) < 1:
        ctx.fail("git_commit 需要至少一个参数: [message]")
    
    message = args[0]
    
    status = _run_git_cmd(ctx, ["status", "--porcelain"])
    if not status:
        logger.warning("⚠️  [Git] 没有检测到暂存的更改，跳过提交。")
        return

    if not ctx.request_confirmation(ctx.root_dir / ".git", "Staged Changes", f"Commit Message: {message}"):
        logger.warning("❌ [Skip] 用户取消提交")
        return

    _run_git_cmd(ctx, ["commit", "-m", message])
    logger.info(f"✅ [Git] 提交成功: {message}")

def _git_status(ctx: ActContext, args: List[str]):
    """
    Act: git_status
    Args: []
    """
    status = _run_git_cmd(ctx, ["status"])
    print(status)