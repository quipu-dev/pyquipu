import subprocess
import logging
import shlex
from typing import List
from core.executor import Executor, ExecutionError

logger = logging.getLogger(__name__)

def register_git_acts(executor: Executor):
    """注册 Git 相关操作"""
    executor.register("git_init", _git_init)
    executor.register("git_add", _git_add)
    executor.register("git_commit", _git_commit)
    executor.register("git_status", _git_status)

def _run_git_cmd(executor: Executor, cmd_args: List[str]) -> str:
    """
    在工作区根目录执行 git 命令的辅助函数。
    返回 stdout。
    """
    try:
        # 确保在工作区根目录下执行
        result = subprocess.run(
            ["git"] + cmd_args,
            cwd=executor.root_dir,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip()
        raise ExecutionError(f"Git 命令执行失败: git {' '.join(cmd_args)}\n错误信息: {error_msg}")
    except FileNotFoundError:
        raise ExecutionError("未找到 git 命令，请确保系统已安装 Git。")

def _git_init(executor: Executor, args: List[str]):
    """
    Act: git_init
    Args: [] (无参数)
    """
    git_dir = executor.root_dir / ".git"
    if git_dir.exists():
        logger.info("⚠️  Git 仓库已存在，跳过初始化。")
        return

    _run_git_cmd(executor, ["init"])
    logger.info(f"✅ [Git] 已初始化仓库: {executor.root_dir}")

def _git_add(executor: Executor, args: List[str]):
    """
    Act: git_add
    Args: [files] (空格分隔的文件列表，或者 "." )
    """
    if not args:
        target = "."
    else:
        target = args[0]
    
    # 将参数字符串拆分为列表，例如 "src/main.py tests/" -> ["src/main.py", "tests/"]
    # 简单的 split 即可，暂不支持带空格的文件名（需要引号处理）
    targets = target.split()
    
    _run_git_cmd(executor, ["add"] + targets)
    logger.info(f"✅ [Git] 已添加文件: {target}")

def _git_commit(executor: Executor, args: List[str]):
    """
    Act: git_commit
    Args: [message]
    """
    if len(args) < 1:
        raise ExecutionError("git_commit 需要至少一个参数: [message]")
    
    message = args[0]
    
    # 检查是否有暂存的更改
    status = _run_git_cmd(executor, ["status", "--porcelain"])
    if not status:
        logger.warning("⚠️  [Git] 没有检测到暂存的更改，跳过提交。")
        return

    # 这里我们认为 commit 是一个副作用操作，询问确认
    # 但由于很难展示 commit 的 diff (需要 git diff --cached)，这里简化为确认消息
    if not executor.request_confirmation(executor.root_dir / ".git", "Staged Changes", f"Commit Message: {message}"):
        logger.warning("❌ [Skip] 用户取消提交")
        return

    _run_git_cmd(executor, ["commit", "-m", message])
    logger.info(f"✅ [Git] 提交成功: {message}")

def _git_status(executor: Executor, args: List[str]):
    """
    Act: git_status
    Args: []
    仅打印状态日志
    """
    status = _run_git_cmd(executor, ["status"])
    logger.info(f"ℹ️  [Git Status]\n{status}")