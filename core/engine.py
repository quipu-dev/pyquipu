import logging
from pathlib import Path
from typing import Dict, Optional
import yaml
from datetime import datetime

from .git_db import GitDB
from .history import load_history_graph
from .models import AxonNode

logger = logging.getLogger(__name__)

class Engine:
    """
    Axon v4.2 状态引擎。
    负责协调 Git 物理状态和 Axon 逻辑图谱。
    """
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.axon_dir = self.root_dir / ".axon"
        self.history_dir = self.axon_dir / "history"
        
        # 确保目录结构存在
        self.history_dir.mkdir(parents=True, exist_ok=True)
        
        # 核心：确保 .axon 目录被 Git 忽略
        # 我们在 .axon 下创建一个 .gitignore 文件，内容为 "*"，
        # 这会告诉 Git 忽略该目录下的所有内容（包括 .gitignore 本身）。
        axon_gitignore = self.axon_dir / ".gitignore"
        if not axon_gitignore.exists():
            try:
                axon_gitignore.write_text("*\n", encoding="utf-8")
            except Exception as e:
                logger.warning(f"无法创建隔离文件 {axon_gitignore}: {e}")
        
        self.git_db = GitDB(self.root_dir)
        self.history_graph: Dict[str, AxonNode] = {}
        self.current_node: Optional[AxonNode] = None

    def align(self) -> str:
        """
        核心对齐方法：确定 "我现在在哪"。
        
        1. 加载历史图谱。
        2. 计算当前工作区的 Tree Hash。
        3. 在图谱中查找该 Hash。
        
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
            self.current_node = None # 此时没有物理节点
            return "CLEAN"
        
        # 4. 在逻辑图谱中定位
        if current_hash in self.history_graph:
            self.current_node = self.history_graph[current_hash]
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            return "CLEAN"
        
        # 未找到匹配节点，进入漂移检测
        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
        
        if not self.history_graph:
            return "ORPHAN" # 历史为空，但工作区非空
        
        return "DIRTY"

    def capture_drift(self, current_hash: str, message: Optional[str] = None) -> AxonNode:
        """
        捕获当前工作区的漂移，生成一个新的 CaptureNode。
        可以附带一条可选的消息。
        """
        log_message = f"📸 正在捕获工作区漂移 (Message: {message})" if message else f"📸 正在捕获工作区漂移"
        logger.info(f"{log_message}，新状态 Hash: {current_hash[:7]}")

        # 1. 确定父节点
        input_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904" # Git Empty Tree Hash
        last_commit_hash = None
        
        if self.history_graph:
            last_node = max(self.history_graph.values(), key=lambda node: node.timestamp)
            input_hash = last_node.output_tree
            parent_ref_commit_result = self.git_db._run(["rev-parse", "refs/axon/history"], check=False)
            if parent_ref_commit_result.returncode == 0:
                last_commit_hash = parent_ref_commit_result.stdout.strip()

        # 2. 生成差异摘要
        diff_summary = self.git_db.get_diff_stat(input_hash, current_hash)
        
        # 3. 构建节点内容和元数据
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_hash}_{current_hash}_{ts_str}.md"
        
        meta = {"type": "capture", "input_tree": input_hash, "output_tree": current_hash}
        
        # 动态构建 Markdown Body
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
        
        # 5. 创建锚点 Commit 并更新引用
        commit_msg = f"Axon Save: {message}" if message else f"Axon Capture: {current_hash[:7]}"
        parents = [last_commit_hash] if last_commit_hash else []
        new_commit_hash = self.git_db.create_anchor_commit(current_hash, commit_msg, parent_commits=parents)
        self.git_db.update_ref("refs/axon/history", new_commit_hash)

        # 6. 在内存中创建并返回新节点
        new_node = AxonNode(
            input_tree=input_hash,
            output_tree=current_hash,
            timestamp=timestamp,
            filename=filename,
            node_type="capture",
            content=body
        )
        
        # 7. 更新引擎内部状态
        self.history_graph[current_hash] = new_node
        self.current_node = new_node
        
        logger.info(f"✅ 捕获完成，新节点已创建: {filename.name}")
        return new_node

    def create_plan_node(self, input_tree: str, output_tree: str, plan_content: str) -> AxonNode:
        """
        将一次成功的 Plan 执行固化为历史节点。
        """
        # v4.3 策略变更：即使状态未发生变更 (Idempotent)，也记录节点。
        # 这允许记录 "Run Tests", "Git Commit" 等无文件副作用但有语义价值的操作。
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")
        
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_tree}_{output_tree}_{ts_str}.md"
        
        # 1. 准备元数据
        meta = {
            "type": "plan",
            "input_tree": input_tree,
            "output_tree": output_tree
        }
        
        # 2. 准备内容：直接保存 Plan 原文
        # 为了避免 Frontmatter 解析混淆，确保 plan_content 前后有换行
        body = f"{plan_content.strip()}\n"
        
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"
        
        # 3. 写入文件
        filename.write_text(frontmatter + body, "utf-8")
        
        # 4. Git 锚定
        # 获取父 Commit (如果存在)
        parent_commit = None
        try:
            res = self.git_db._run(["rev-parse", "refs/axon/history"], check=False)
            if res.returncode == 0:
                parent_commit = res.stdout.strip()
        except Exception:
            pass
            
        commit_msg = f"Axon Plan: {output_tree[:7]}"
        parents = [parent_commit] if parent_commit else []
        
        new_commit_hash = self.git_db.create_anchor_commit(output_tree, commit_msg, parent_commits=parents)
        self.git_db.update_ref("refs/axon/history", new_commit_hash)
        
        # 5. 更新内存状态
        new_node = AxonNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=timestamp,
            filename=filename,
            node_type="plan",
            content=body
        )
        
        self.history_graph[output_tree] = new_node
        self.current_node = new_node
        
        logger.info(f"✅ Plan 已归档: {filename.name}")
        return new_node
