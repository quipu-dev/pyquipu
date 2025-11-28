## fix: 修复在严格 .gitignore 环境中 git add 失败的问题

你说得对，我为我之前的两个错误方案道歉。你的判断是正确的，简单地列出顶层文件会遇到和 `git add .` 完全相同的问题，因为我们仍然在显式地要求 Git 添加它已经被告知要忽略的文件。全局 `--force` 更是不可接受的。

这个问题比看起来更棘手，它触及了 Git 命令设计的核心。感谢你的坚持，这让我重新思考并找到了一个更健壮、更符合 Git 工作方式的解决方案。

### 错误分析
我之前两个方案的共同缺陷在于，它们都试图“自作聪明”地告诉 `git add` 要添加什么。而正确的思路应该是，让 Git 自己去判断哪些是它应该追踪的变更，我们只需要再进行一次精确的“排除法”操作。

1.  **`git add -A` 的正确用法**: 当不带任何路径参数执行时，`git add -A` 的意图是“暂存工作区中所有跟踪文件的修改、所有未跟踪的新文件以及所有被删除的文件”。在这个模式下，它会**自动且高效地应用所有的 `.gitignore` 规则**，因为它是在操作整个工作区的“状态”，而不是我们提供给它的具体“路径列表”。这从根本上解决了之前所有的问题。
2.  **`.quipu` 的最终排除**: 虽然 `quipu` 在 `.quipu` 目录内创建了 `.gitignore` 文件来忽略其内容，但在复杂的 `.gitignore` 规则下（例如，父目录有 `!/.quipu` 规则），我们不能百分之百保证 `.quipu` 目录本身不会被意外加入。因此，我们需要一个绝对可靠的“清理”步骤。
3.  **精确的清理工具**: `git rm --cached -r <path>` 是一个完美的工具。它能将一个文件或目录从**暂存区 (index)** 中移除，但**不会**触碰工作区的文件。这正是我们在影子索引中需要的操作：在计算快照前，确保我们自己的数据被彻底排除。

### 解决方案
我们将采用一个两阶段的方法来构建纯净的影子索引：

1.  **第一阶段 (全量添加)**: 调用 `git add -A`，不带任何路径。这会安全地将所有非忽略的变更添加到影子索引中。
2.  **第二阶段 (精确排除)**: 紧接着，调用 `git rm --cached -r .quipu`。这将从影子索引中可靠地移除 `.quipu` 目录及其所有内容，以防它在第一阶段被意外加入。

这个方法是健壮的，因为它完全依赖 Git 自身的机制来处理忽略规则，并且通过一个独立的、明确的命令来保证自身数据的隔离性。

### 标签
#intent/fix #flow/ready #priority/high #comp/engine #concept/state #scope/core #ai/instruct #task/domain/storage #task/object/git-backend #task/action/bug-fix #task/state/end

---

### Script

#### Acts 1: 实现两阶段索引构建逻辑

我们将再次修改 `quipu-engine` 包中的 `git_db.py` 文件，用新的两阶段逻辑替换 `get_tree_hash` 的实现。

~~~~~act
write_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
import os
import subprocess
import logging
import shutil
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Union
from contextlib import contextmanager
from quipu.core.exceptions import ExecutionError

logger = logging.getLogger(__name__)


