import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple
import yaml
import re
from datetime import datetime

from .git_db import GitDB
from .history import load_history_graph
from .config import ConfigManager
from quipu.core.models import QuipuNode

logger = logging.getLogger(__name__)

class Engine:
    """
    Axon 状态引擎。
    负责协调 Git 物理状态和 Axon 逻辑图谱。
    """

    def _sync_persistent_ignores(self):
        """将 config.yml 中的持久化忽略规则同步到 .git/info/exclude。"""
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

            # 使用 re.DOTALL (s) 标志来匹配包括换行符在内的任何字符
            managed_block_pattern = re.compile(rf"{re.escape(header)}.*{re.escape(footer)}", re.DOTALL)
            
            new_block = f"{header}\n" + "\n".join(patterns) + f"\n{footer}"

            new_content, count = managed_block_pattern.subn(new_block, content)
            if count == 0:
                # 如果没有找到匹配项，则在末尾追加
                if content and not content.endswith("\n"):
                    content += "\n"
                new_content = content + "\n" + new_block + "\n"
            
            if new_content != content:
                exclude_file.write_text(new_content, "utf-8")
                logger.debug("✅ .git/info/exclude 已更新。")

        except Exception as e:
            logger.warning(f"⚠️  无法同步持久化忽略规则: {e}")

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.quipu_dir = self.root_dir / ".quipu"
        self.history_dir = self.quipu_dir / "history"
        self.head_file = self.quipu_dir / "HEAD"
        
        # Navigation History Files
        self.nav_log_file = self.quipu_dir / "nav_log"
        self.nav_ptr_file = self.quipu_dir / "nav_ptr"
        
        # 确保目录结构存在
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # 核心：确保 .quipu 目录被 Git 忽略
        quipu_gitignore = self.quipu_dir / ".gitignore"
        if not quipu_gitignore.exists():
            try:
                quipu_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {quipu_gitignore}: {e}")
        
        self.git_db = GitDB(self.root_dir)
        self.history_graph: Dict[str, QuipuNode] = {}
        self.current_node: Optional[QuipuNode] = None

        # 自动同步本地配置，如持久化忽略规则
        self._sync_persistent_ignores()

    def _read_head(self) -> Optional[str]:
        """读取 .quipu/HEAD 文件中的 Hash"""
        if self.head_file.exists():
            return self.head_file.read_text(encoding="utf-8").strip()
        return None

    def _write_head(self, tree_hash: str):
        """更新 .quipu/HEAD"""
        try:
            self.head_file.write_text(tree_hash, encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️  无法更新 HEAD 指针: {e}")

    # --- Navigation History Logic ---

    def _read_nav(self) -> Tuple[List[str], int]:
        """读取导航日志和指针。如果文件不存在则返回空列表和-1。"""
        log = []
        ptr = -1
        
        if self.nav_log_file.exists():
            try:
                content = self.nav_log_file.read_text(encoding="utf-8").strip()
                if content:
                    log = content.splitlines()
            except Exception: pass
            
        if self.nav_ptr_file.exists():
            try:
                ptr = int(self.nav_ptr_file.read_text(encoding="utf-8").strip())
            except Exception: pass
            
        # 简单的完整性检查
        if not log:
            ptr = -1
        elif ptr < 0:
            ptr = 0
        elif ptr >= len(log):
            ptr = len(log) - 1
            
        return log, ptr

    def _write_nav(self, log: List[str], ptr: int):
        """写入导航日志和指针。"""
        try:
            self.nav_log_file.write_text("\n".join(log), encoding="utf-8")
            self.nav_ptr_file.write_text(str(ptr), encoding="utf-8")
        except Exception as e:
            logger.warning(f"⚠️  无法更新导航历史: {e}")

    def _append_nav(self, tree_hash: str):
        """
        核心逻辑：访问新状态。
        1. 如果是全新的历史（空 log），且当前有 HEAD，先将当前 HEAD 记入（作为起点）。
        2. 截断当前指针之后的所有记录（类似浏览器访问新页面）。
        3. 追加新记录。
        4. 移动指针到末尾。
        """
        log, ptr = self._read_nav()
        
        # 处理初始化：如果 log 为空，但我们已经在某个状态了（比如 HEAD），应该把起点也记下来
        if not log:
            current_head = self._read_head()
            # 只有当 current_head 存在且不等于我们要去的新 hash 时才记录起点
            # 如果等于，说明是原地踏步或者初始化同步，直接记一个就行
            if current_head and current_head != tree_hash:
                log.append(current_head)
                ptr = 0
        
        # 截断历史
        if ptr < len(log) - 1:
            log = log[:ptr+1]
        
        # 避免连续重复记录 (Idempotency)
        if log and log[-1] == tree_hash:
            # 已经在目标状态，且是在末尾，不需要重复记录，但要确保指针正确
            ptr = len(log) - 1
            self._write_nav(log, ptr)
            return

        log.append(tree_hash)
        ptr = len(log) - 1
        
        # 可选：限制日志长度（例如保留最近 100 条）
        MAX_LOG_SIZE = 100
        if len(log) > MAX_LOG_SIZE:
            log = log[-MAX_LOG_SIZE:]
            ptr = len(log) - 1
            
        self._write_nav(log, ptr)

    # --- Public Navigation API ---

    def visit(self, target_hash: str):
        """
        高级导航：切换到目标状态，并将其记入访问历史。
        用于 checkout, undo, redo 等用户显式操作。
        """
        # 1. 先执行物理切换 (可能会失败)
        self.checkout(target_hash)
        # 2. 成功后记录历史
        self._append_nav(target_hash)

    def back(self) -> Optional[str]:
        """
        时序后退：移动指针到上一个记录，并切换状态。
        """
        log, ptr = self._read_nav()
        if ptr > 0:
            new_ptr = ptr - 1
            target_hash = log[new_ptr]
            
            logger.info(f"🔙 Back to: {target_hash[:7]} (History: {new_ptr + 1}/{len(log)})")
            self.checkout(target_hash)
            
            # 只有 checkout 成功才更新指针
            self._write_nav(log, new_ptr)
            return target_hash
        return None

    def forward(self) -> Optional[str]:
        """
        时序前进：移动指针到下一个记录，并切换状态。
        """
        log, ptr = self._read_nav()
        if ptr < len(log) - 1:
            new_ptr = ptr + 1
            target_hash = log[new_ptr]
            
            logger.info(f"🔜 Forward to: {target_hash[:7]} (History: {new_ptr + 1}/{len(log)})")
            self.checkout(target_hash)
            
            # 只有 checkout 成功才更新指针
            self._write_nav(log, new_ptr)
            return target_hash
        return None

    # --- Existing Methods ---

    def align(self) -> str:
        """
        核心对齐方法：确定 "我现在在哪"。
        返回状态: "CLEAN", "DIRTY", "ORPHAN"
        """
        # 1. 加载或重新加载历史
        self.history_graph = load_history_graph(self.history_dir)
        
        # 2. 获取当前物理状态
        current_hash = self.git_db.get_tree_hash()

        # 3. 特殊情况：处理创世状态 (空仓库)
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        if current_hash == EMPTY_TREE_HASH and not self.history_graph:
            logger.info("✅ 状态对齐：检测到创世状态 (空仓库)。")
            self.current_node = None
            # 创世状态不写入 HEAD，或者写入空？暂不写入。
            return "CLEAN"
        
        # 4. 在逻辑图谱中定位
        if current_hash in self.history_graph:
            self.current_node = self.history_graph[current_hash]
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            # 对齐成功，更新 HEAD
            self._write_head(current_hash)
            return "CLEAN"
        
        # 未找到匹配节点，进入漂移检测
        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
        
        if not self.history_graph:
            return "ORPHAN" # 历史为空，但工作区非空
        
        return "DIRTY"

    def capture_drift(self, current_hash: str, message: Optional[str] = None) -> QuipuNode:
        """
        捕获当前工作区的漂移，生成一个新的 CaptureNode。
        """
        log_message = f"📸 正在捕获工作区漂移 (Message: {message})" if message else f"📸 正在捕获工作区漂移"
        logger.info(f"{log_message}，新状态 Hash: {current_hash[:7]}")

        # 1. 确定父节点 (input_tree)
        # 优先使用 HEAD 指针，其次尝试从历史中推断，最后回退到创世 Hash
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        input_hash = genesis_hash
        
        head_hash = self._read_head()
        if head_hash and head_hash in self.history_graph:
            input_hash = head_hash
        elif self.history_graph:
            # Fallback: 使用时间戳最新的节点（风险：可能导致跳线，但在无 HEAD 时是唯一选择）
            last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
            input_hash = last_node.output_tree
            logger.warning(f"⚠️  丢失 HEAD 指针，自动回退到最新历史节点: {input_hash[:7]}")
        
        # 获取父 Commit 用于 Git 锚定
        last_commit_hash = None
        res = self.git_db._run(["rev-parse", "refs/quipu/history"], check=False)
        if res.returncode == 0:
            last_commit_hash = res.stdout.strip()

        # 2. 生成差异摘要
        diff_summary = self.git_db.get_diff_stat(input_hash, current_hash)
        
        # 3. 构建节点内容和元数据
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_hash}_{current_hash}_{ts_str}.md"
        
        meta = {"type": "capture", "input_tree": input_hash, "output_tree": current_hash}
        
        user_message_section = f"### 💬 备注:\n{message}\n\n" if message else ""
        body = (
            f"# 📸 Snapshot Capture\n\n"
            f"{user_message_section}"
            f"检测到工作区发生变更。\n\n"
            f"### 📝 变更文件摘要:\n```\n{diff_summary}\n```"
        )
        
        # 4. 写入文件
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"
        filename.write_text(frontmatter + body, "utf-8")
        
        # 5. 创建锚点 Commit
        commit_msg = f"Axon Save: {message}" if message else f"Axon Capture: {current_hash[:7]}"
        parents = [last_commit_hash] if last_commit_hash else []
        new_commit_hash = self.git_db.create_anchor_commit(current_hash, commit_msg, parent_commits=parents)
        self.git_db.update_ref("refs/quipu/history", new_commit_hash)

        # 6. 更新内存状态
        new_node = QuipuNode(
            input_tree=input_hash,
            output_tree=current_hash,
            timestamp=timestamp,
            filename=filename,
            node_type="capture",
            content=body
        )
        
        self.history_graph[current_hash] = new_node
        self.current_node = new_node
        
        # 7. 关键：更新 HEAD 指向新的捕获节点
        self._write_head(current_hash)
        
        # 8. 导航日志更新
        self._append_nav(current_hash)
        
        logger.info(f"✅ 捕获完成，新节点已创建: {filename.name}")
        return new_node

    def create_plan_node(self, input_tree: str, output_tree: str, plan_content: str) -> QuipuNode:
        """
        将一次成功的 Plan 执行固化为历史节点。
        """
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")
        
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_tree}_{output_tree}_{ts_str}.md"
        
        meta = {
            "type": "plan",
            "input_tree": input_tree,
            "output_tree": output_tree
        }
        
        body = f"{plan_content.strip()}\n"
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"
        
        filename.write_text(frontmatter + body, "utf-8")
        
        # Git 锚定逻辑...
        parent_commit = None
        try:
            res = self.git_db._run(["rev-parse", "refs/quipu/history"], check=False)
            if res.returncode == 0:
                parent_commit = res.stdout.strip()
        except Exception: pass
            
        commit_msg = f"Axon Plan: {output_tree[:7]}"
        parents = [parent_commit] if parent_commit else []
        
        new_commit_hash = self.git_db.create_anchor_commit(output_tree, commit_msg, parent_commits=parents)
        self.git_db.update_ref("refs/quipu/history", new_commit_hash)
        
        new_node = QuipuNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=timestamp,
            filename=filename,
            node_type="plan",
            content=body
        )
        
        self.history_graph[output_tree] = new_node
        self.current_node = new_node
        
        # 关键：更新 HEAD
        self._write_head(output_tree)

        # 导航日志更新
        self._append_nav(output_tree)
        
        logger.info(f"✅ Plan 已归档: {filename.name}")
        return new_node

    def checkout(self, target_hash: str):
        """
        将工作区重置到指定状态，并更新 HEAD 指针。
        注意：此方法不负责更新导航日志，它是底层操作。
        """
        # 1. 执行物理检出
        self.git_db.checkout_tree(target_hash)
        
        # 2. 更新 HEAD 指针
        self._write_head(target_hash)
        
        # 3. 尝试更新内存中的当前节点状态
        if target_hash in self.history_graph:
            self.current_node = self.history_graph[target_hash]
        
        logger.info(f"🔄 状态已切换至: {target_hash[:7]}")