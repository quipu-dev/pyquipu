# [Feature] 实现 SQLiteHistoryReader 的分页与高级查询接口

## 用户需求
完成 Quipu UI 性能优化的后端部分：
1.  实现 `SQLiteHistoryReader` 中的分页加载逻辑 (`load_nodes_paginated`)。
2.  实现高效的 SQL 级祖先节点查询 (`get_ancestor_hashes`)，用于可达性分析。
3.  实现私有数据读取 (`get_private_data`)。

## 评论
这是“秒开”功能的基石。通过利用 SQLite 的 `LIMIT/OFFSET` 和 CTE (Common Table Expressions) 递归查询，我们将彻底解决加载全量历史导致的性能问题。特别注意 `get_ancestor_hashes` 的参数实际上是 Tree Hash，需要先转换。

## 目标
更新 `packages/quipu-engine/src/quipu/core/sqlite_storage.py`，完整实现 `HistoryReader` 的新接口。

## 基本原理
-   **分页**: 使用 SQL `LIMIT` 避免全表扫描。
-   **Input Tree 推断**: 分页加载时缺少父节点对象，通过 `JOIN` 查询直接获取父节点的 `output_tree` 来填充 `input_tree` 字段，保证 TUI 连线正确。
-   **递归查询**: 使用 SQLite `WITH RECURSIVE` 替代 Python 层的递归，极大幅度降低内存开销。

## 标签
#intent/build #flow/ready #priority/high
#comp/engine #concept/state #scope/core
#ai/instruct
#task/domain/storage #task/object/sqlite-reader #task/action/implement-pagination
#task/state/continue

---

## Script

### Acts 1: 实现 SQLiteHistoryReader 的新方法

~~~~~act
write_file packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
from typing import Any, List, Dict, Optional, Set
from datetime import datetime
from pathlib import Path

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter
from quipu.core.git_object_storage import GitObjectHistoryWriter, GitObjectHistoryReader
from .sqlite_db import DatabaseManager
from .git_db import GitDB

logger = logging.getLogger(__name__)