class GitDB:
    """
    Quipu 的 Git 底层接口 (Plumbing Interface)。
    负责与 Git 对象数据库交互，维护 Shadow Index 和 Refs。
    """

    def __init__(self, root_dir: Path):
        if not shutil.which("git"):
            raise ExecutionError("未找到 'git' 命令。请安装 Git 并确保它在系统的 PATH 中。")

        self.root = root_dir.resolve()
        self.quipu_dir = self.root / ".quipu"
        self._ensure_git_repo()

    def _ensure_git_repo(self):
        """确保目标是一个 Git 仓库"""
        if not (self.root / ".git").is_dir():
            # 这是一个关键的前置条件检查
            raise ExecutionError(f"工作目录 '{self.root}' 不是一个有效的 Git 仓库。请先运行 'git init'。")

    def _run(
        self,
        args: list[str],
        env: Optional[Dict] = None,
        check: bool = True,
        log_error: bool = True,
        input_data: Optional[str] = None,
    ) -> subprocess.CompletedProcess:
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
                check=check,
                input=input_data,
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
        index_path = self.quipu_dir / "tmp_index"
        self.quipu_dir.mkdir(exist_ok=True)

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
            # --- 两阶段构建纯净索引 ---

            # 阶段 1: 添加所有变更。
            # 使用 `git add -A` (不带路径) 可以让 Git 自行处理所有 .gitignore 规则，
            # 这是最健壮的方式，可以避免因手动提供路径而导致的错误。
            self._run(["add", "-A", "--ignore-errors"], env=env)

            # 阶段 2: 显式移除 .quipu 目录。
            # 这是一个“安全网”，确保无论 .gitignore 规则多复杂，
            # Quipu 自身的数据都绝不会被包含在状态快照中。
            # `--cached` 确保只从索引中移除，不影响工作区文件。
            # `-r` 用于递归删除目录。
            # `check=False` 是因为如果 .quipu 未被添加，此命令会失败，但这属于正常情况。
            self._run(["rm", "--cached", "-r", ".quipu"], env=env, check=False)

            # 3. 将索引写入对象库，返回 Tree Hash
            result = self._run(["write-tree"], env=env)
            return result.stdout.strip()

    def hash_object(self, content_bytes: bytes, object_type: str = "blob") -> str:
        """
        将内容写入 Git 对象数据库并返回对象哈希。
        """
        try:
            result = subprocess.run(
                ["git", "hash-object", "-w", "-t", object_type, "--stdin"],
                cwd=self.root,
                input=content_bytes,
                capture_output=True,
                check=True,
            )
            return result.stdout.decode("utf-8").strip()
        except subprocess.CalledProcessError as e:
            stderr_str = e.stderr.decode("utf-8") if e.stderr else "No stderr"
            logger.error(f"Git hash-object failed: {stderr_str}")
            raise RuntimeError(f"Git command failed: hash-object\n{stderr_str}") from e

    def mktree(self, tree_descriptor: str) -> str:
        """
        从描述符创建 tree 对象并返回其哈希。
        """
        result = self._run(["mktree"], input_data=tree_descriptor)
        return result.stdout.strip()

    def commit_tree(self, tree_hash: str, parent_hashes: Optional[List[str]], message: str) -> str:
        """
        创建一个 commit 对象并返回其哈希。
        """
        cmd = ["commit-tree", tree_hash]
        if parent_hashes:
            for p in parent_hashes:
                cmd.extend(["-p", p])

        result = self._run(cmd, input_data=message)
        return result.stdout.strip()

    def update_ref(self, ref_name: str, commit_hash: str):
        """
        更新引用 (如 refs/quipu/history)。
        防止 Commit 被 GC 回收。
        """
        self._run(["update-ref", ref_name, commit_hash])

    def delete_ref(self, ref_name: str):
        """删除指定的引用"""
        self._run(["update-ref", "-d", ref_name], check=False)

    def get_commit_by_output_tree(self, tree_hash: str) -> Optional[str]:
        """
        根据 Trailer 中的 X-Quipu-Output-Tree 查找对应的 Commit Hash。
        用于在创建新节点时定位语义上的父节点。
        """
        # 使用 grep 搜索所有 refs/quipu/ 下的记录
        # 注意：这假设 Output Tree 是唯一的，这在大概率上是成立的，
        # 且即使有重复（如 merge），找到任意一个作为父节点通常也是可接受的起点。
        cmd = ["log", "--all", f"--grep=X-Quipu-Output-Tree: {tree_hash}", "--format=%H", "-n", "1"]
        res = self._run(cmd, check=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        return None

    def get_head_commit(self) -> Optional[str]:
        """获取当前工作区 HEAD 的 Commit Hash"""
        try:
            result = self._run(["rev-parse", "HEAD"])
            return result.stdout.strip()
        except RuntimeError:
            return None  # 可能是空仓库

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        """
        判断两个 Commit 是否具有血统关系。
        用于解决 'Lost Time' 问题。
        """
        # merge-base --is-ancestor A B 返回 0 表示真，1 表示假
        # 我们在这里直接调用 subprocess，因为我们关心返回码而不是输出
        result = self._run(
            ["merge-base", "--is-ancestor", ancestor, descendant],
            check=False,  # 必须禁用 check，否则非 0 退出码会抛异常
            log_error=False,  # 我们不认为这是一个错误
        )
        return result.returncode == 0

    def get_diff_stat(self, old_tree: str, new_tree: str) -> str:
        """
        获取两个 Tree 之间的差异统计 (Human Readable)。
        """
        result = self._run(["diff-tree", "--stat", old_tree, new_tree])
        return result.stdout.strip()

    def get_diff_name_status(self, old_tree: str, new_tree: str) -> List[Tuple[str, str]]:
        """
        获取两个 Tree 之间的文件变更状态列表 (M, A, D, etc.)。
        """
        result = self._run(["diff-tree", "--name-status", "--no-commit-id", "-r", old_tree, new_tree])
        changes = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                status, path = parts
                changes.append((status, path))
        return changes

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
        # -d: 目录, -f: 强制
        # 移除了 -x 参数，以尊重 .gitignore 规则
        # -e .quipu: 排除 .quipu 目录，防止自毁
        self._run(["clean", "-df", "-e", ".quipu"])

        logger.info("✅ Workspace reset to target state.")

    def cat_file(self, object_hash: str, object_type: str = "blob") -> bytes:
        """读取 Git 对象的内容，返回字节流。"""
        # 使用 -p (pretty print) for commits/trees, and no flag for blobs
        cmd = ["cat-file"]
        if object_type in ["commit", "tree"]:
            cmd.append("-p")
        else:
            cmd.append(object_type)
        cmd.append(object_hash)

        result = self._run(cmd)
        return result.stdout.encode("utf-8")

    def batch_cat_file(self, object_hashes: List[str]) -> Dict[str, bytes]:
        """
        批量读取 Git 对象。
        解决 N+1 查询性能问题。

        Args:
            object_hashes: 需要读取的对象哈希列表 (可以重复，内部会自动去重)

        Returns:
            Dict[hash, content_bytes]: 哈希到内容的映射。
            如果对象不存在，则不会出现在返回字典中。
        """
        if not object_hashes:
            return {}

        # Deduplicate
        unique_hashes = list(set(object_hashes))

        # Prepare input: <hash>\n
        input_str = "\n".join(unique_hashes) + "\n"

        results = {}

        try:
            # git cat-file --batch format:
            # <hash> <type> <size>\n
            # <content>\n
            with subprocess.Popen(
                ["git", "cat-file", "--batch"],
                cwd=self.root,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                # bufsize=0 is often recommended for binary streams but careful buffering is usually fine
            ) as proc:
                # Write requests and close stdin to signal EOF
                if proc.stdin:
                    proc.stdin.write(input_str.encode("utf-8"))
                    proc.stdin.close()

                if not proc.stdout:
                    return {}

                while True:
                    # Read header line
                    header_line = proc.stdout.readline()
                    if not header_line:
                        break

                    header_parts = header_line.strip().split()
                    if not header_parts:
                        continue

                    obj_hash_bytes = header_parts[0]
                    obj_hash = obj_hash_bytes.decode("utf-8")

                    # Check for missing object: "<hash> missing"
                    if len(header_parts) == 2 and header_parts[1] == b"missing":
                        continue

                    if len(header_parts) < 3:
                        logger.warning(f"Unexpected git cat-file header: {header_line}")
                        continue

                    # size is at index 2
                    try:
                        size = int(header_parts[2])
                    except ValueError:
                        logger.warning(f"Invalid size in header: {header_line}")
                        continue

                    # Read content bytes + trailing newline
                    content = proc.stdout.read(size)
                    proc.stdout.read(1)  # Consume the trailing LF

                    results[obj_hash] = content

        except Exception as e:
            logger.error(f"Batch cat-file failed: {e}")
            raise RuntimeError(f"Git batch operation failed: {e}") from e

        return results

    def get_all_ref_heads(self, prefix: str) -> List[Tuple[str, str]]:
        """
        查找指定前缀下的所有 ref heads。
        返回 (commit_hash, ref_name) 元组列表。
        """
        res = self._run(["for-each-ref", f"--format=%(objectname) %(refname)", prefix], check=False)
        if res.returncode != 0 or not res.stdout.strip():
            return []
        
        results = []
        for line in res.stdout.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                results.append((parts[0], parts[1]))
        return results

    def has_quipu_ref(self) -> bool:
        """检查是否存在任何 'refs/quipu/' 引用，用于判断存储格式。"""
        # We use show-ref and check the exit code. Exit 0 if refs exist, 1 otherwise.
        res = self._run(["show-ref", "--verify", "--quiet", "refs/quipu/"], check=False, log_error=False)
        return res.returncode == 0

    def log_ref(self, ref_names: Union[str, List[str]]) -> List[Dict[str, str]]:
        """获取指定引用的日志，并解析为结构化数据列表。"""
        # A unique delimiter that's unlikely to appear in commit messages
        DELIMITER = "---QUIPU-LOG-ENTRY---"
        # Format: H=hash, P=parent, T=tree, ct=commit_timestamp, B=body
        log_format = f"%H%n%P%n%T%n%ct%n%B{DELIMITER}"

        if isinstance(ref_names, str):
            refs_to_log = [ref_names]
        else:
            refs_to_log = ref_names

        if not refs_to_log:
            return []

        # Git log on multiple refs will automatically show the union of their histories without duplicates.
        cmd = ["log", f"--format={log_format}"] + refs_to_log
        res = self._run(cmd, check=False, log_error=False)

        if res.returncode != 0:
            return []

        entries = res.stdout.strip().split(DELIMITER)
        parsed_logs = []
        for entry in entries:
            if not entry.strip():
                continue

            parts = entry.strip().split("\n", 4)
            if len(parts) >= 4:
                parsed_logs.append(
                    {
                        "hash": parts[0],
                        "parent": parts[1],
                        "tree": parts[2],
                        "timestamp": parts[3],
                        "body": parts[4] if len(parts) > 4 else "",
                    }
                )
        return parsed_logs

    def push_quipu_refs(self, remote: str, user_id: str):
        """
        将本地 Quipu heads 推送到远程用户专属的命名空间。
        遵循 QDPS v1.1 规范。
        """
        refspec = f"refs/quipu/local/heads/*:refs/quipu/users/{user_id}/heads/*"
        logger.info(f"🚀 Pushing Quipu history to {remote} for user {user_id}...")
        self._run(["push", remote, "--prune", refspec])

    def fetch_quipu_refs(self, remote: str, user_id: str):
        """
        从远程用户专属命名空间拉取 Quipu heads 到本地镜像。
        遵循 QDPS v1.1 规范。
        """
        refspec = f"refs/quipu/users/{user_id}/heads/*:refs/quipu/remotes/{remote}/{user_id}/heads/*"
        logger.info(f"🔍 Fetching Quipu history from {remote} for user {user_id}...")
        self._run(["fetch", remote, "--prune", refspec])
~~~~~
