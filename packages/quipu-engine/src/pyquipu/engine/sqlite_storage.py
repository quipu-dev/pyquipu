import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from pyquipu.engine.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from pyquipu.interfaces.models import QuipuNode
from pyquipu.interfaces.storage import HistoryReader, HistoryWriter

from .git_db import GitDB
from .sqlite_db import DatabaseManager

logger = logging.getLogger(__name__)


class SQLiteHistoryReader(HistoryReader):
    def __init__(self, db_manager: DatabaseManager, git_db: GitDB):
        self.db_manager = db_manager
        # git_reader 用于按需加载内容和解析二进制 tree
        self._git_reader = GitObjectHistoryReader(git_db)

    def load_all_nodes(self) -> List[QuipuNode]:
        conn = self.db_manager._get_conn()

        # 1. 一次性获取所有节点元数据
        nodes_cursor = conn.execute("SELECT * FROM nodes ORDER BY timestamp DESC;")
        nodes_data = nodes_cursor.fetchall()

        temp_nodes: Dict[str, QuipuNode] = {}
        for row in nodes_data:
            commit_hash = row["commit_hash"]
            node = QuipuNode(
                commit_hash=commit_hash,
                # input_tree 将在第二阶段链接
                input_tree="",
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{commit_hash}"),
                node_type=row["node_type"],
                summary=row["summary"],
                # 内容是懒加载的
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
                owner_id=row["owner_id"],
            )
            temp_nodes[commit_hash] = node

        # 2. 一次性获取所有边关系
        edges_cursor = conn.execute("SELECT child_hash, parent_hash FROM edges;")
        edges_data = edges_cursor.fetchall()

        # 3. 在内存中构建图
        for row in edges_data:
            child_hash, parent_hash = row["child_hash"], row["parent_hash"]

            # 关键修复：增加一个健全性检查，防止循环引用
            if child_hash == parent_hash:
                logger.warning(f"检测到并忽略了一个自引用边: {child_hash[:7]}")
                continue

            if child_hash in temp_nodes and parent_hash in temp_nodes:
                child_node = temp_nodes[child_hash]
                parent_node = temp_nodes[parent_hash]

                # 确保一个节点只有一个父节点（对于非合并节点）
                if child_node.parent is None:
                    child_node.parent = parent_node
                    parent_node.children.append(child_node)
                    # 根据父节点设置 input_tree
                    child_node.input_tree = parent_node.output_tree
                else:
                    # 如果一个节点有多个父节点（合并提交），我们只处理第一个
                    # 真正的合并逻辑需要更复杂的处理，但对于防止循环，此逻辑是安全的
                    logger.debug(f"节点 {child_hash[:7]} 已有父节点，忽略额外的父节点 {parent_hash[:7]}")

        # 4. 填充根节点的 input_tree 并排序子节点
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        for node in temp_nodes.values():
            if node.parent is None:
                node.input_tree = genesis_hash
            node.children.sort(key=lambda n: n.timestamp)

        return list(temp_nodes.values())

    def get_node_count(self) -> int:
        conn = self.db_manager._get_conn()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM nodes")
            row = cursor.fetchone()
            return row[0] if row else 0
        except sqlite3.Error as e:
            logger.error(f"Failed to get node count: {e}")
            return 0

    def get_node_position(self, output_tree_hash: str) -> int:
        conn = self.db_manager._get_conn()
        try:
            # 1. 获取目标节点的时间戳
            cursor = conn.execute("SELECT timestamp FROM nodes WHERE output_tree = ?", (output_tree_hash,))
            row = cursor.fetchone()
            if not row:
                return -1
            target_ts = row[0]

            # 2. 计算有多少个节点比它新（时间戳更大）
            cursor = conn.execute("SELECT COUNT(*) FROM nodes WHERE timestamp > ?", (target_ts,))
            count = cursor.fetchone()[0]
            return count
        except sqlite3.Error as e:
            logger.error(f"Failed to get node position: {e}")
            return -1

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        conn = self.db_manager._get_conn()
        try:
            # 1. Fetch nodes
            cursor = conn.execute("SELECT * FROM nodes ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset))
            rows = cursor.fetchall()

            if not rows:
                return []

            nodes_map = {}
            node_hashes = []

            for row in rows:
                commit_hash = row["commit_hash"]
                node_hashes.append(commit_hash)
                nodes_map[commit_hash] = QuipuNode(
                    commit_hash=commit_hash,
                    input_tree="",  # Placeholder
                    output_tree=row["output_tree"],
                    timestamp=datetime.fromtimestamp(row["timestamp"]),
                    filename=Path(f".quipu/git_objects/{commit_hash}"),
                    node_type=row["node_type"],
                    summary=row["summary"],
                    content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
                    owner_id=row["owner_id"],
                )

            # 2. Fetch edges to identify parents
            placeholders = ",".join("?" * len(node_hashes))
            edges_cursor = conn.execute(
                f"SELECT child_hash, parent_hash FROM edges WHERE child_hash IN ({placeholders})", tuple(node_hashes)
            )
            edges = edges_cursor.fetchall()

            child_to_parent = {row["child_hash"]: row["parent_hash"] for row in edges}
            parent_hashes = [row["parent_hash"] for row in edges]

            # 3. Fetch parent output_tree for input_tree linking
            parent_info = {}
            if parent_hashes:
                p_placeholders = ",".join("?" * len(parent_hashes))
                p_cursor = conn.execute(
                    f"SELECT commit_hash, output_tree FROM nodes WHERE commit_hash IN ({p_placeholders})",
                    tuple(parent_hashes),
                )
                parent_info = {row["commit_hash"]: row["output_tree"] for row in p_cursor.fetchall()}

            genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

            results = []
            for commit_hash in node_hashes:
                node = nodes_map[commit_hash]
                parent_hash = child_to_parent.get(commit_hash)

                if parent_hash:
                    # Set input_tree from parent's output_tree
                    node.input_tree = parent_info.get(parent_hash, genesis_hash)

                    # Link objects if parent is in the same page
                    if parent_hash in nodes_map:
                        parent_node = nodes_map[parent_hash]
                        node.parent = parent_node
                        parent_node.children.append(node)
                else:
                    node.input_tree = genesis_hash

                results.append(node)

            # Sort children for consistency (though partial)
            for node in results:
                node.children.sort(key=lambda n: n.timestamp)

            return results

        except sqlite3.Error as e:
            logger.error(f"Failed to load paginated nodes: {e}")
            return []

    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        conn = self.db_manager._get_conn()
        try:
            # 1. 查找起点的 commit_hash
            cursor = conn.execute("SELECT commit_hash FROM nodes WHERE output_tree = ?", (start_output_tree_hash,))
            row = cursor.fetchone()
            if not row:
                return set()
            start_commit_hash = row[0]

            # 2. 使用递归 CTE 查找所有后代 commit_hash
            sql = """
            WITH RECURSIVE descendants(h) AS (
                SELECT child_hash FROM edges WHERE parent_hash = ?
                UNION ALL
                SELECT e.child_hash FROM edges e, descendants d WHERE e.parent_hash = d.h AND e.child_hash IS NOT NULL
            )
            SELECT h FROM descendants WHERE h IS NOT NULL;
            """
            cursor = conn.execute(sql, (start_commit_hash,))
            descendant_commit_hashes = {row[0] for row in cursor.fetchall()}

            if not descendant_commit_hashes:
                return set()

            # 3. 将 commit_hash 集合转换为 output_tree 集合
            placeholders = ",".join("?" * len(descendant_commit_hashes))
            sql_out = f"SELECT output_tree FROM nodes WHERE commit_hash IN ({placeholders})"
            cursor = conn.execute(sql_out, tuple(descendant_commit_hashes))
            return {row[0] for row in cursor.fetchall()}

        except sqlite3.Error as e:
            logger.error(f"Failed to get descendants for {start_output_tree_hash[:7]}: {e}")
            return set()

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        conn = self.db_manager._get_conn()
        try:
            # 1. 查找起点的 commit_hash
            cursor = conn.execute("SELECT commit_hash FROM nodes WHERE output_tree = ?", (start_output_tree_hash,))
            row = cursor.fetchone()
            if not row:
                return set()
            start_commit_hash = row[0]

            # 2. 使用递归 CTE 查找所有祖先 commit_hash
            sql = """
            WITH RECURSIVE ancestors(h) AS (
                SELECT parent_hash FROM edges WHERE child_hash = ?
                UNION ALL
                SELECT e.parent_hash FROM edges e, ancestors a WHERE e.child_hash = a.h AND e.parent_hash IS NOT NULL
            )
            SELECT h FROM ancestors WHERE h IS NOT NULL;
            """
            cursor = conn.execute(sql, (start_commit_hash,))
            ancestor_commit_hashes = {row[0] for row in cursor.fetchall()}

            if not ancestor_commit_hashes:
                return set()

            # 3. 将 commit_hash 集合转换为 output_tree 集合
            placeholders = ",".join("?" * len(ancestor_commit_hashes))
            sql_out = f"SELECT output_tree FROM nodes WHERE commit_hash IN ({placeholders})"
            cursor = conn.execute(sql_out, tuple(ancestor_commit_hashes))
            return {row[0] for row in cursor.fetchall()}

        except sqlite3.Error as e:
            logger.error(f"Failed to get ancestors for {start_output_tree_hash[:7]}: {e}")
            return set()

    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        conn = self.db_manager._get_conn()
        try:
            cursor = conn.execute("SELECT intent_md FROM private_data WHERE node_hash = ?", (node_commit_hash,))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get private data for {node_commit_hash[:7]}: {e}")
            return None

    def get_node_blobs(self, commit_hash: str) -> Dict[str, bytes]:
        return self._git_reader.get_node_blobs(commit_hash)

    def get_node_content(self, node: QuipuNode) -> str:
        if node.content:
            return node.content

        commit_hash = node.commit_hash

        # 尝试从 Git 加载内容
        content = self._git_reader.get_node_content(node)

        # 如果成功加载，回填到缓存
        if content:
            try:
                self.db_manager.execute_write(
                    "UPDATE nodes SET plan_md_cache = ? WHERE commit_hash = ?", (content, commit_hash)
                )
                logger.debug(f"缓存已回填: {commit_hash[:7]}")
            except Exception as e:
                logger.warning(f"回填缓存失败: {commit_hash[:7]}: {e}")

        return content

    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        query = "SELECT * FROM nodes"
        conditions = []
        params = []

        if node_type:
            conditions.append("node_type = ?")
            params.append(node_type)

        # 注意: 标准 SQLite 不支持 REGEXP。
        # 此处使用 LIKE 实现简单的子字符串匹配作为替代。
        # 完整的正则支持需要加载扩展或在 Python 端进行二次过滤。
        if summary_regex:
            conditions.append("summary LIKE ?")
            params.append(f"%{summary_regex}%")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        conn = self.db_manager._get_conn()
        cursor = conn.execute(query, tuple(params))
        rows = cursor.fetchall()

        # 将查询结果行映射回 QuipuNode 对象 (不含父子关系)
        results = []
        for row in rows:
            node = QuipuNode(
                commit_hash=row["commit_hash"],
                input_tree="",  # 查找结果是扁平列表，不包含父子关系
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{row['commit_hash']}"),
                node_type=row["node_type"],
                summary=row["summary"],
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
                owner_id=row["owner_id"],
            )
            results.append(node)

        return results


class SQLiteHistoryWriter(HistoryWriter):
    def __init__(self, git_writer: GitObjectHistoryWriter, db_manager: DatabaseManager):
        self.git_writer = git_writer
        self.db_manager = db_manager

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        # 步骤 1: 调用底层 Git 写入器创建 Git Commit
        # 它会返回一个包含所有必要信息的 QuipuNode 实例
        git_node = self.git_writer.create_node(node_type, input_tree, output_tree, content, **kwargs)
        commit_hash = git_node.filename.name

        # 步骤 2: 将元数据写入 SQLite
        try:
            # 2.1 提取元数据 (从 Git 写入器内部逻辑中获取)
            # 这部分有些重复，未来可以优化 writer 的返回值
            start_time = kwargs.get("start_time", git_node.timestamp.timestamp())
            summary = self.git_writer._generate_summary(node_type, content, input_tree, output_tree, **kwargs)
            metadata = {
                "meta_version": "1.0",
                "summary": summary,
                "type": node_type,
                "generator": self.git_writer._get_generator_info(),
                "env": self.git_writer._get_env_info(),
                "exec": {"start": start_time, "duration_ms": 0},  # 持续时间暂时无法精确计算
            }
            meta_json_str = json.dumps(metadata)

            # 2.2 写入 'nodes' 表
            owner_id = kwargs.get("owner_id", "unknown-local-user")
            self.db_manager.execute_write(
                """
                INSERT OR REPLACE INTO nodes
                (commit_hash, owner_id, output_tree, node_type, timestamp, summary,
                 generator_id, meta_json, plan_md_cache)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_hash,
                    owner_id,
                    output_tree,
                    node_type,
                    start_time,
                    summary,
                    metadata["generator"]["id"],
                    meta_json_str,
                    content,  # 热缓存: 新创建的节点内容直接写入缓存
                ),
            )

            # 2.3 写入 'edges' 表
            # 关键修改：直接使用 GitWriter 传递回来的确切父节点信息，不再进行 Tree 反查
            if git_node.parent:
                parent_commit_hash = git_node.parent.commit_hash
                self.db_manager.execute_write(
                    "INSERT OR IGNORE INTO edges (child_hash, parent_hash) VALUES (?, ?)",
                    (commit_hash, parent_commit_hash),
                )

            # 2.4 (未来) 写入 'private_data' 表
            # intent = kwargs.get("intent_md")
            # if intent: ...

            logger.debug(f"✅ 节点元数据 {commit_hash[:7]} 已写入 SQLite。")

        except Exception as e:
            # 关键：如果数据库写入失败，我们不能回滚 Git 提交，
            # 但必须记录一个严重警告，提示需要进行数据补水。
            logger.error(f"⚠️  严重: Git 节点 {commit_hash[:7]} 已创建，但写入 SQLite 失败: {e}")
            logger.warning("   -> 下次启动或 `sync` 时将通过补水机制修复。")

        # 无论数据库写入是否成功，都返回从 Git 创建的节点
        return git_node
