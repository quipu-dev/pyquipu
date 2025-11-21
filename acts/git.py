import subprocess
import logging
import shlex
from typing import List
from core.executor import Executor, ExecutionError

logger = logging.getLogger(__name__)

def register_git_acts(executor: Executor):
    """注册 Git 相关操作"""
    # git_init: 无参数，Exclusive 模式更安全，防止误吸入后续块
    executor.register("git_init", _git_init, arg_mode="exclusive")
    
    # git_add: Exclusive 模式
    # 写法 A: git_add file1 file2 (忽略块)
    # 写法 B: git_add (读取块)
    executor.register("git_add", _git_add, arg_mode="exclusive")
    
    # git_commit: Block Only 模式
    # 强制忽略行内参数，防止 AI 写 git_commit -m "msg" 导致解析混乱，强制要求消息在块中
    executor.register("git_commit", _git_commit, arg_mode="block_only")
    
    executor.register("git_status", _git_status, arg_mode="exclusive")

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
    Args: [files] (空白符分隔的文件列表)
    """
    if not args:
        target = "."
        targets = [target]
    else:
        # Exclusive 模式下，args 可能来源：
        # 1. 行内参数: ["file1", "file2"]
        # 2. 块参数: ["file1\nfile2"]
        # 我们需要统一展平
        targets = []
        for arg in args:
            # split() 不带参数会同时处理空格和换行符
            targets.extend(arg.split())
    
    if not targets:
        targets = ["."]

    _run_git_cmd(executor, ["add"] + targets)
    logger.info(f"✅ [Git] 已添加文件: {targets}")

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

    # 确认
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