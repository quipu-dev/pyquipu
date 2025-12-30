import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pyquipu.common.identity import get_user_id_from_email
from pyquipu.interfaces.models import QuipuNode
from pyquipu.interfaces.storage import HistoryReader, HistoryWriter

from .config import ConfigManager
from .git_db import GitDB
from .hydrator import Hydrator

# 导入类型以进行类型提示
try:
    from .sqlite_db import DatabaseManager
except ImportError:
    DatabaseManager = None

logger = logging.getLogger(__name__)


class Engine:
    def _sync_persistent_ignores(self):
        try:
            config = ConfigManager(self.root_dir)
            patterns = config.get("sync.persistent_ignores", [])
            if not patterns:
                return

            exclude_file = self.root_dir / ".git" / "info" / "exclude"
            exclude_file.parent.mkdir(exist_ok=True)

            header = "# --- Managed by Quipu ---"
            footer = "# --- End Managed by Quipu ---"

            content = ""
            if exclude_file.exists():
                content = exclude_file.read_text("utf-8")

            managed_block_pattern = re.compile(rf"{re.escape(header)}.*{re.escape(footer)}", re.DOTALL)

            new_block = f"{header}\n" + "\n".join(patterns) + f"\n{footer}"

            new_content, count = managed_block_pattern.subn(new_block, content)
            if count == 0:
                if content and not content.endswith("\n"):
                    content += "\n"
                new_content = content + "\n" + new_block + "\n"

            if new_content != content:
                exclude_file.write_text(new_content, "utf-8")
                logger.debug("✅ .git/info/exclude 已更新。")

        except Exception as e:
            logger.warning(f"⚠️  无法同步持久化忽略规则: {e}")

    def __init__(
        self,
        root_dir: Path,
        db: Any,
        reader: HistoryReader,
        writer: HistoryWriter,
        db_manager: Optional[Any] = None,
    ):
        self.root_dir = root_dir.resolve()
        self.quipu_dir = self.root_dir / ".quipu"
        self.quipu_dir.mkdir(exist_ok=True)
        self.history_dir = self.quipu_dir / "history"
        self.head_file = self.quipu_dir / "HEAD"

        self.nav_log_file = self.quipu_dir / "nav_log"
        self.nav_ptr_file = self.quipu_dir / "nav_ptr"

        quipu_gitignore = self.quipu_dir / ".gitignore"
        if not quipu_gitignore.exists():
            try:
                quipu_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {quipu_gitignore}: {e}")

        self.git_db = db
        self.reader = reader
        self.writer = writer
        self.db_manager = db_manager  # 持有数据库管理器引用
        self.history_graph: Dict[str, QuipuNode] = {}
        self.current_node: Optional[QuipuNode] = None

        if isinstance(db, GitDB):
            self._sync_persistent_ignores()

    def close(self):
        if self.db_manager:
            self.db_manager.close()

    def _get_current_user_id(self) -> str:
        # 1. 尝试从 Quipu 配置中读取
        config = ConfigManager(self.root_dir)
        user_id = config.get("sync.user_id")
        if user_id:
            return user_id

        # 2. 如果配置中没有，则回退到 Git 配置
        try:
            result = subprocess.run(
                ["git", "config", "user.email"],
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            email = result.stdout.strip()
            if email:
                derived_id = get_user_id_from_email(email)
                logger.debug(f"从 Git config 动态获取 user_id: {derived_id}")
                return derived_id
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.debug("无法从 git config 中获取 user.email。")
            pass  # 忽略错误，继续执行最终的回退逻辑

        # 3. 最终回退
        logger.debug("未找到 user_id，将使用默认回退值 'unknown-local-user'。")
        return "unknown-local-user"

    def _read_head(self) -> Optional[str]:
        if self.head_file.exists():
            return self.head_file.read_text(encoding="utf-8").strip()
        return None

    def _write_head(self, tree_hash: str):
        try:
            self.head_file.write_text(tree_hash, encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️  无法更新 HEAD 指针: {e}")

    def _read_nav(self) -> Tuple[List[str], int]:
        log = []
        ptr = -1
        if self.nav_log_file.exists():
            try:
                content = self.nav_log_file.read_text(encoding="utf-8").strip()
                if content:
                    log = content.splitlines()
            except Exception:
                pass
        if self.nav_ptr_file.exists():
            try:
                ptr = int(self.nav_ptr_file.read_text(encoding="utf-8").strip())
            except Exception:
                pass
        if not log:
            ptr = -1
        elif ptr < 0:
            ptr = 0
        elif ptr >= len(log):
            ptr = len(log) - 1
        return log, ptr

    def _write_nav(self, log: List[str], ptr: int):
        try:
            self.nav_log_file.write_text("\n".join(log), encoding="utf-8")
            self.nav_ptr_file.write_text(str(ptr), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️  无法更新导航历史: {e}")

    def _append_nav(self, tree_hash: str):
        log, ptr = self._read_nav()
        if not log:
            current_head = self._read_head()
            if current_head and current_head != tree_hash:
                log.append(current_head)
                ptr = 0
        if ptr < len(log) - 1:
            log = log[: ptr + 1]
        if log and log[-1] == tree_hash:
            ptr = len(log) - 1
            self._write_nav(log, ptr)
            return
        log.append(tree_hash)
        ptr = len(log) - 1
        MAX_LOG_SIZE = 100
        if len(log) > MAX_LOG_SIZE:
            log = log[-MAX_LOG_SIZE:]
            ptr = len(log) - 1
        self._write_nav(log, ptr)

    def visit(self, target_hash: str):
        self.checkout(target_hash)
        self._append_nav(target_hash)

    def back(self) -> Optional[str]:
        log, ptr = self._read_nav()
        if ptr > 0:
            new_ptr = ptr - 1
            target_hash = log[new_ptr]
            logger.info(f"🔙 Back to: {target_hash[:7]} (History: {new_ptr + 1}/{len(log)})")
            self.checkout(target_hash)
            self._write_nav(log, new_ptr)
            return target_hash
        return None

    def forward(self) -> Optional[str]:
        log, ptr = self._read_nav()
        if ptr < len(log) - 1:
            new_ptr = ptr + 1
            target_hash = log[new_ptr]
            logger.info(f"🔜 Forward to: {target_hash[:7]} (History: {new_ptr + 1}/{len(log)})")
            self.checkout(target_hash)
            self._write_nav(log, new_ptr)
            return target_hash
        return None

    def align(self) -> str:
        # 如果使用 SQLite，先进行数据补水
        if self.db_manager:
            try:
                user_id = self._get_current_user_id()
                hydrator = Hydrator(self.git_db, self.db_manager)
                hydrator.sync(local_user_id=user_id)
            except Exception as e:
                logger.error(f"❌ 自动数据补水失败: {e}", exc_info=True)

        all_nodes = self.reader.load_all_nodes()
        self.history_graph = {node.commit_hash: node for node in all_nodes}
        if all_nodes:
            logger.info(f"从存储中加载了 {len(all_nodes)} 个历史事件，形成 {len(self.history_graph)} 个唯一状态节点。")

        current_hash = self.git_db.get_tree_hash()
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        if current_hash == EMPTY_TREE_HASH and not self.history_graph:
            logger.info("✅ 状态对齐：检测到创世状态 (空仓库)。")
            self.current_node = None
            return "CLEAN"

        # Find node by iterating since keys are now commit hashes
        found_node = None
        for node in self.history_graph.values():
            if node.output_tree == current_hash:
                found_node = node
                break

        if found_node:
            self.current_node = found_node
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            self._write_head(current_hash)
            return "CLEAN"

        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
        if not self.history_graph:
            return "ORPHAN"
        return "DIRTY"

    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        return self.reader.find_nodes(
            summary_regex=summary_regex,
            node_type=node_type,
            limit=limit,
        )

    def capture_drift(self, current_hash: str, message: Optional[str] = None) -> QuipuNode:
        log_message = f"📸 正在捕获工作区漂移 (Message: {message})" if message else "📸 正在捕获工作区漂移"
        logger.info(f"{log_message}，新状态 Hash: {current_hash[:7]}")

        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        input_hash = genesis_hash
        head_tree_hash = self._read_head()
        parent_node = None

        if head_tree_hash:
            # 正确的逻辑：遍历节点，用 output_tree 匹配 head 的 tree hash
            parent_node = next(
                (node for node in self.history_graph.values() if node.output_tree == head_tree_hash), None
            )

        if parent_node:
            input_hash = parent_node.output_tree
        elif self.history_graph:
            # 只有当 HEAD 指针无效或丢失时，才执行回退逻辑
            last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
            input_hash = last_node.output_tree
            logger.warning(
                f"⚠️  HEAD 指针 '{head_tree_hash[:7] if head_tree_hash else 'N/A'}' 无效或丢失，"
                f"自动回退到最新历史节点: {input_hash[:7]}"
            )

        diff_summary = self.git_db.get_diff_stat(input_hash, current_hash)
        user_message_section = f"### 💬 备注:\n{message}\n\n" if message else ""
        body = (
            f"# 📸 Snapshot Capture\n\n"
            f"{user_message_section}"
            f"检测到工作区发生变更。\n\n"
            f"### 📝 变更文件摘要:\n```\n{diff_summary}\n```"
        )

        user_id = self._get_current_user_id()

        new_node = self.writer.create_node(
            node_type="capture",
            input_tree=input_hash,
            output_tree=current_hash,
            content=body,
            message=message,
            owner_id=user_id,
        )

        if new_node.parent and new_node.parent.commit_hash in self.history_graph:
            real_parent = self.history_graph[new_node.parent.commit_hash]
            new_node.parent = real_parent
            if new_node not in real_parent.children:
                real_parent.children.append(new_node)

        self.history_graph[new_node.commit_hash] = new_node
        self.current_node = new_node
        self._write_head(current_hash)
        self._append_nav(current_hash)

        logger.info(f"✅ 捕获完成，新节点已创建: {new_node.filename.name}")
        return new_node

    def create_plan_node(
        self, input_tree: str, output_tree: str, plan_content: str, summary_override: Optional[str] = None
    ) -> QuipuNode:
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")

        user_id = self._get_current_user_id()

        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
            owner_id=user_id,
        )

        if new_node.parent and new_node.parent.commit_hash in self.history_graph:
            real_parent = self.history_graph[new_node.parent.commit_hash]
            new_node.parent = real_parent
            if new_node not in real_parent.children:
                real_parent.children.append(new_node)

        self.history_graph[new_node.commit_hash] = new_node
        self.current_node = new_node
        self._write_head(output_tree)
        self._append_nav(output_tree)

        logger.info(f"✅ Plan 已归档: {new_node.filename.name}")
        return new_node

    def checkout(self, target_hash: str):
        # 获取切换前的 tree hash 作为 "old_tree"
        current_head_hash = self._read_head()

        # 调用已优化的 checkout_tree 方法
        self.git_db.checkout_tree(new_tree_hash=target_hash, old_tree_hash=current_head_hash)

        self._write_head(target_hash)
        self.current_node = None
        for node in self.history_graph.values():
            if node.output_tree == target_hash:
                self.current_node = node
                break
        logger.info(f"🔄 状态已切换至: {target_hash[:7]}")