class SQLiteHistoryReader(HistoryReader):
    """
    一个从 SQLite 缓存读取历史的实现，并按需从 Git 回填。
    """

    def __init__(self, db_manager: DatabaseManager, git_db: GitDB):
        self.db_manager = db_manager
        # git_reader 用于按需加载内容和解析二进制 tree
        self._git_reader = GitObjectHistoryReader(git_db)

    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从 SQLite 数据库高效加载所有节点元数据和关系。
        """
        conn = self.db_manager._get_conn()
        
        # 1. 一次性获取所有节点元数据
        nodes_cursor = conn.execute("SELECT * FROM nodes ORDER BY timestamp DESC;")
        nodes_data = nodes_cursor.fetchall()

        temp_nodes: Dict[str, QuipuNode] = {}
        for row in nodes_data:
            node = QuipuNode(
                # input_tree 将在第二阶段链接
                input_tree="",
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{row['commit_hash']}"),
                node_type=row["node_type"],
                summary=row["summary"],
                # 内容是懒加载的
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
            )
            temp_nodes[row["commit_hash"]] = node

        # 2. 一次性获取所有边关系
        edges_cursor = conn.execute("SELECT child_hash, parent_hash FROM edges;")
        edges_data = edges_cursor.fetchall()
        
        # 3. 在内存中构建图
        for row in edges_data:
            child_hash, parent_hash = row["child_hash"], row["parent_hash"]
            if child_hash in temp_nodes and parent_hash in temp_nodes:
                child_node = temp_nodes[child_hash]
                parent_node = temp_nodes[parent_hash]
                
                child_node.parent = parent_node
                parent_node.children.append(child_node)
                # 根据父节点设置 input_tree
                child_node.input_tree = parent_node.output_tree
        
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
        except Exception as e:
            logger.error(f"Failed to count nodes: {e}")
            return 0

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """
        分页加载节点。
        在此模式下，我们无法构建完整的父子对象链接 (node.parent)，
        但我们会通过 JOIN 查询来正确填充 node.input_tree，确保 UI 能画出连线。
        """
        conn = self.db_manager._get_conn()
        
        # 1. Fetch Page Nodes
        sql = "SELECT * FROM nodes ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        cursor = conn.execute(sql, (limit, offset))
        rows = cursor.fetchall()
        
        if not rows:
            return []

        nodes = []
        commit_hashes = []
        node_map = {}
        genesis_hash = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

        for row in rows:
            node = QuipuNode(
                input_tree=genesis_hash, # Default to genesis, will update via edges
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{row['commit_hash']}"),
                node_type=row["node_type"],
                summary=row["summary"],
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
            )
            nodes.append(node)
            commit_hashes.append(row["commit_hash"])
            node_map[row["commit_hash"]] = node

        # 2. Fetch Edges to determine input_tree
        # 我们查询这些节点的父节点，并 JOIN nodes 表获取父节点的 output_tree
        if commit_hashes:
            placeholders = ",".join("?" * len(commit_hashes))
            edge_sql = f"""
                SELECT e.child_hash, n.output_tree as parent_output_tree 
                FROM edges e 
                JOIN nodes n ON e.parent_hash = n.commit_hash 
                WHERE e.child_hash IN ({placeholders})
            """
            edge_cursor = conn.execute(edge_sql, commit_hashes)
            for edge_row in edge_cursor:
                child = node_map.get(edge_row["child_hash"])
                if child:
                    child.input_tree = edge_row["parent_output_tree"]
                    # 注意: 这里 node.parent 仍为 None，这是分页模式的预期行为
                    
        return nodes

    def get_ancestor_hashes(self, commit_hash: str) -> Set[str]:
        """
        使用 CTE 递归查询获取所有祖先节点的 output_tree 集合。
        注意: 入参 commit_hash 实际上是 Tree Hash (TUI current_hash)。
        """
        conn = self.db_manager._get_conn()
        
        # 1. 将 Tree Hash 转换为 Commit Hash
        # TUI 传递的是 output_tree (因为它只知道这个)
        target_tree = commit_hash
        cursor = conn.execute("SELECT commit_hash FROM nodes WHERE output_tree = ?", (target_tree,))
        row = cursor.fetchone()
        
        if not row:
            return set()
            
        start_commit_hash = row[0]
        
        # 2. 递归查询
        sql = """
        WITH RECURSIVE ancestors(hash) AS (
            SELECT parent_hash FROM edges WHERE child_hash = ?
            UNION
            SELECT e.parent_hash FROM edges e, ancestors a WHERE e.child_hash = a.hash
        )
        SELECT n.output_tree FROM ancestors a JOIN nodes n ON a.hash = n.commit_hash;
        """
        
        cursor = conn.execute(sql, (start_commit_hash,))
        return {row[0] for row in cursor.fetchall()}

    def get_private_data(self, commit_hash: str) -> Optional[str]:
        """
        注意: 入参 commit_hash 在 QuipuNode.filename.name 中实际上是 Commit Hash。
        这与 get_ancestor_hashes 不同 (那里是 Tree Hash)。
        UI 调用时使用的是 node.filename.name。
        """
        conn = self.db_manager._get_conn()
        try:
            cursor = conn.execute("SELECT intent_md FROM private_data WHERE node_hash = ?", (commit_hash,))
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception:
            return None

    def get_node_content(self, node: QuipuNode) -> str:
        """
        实现通读缓存策略来获取节点内容。
        """
        if node.content:
            return node.content
        
        commit_hash = node.filename.name
        
        # 尝试从 Git 加载内容
        content = self._git_reader.get_node_content(node)
        
        # 如果成功加载，回填到缓存
        if content:
            try:
                self.db_manager.execute_write(
                    "UPDATE nodes SET plan_md_cache = ? WHERE commit_hash = ?",
                    (content, commit_hash)
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
        """
        直接在 SQLite 数据库中执行高效的节点查找。
        """
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
                input_tree="",  # 查找结果是扁平列表，不包含父子关系
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{row['commit_hash']}"),
                node_type=row["node_type"],
                summary=row["summary"],
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
            )
            results.append(node)
            
        return results
~~~~~

### Acts 2: 更新 SQLite 测试用例

添加测试以验证分页、计数和祖先查询功能。

~~~~~act
append_file tests/test_sqlite_reader.py
~~~~~
~~~~~python

    def test_pagination(self, sqlite_reader_setup):
        """测试分页加载和 input_tree 的正确推断。"""
        reader, git_writer, hydrator, _, repo, git_db = sqlite_reader_setup

        # Create chain: A -> B -> C
        (repo / "f.txt").write_text("v1")
        h_a = git_db.get_tree_hash()
        git_writer.create_node("plan", "genesis", h_a, "A")
        
        (repo / "f.txt").write_text("v2")
        h_b = git_db.get_tree_hash()
        git_writer.create_node("plan", h_a, h_b, "B")

        (repo / "f.txt").write_text("v3")
        h_c = git_db.get_tree_hash()
        git_writer.create_node("plan", h_b, h_c, "C")

        hydrator.sync()

        assert reader.get_node_count() == 3

        # Page 1: Limit 2 (Should get C and B, newest first)
        page1 = reader.load_nodes_paginated(limit=2, offset=0)
        assert len(page1) == 2
        node_c = page1[0]
        node_b = page1[1]

        assert node_c.summary == "C"
        assert node_c.input_tree == h_b  # Should be inferred correctly
        
        assert node_b.summary == "B"
        assert node_b.input_tree == h_a

        # Page 2: Limit 2, Offset 2 (Should get A)
        page2 = reader.load_nodes_paginated(limit=2, offset=2)
        assert len(page2) == 1
        node_a = page2[0]
        assert node_a.summary == "A"
        # Since A's parent (genesis) is not in DB, it might be genesis string or None depending on impl
        # Our impl sets default genesis, then tries to update from edges.
        # Since no edge for A's parent, it remains genesis.
        assert node_a.input_tree == "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

    def test_ancestor_query(self, sqlite_reader_setup):
        """测试 CTE 递归祖先查询。"""
        reader, git_writer, hydrator, _, repo, git_db = sqlite_reader_setup

        # A -> B -> C
        (repo / "f.txt").write_text("v1")
        h_a = git_db.get_tree_hash()
        git_writer.create_node("plan", "genesis", h_a, "A")
        
        (repo / "f.txt").write_text("v2")
        h_b = git_db.get_tree_hash()
        git_writer.create_node("plan", h_a, h_b, "B")
        
        (repo / "f.txt").write_text("v3")
        h_c = git_db.get_tree_hash()
        git_writer.create_node("plan", h_b, h_c, "C")

        hydrator.sync()

        # Query ancestors of C (input is tree hash)
        ancestors = reader.get_ancestor_hashes(h_c)
        
        assert h_b in ancestors
        assert h_a in ancestors
        assert h_c not in ancestors  # Strict ancestors

        # Query ancestors of A
        ancestors_a = reader.get_ancestor_hashes(h_a)
        assert len(ancestors_a) == 0

    def test_private_data_read(self, sqlite_reader_setup):
        """测试私有数据读取。"""
        reader, git_writer, hydrator, db_manager, repo, git_db = sqlite_reader_setup

        (repo / "p.txt").touch()
        h_p = git_db.get_tree_hash()
        node = git_writer.create_node("plan", "genesis", h_p, "Private")
        commit_hash = node.filename.name
        
        hydrator.sync()
        
        # Manually insert private data (simulate writer logic which is not yet impl)
        db_manager.execute_write(
            "INSERT INTO private_data (node_hash, intent_md) VALUES (?, ?)",
            (commit_hash, "My Secret Intent")
        )
        
        # Test read
        intent = reader.get_private_data(commit_hash)
        assert intent == "My Secret Intent"
        
        # Test missing
        assert reader.get_private_data("non-existent") is None
~~~~~
