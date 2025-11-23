import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict
from contextlib import contextmanager
from .exceptions import ExecutionError

logger = logging.getLogger(__name__)

class GitDB:
    """
    Axon 的 Git 底层接口 (Plumbing Interface)。
    负责与 Git 对象数据库交互，维护 Shadow Index 和 Refs。
    """
    def __init__(self, root_dir: Path):
        if not shutil.which("git"):
            raise ExecutionError("未找到 'git' 命令。请安装 Git 并确保它在系统的 PATH 中。")

        self.root = root_dir.resolve()
        self.axon_dir = self.root / ".axon"
        self._ensure_git_repo()

    def _ensure_git_repo(self):
        """确保目标是一个 Git 仓库"""
        if not (self.root / ".git").is_dir():
            # 这是一个关键的前置条件检查
            raise ExecutionError(f"工作目录 '{self.root}' 不是一个有效的 Git 仓库。请先运行 'git init'。")

    def _run(self, args: list[str], env: Optional[Dict] = None, check: bool = True, log_error: bool = True) -> subprocess.CompletedProcess:
        """执行 git 命令的底层封装，返回完整的 CompletedProcess 对象"""
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
            
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.root,
                env=full_env,
                capture_output=True,
                text=True,
                check=check
            )
            return result
        except subprocess.CalledProcessError as e:
            if log_error:
                logger.error(f"Git plumbing error: {e.stderr}")
            raise RuntimeError(f"Git command failed: {' '.join(args)}\n{e.stderr}") from e

    @contextmanager
    def shadow_index(self):
        """
        上下文管理器：创建一个隔离的 Shadow Index。
        在此上下文内的操作不会污染用户的 .git/index。
        """
        index_path = self.axon_dir / "tmp_index"
        self.axon_dir.mkdir(exist_ok=True)
        
        # 定义隔离的环境变量
        env = {"GIT_INDEX_FILE": str(index_path)}
        
        try:
            yield env
        finally:
            # 无论成功失败，必须清理临时索引文件
            if index_path.exists():
                try:
                    index_path.unlink()
                except OSError:
                    logger.warning(f"Failed to cleanup shadow index: {index_path}")

    def get_tree_hash(self) -> str:
        """
        计算当前工作区的 Tree Hash (Snapshot)。
        实现 'State is Truth' 的核心。
        """
        with self.shadow_index() as env:
            # 1. 将当前工作区全量加载到影子索引
            # 使用 ':(exclude).axon' 确保 Axon 自身数据不影响状态计算
            # -A: 自动处理添加、修改、删除
            # --ignore-errors: 即使某些文件无法读取也继续（尽力而为）
            self._run(
                ["add", "-A", "--ignore-errors", ".", ":(exclude).axon"],
                env=env
            )
            
            # 2. 将索引写入对象库，返回 Tree Hash
            result = self._run(["write-tree"], env=env)
            return result.stdout.strip()

    def create_anchor_commit(self, tree_hash: str, message: str, parent_commits: list[str] = None) -> str:
        """
        创建一个 Commit Object 指向特定的 Tree Hash。
        这是 Axon 历史链的物理载体。
        """
        cmd = ["commit-tree", tree_hash, "-m", message]
        
        if parent_commits:
            for p in parent_commits:
                cmd.extend(["-p", p])
                
        result = self._run(cmd)
        return result.stdout.strip()

    def update_ref(self, ref_name: str, commit_hash: str):
        """
        更新引用 (如 refs/axon/history)。
        防止 Commit 被 GC 回收。
        """
        self._run(["update-ref", ref_name, commit_hash])

    def get_head_commit(self) -> Optional[str]:
        """获取当前工作区 HEAD 的 Commit Hash"""
        try:
            result = self._run(["rev-parse", "HEAD"])
            return result.stdout.strip()
        except RuntimeError:
            return None # 可能是空仓库

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """
        判断两个 Commit 是否具有血统关系。
        用于解决 'Lost Time' 问题。
        """
        # merge-base --is-ancestor A B 返回 0 表示真，1 表示假
        # 我们在这里直接调用 subprocess，因为我们关心返回码而不是输出
        result = self._run(
            ["merge-base", "--is-ancestor", ancestor, descendant],
            check=False, # 必须禁用 check，否则非 0 退出码会抛异常
            log_error=False # 我们不认为这是一个错误
        )
        return result.returncode == 0

    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        """
        获取两个 Tree 之间的差异统计 (Human Readable)。
        """
        result = self._run(["diff-tree", "--stat", old_tree, new_tree])
        return result.stdout.strip()

    def checkout_tree(self, tree_hash: str):
        """
        将工作区强制重置为目标 Tree 的状态。
        这是一个底层方法，上层应确保工作区的未提交更改已被处理。
        """
        logger.info(f"Executing hard checkout to tree: {tree_hash[:7]}")
        
        # 1. 使用 read-tree 更新索引，这是一个安全的操作
        self._run(["read-tree", tree_hash])
        
        # 2. 从更新后的索引检出文件，-a (all) -f (force)
        self._run(["checkout-index", "-a", "-f"])
        
        # 3. 清理工作区中多余的文件和目录
        # -d: 目录, -f: 强制, -x: 包含忽略文件
        # -e .axon: 排除 .axon 目录，防止自毁
        self._run(["clean", "-dfx", "-e", ".axon"])
        
        logger.info("✅ Workspace reset to target state.")