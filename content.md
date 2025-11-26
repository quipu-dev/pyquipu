# feat: 激活 SQLite 读取路径以提升性能

## 用户需求
当前系统即使配置了 SQLite，在读取历史记录（如 `quipu ui` 或 `quipu log`）时依然从 Git 对象中逐个解析，导致性能瓶颈无法解决。需要将读取路径切换到 SQLite，以实现 UI 和查询的“秒开”体验。

## 评论
这是 SQLite 升级计划中至关重要的一步，它将真正释放数据库带来的性能优势。此计划遵循“读写分离”和“通读缓存”的设计模式，确保了数据一致性与高性能。

## 目标
1.  在 `quipu-engine` 中实现 `SQLiteHistoryReader`，使其能够从数据库中高效加载完整的历史图谱。
2.  为 `SQLiteHistoryReader` 实现“通读缓存 (Read-Through Cache)”策略，用于按需、懒加载节点内容。
3.  在 `quipu-cli` 的工厂函数 `create_engine` 中集成新的 `SQLiteHistoryReader`，使其在配置为 `sqlite` 模式时被激活。

## 基本原理
本计划的核心是实现 `HistoryReader` 接口的 SQLite 版本。

1.  **图谱加载**: `load_all_nodes` 方法将通过一次或两次 SQL 查询，从 `nodes` 和 `edges` 表中获取所有元数据和关系，然后在内存中快速构建出 `QuipuNode` 对象的图结构。这避免了对成百上千个 Git 对象的慢速遍历和解析。
2.  **内容缓存**: `get_node_content` 方法实现了“通读缓存”。当请求节点内容时，它首先检查数据库中的 `plan_md_cache` 字段。如果内容已缓存（热数据），则直接返回；如果未缓存（冷数据），则从 Git 中读取，回填到数据库缓存中，然后返回。这确保了首次访问后，后续访问将是毫秒级的。

通过在 `factory.py` 中进行条件实例化，我们确保了旧的 `GitObjectHistoryReader` 仍然是默认选项，只有当用户明确配置 `storage.type: sqlite` 时，新的高性能读取器才会被启用。

## 标签
#intent/build #flow/ready #priority/high
#comp/engine #comp/cli
#concept/history #concept/state #concept/ui
#scope/core #scope/ux
#ai/instruct
#task/domain/storage
#task/object/sqlite-backend
#task/action/integration
#task/state/continue
#task/status/active

---

## Script

### Acts 1: 实现 `SQLiteHistoryReader`

我们将在 `quipu-engine` 的 `sqlite_storage.py` 文件中添加 `SQLiteHistoryReader` 类。这与 `SQLiteHistoryWriter` 放在一起，符合逻辑内聚性。

~~~~~act
write_file packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
import json
import logging
from typing import Any, List, Dict
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


class SQLiteHistoryWriter(HistoryWriter):
    """
    一个实现“双写”的历史写入器。
    1. 委托 GitObjectHistoryWriter 将节点写入 Git。
    2. 将元数据和关系写入 SQLite。
    """

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
        git_node = self.git_writer.create_node(
            node_type, input_tree, output_tree, content, **kwargs
        )
        commit_hash = git_node.filename.name

        # 步骤 2: 将元数据写入 SQLite
        try:
            # 2.1 提取元数据 (从 Git 写入器内部逻辑中获取)
            # 这部分有些重复，未来可以优化 writer 的返回值
            start_time = kwargs.get("start_time", git_node.timestamp.timestamp())
            summary = self.git_writer._generate_summary(
                node_type, content, input_tree, output_tree, **kwargs
            )
            metadata = {
                "meta_version": "1.0",
                "summary": summary,
                "type": node_type,
                "generator": self.git_writer._get_generator_info(),
                "env": self.git_writer._get_env_info(),
                "exec": {"start": start_time, "duration_ms": 0}, # 持续时间暂时无法精确计算
            }
            meta_json_str = json.dumps(metadata)

            # 2.2 写入 'nodes' 表
            self.db_manager.execute_write(
                """
                INSERT OR REPLACE INTO nodes 
                (commit_hash, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_hash,
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
            parent_commit = self.git_writer.git_db.get_commit_by_output_tree(input_tree)
            if parent_commit:
                self.db_manager.execute_write(
                    "INSERT OR IGNORE INTO edges (child_hash, parent_hash) VALUES (?, ?)",
                    (commit_hash, parent_commit),
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
~~~~~

### Acts 2: 在 CLI 工厂中集成新的读取器

现在，我们将修改 `quipu-cli` 中的 `create_engine` 函数，让它在检测到 SQLite 配置时，使用我们刚刚创建的 `SQLiteHistoryReader`。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/factory.py
~~~~~
~~~~~python
# 迟延导入以避免循环依赖
try:
    from quipu.core.sqlite_db import DatabaseManager
    from quipu.core.sqlite_storage import SQLiteHistoryWriter
except ImportError:
    DatabaseManager = None
    SQLiteHistoryWriter = None
~~~~~
~~~~~python
# 迟延导入以避免循环依赖
try:
    from quipu.core.sqlite_db import DatabaseManager
    from quipu.core.sqlite_storage import SQLiteHistoryWriter, SQLiteHistoryReader
except ImportError:
    DatabaseManager = None
    SQLiteHistoryWriter = None
    SQLiteHistoryReader = None
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/factory.py
~~~~~
~~~~~python
    # 默认和备用后端
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    if storage_type == "sqlite":
        if not DatabaseManager or not SQLiteHistoryWriter:
            raise ImportError("SQLite dependencies could not be loaded. Please check your installation.")

        logger.debug("Using SQLite storage format for writes.")
        db_manager = DatabaseManager(project_root)
        db_manager.init_schema()

        writer = SQLiteHistoryWriter(git_writer=writer, db_manager=db_manager)

    elif storage_type != "git_object":
        raise NotImplementedError(f"Storage type '{storage_type}' is not supported.")
~~~~~
~~~~~python
    # 默认和备用后端
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    if storage_type == "sqlite":
        if not DatabaseManager or not SQLiteHistoryWriter or not SQLiteHistoryReader:
            raise ImportError("SQLite dependencies could not be loaded. Please check your installation.")

        logger.debug("Using SQLite storage format for reads and writes.")
        db_manager = DatabaseManager(project_root)
        db_manager.init_schema()

        # 切换到 SQLite 后端
        reader = SQLiteHistoryReader(db_manager=db_manager, git_db=git_db)
        writer = SQLiteHistoryWriter(git_writer=writer, db_manager=db_manager)

    elif storage_type != "git_object":
        raise NotImplementedError(f"Storage type '{storage_type}' is not supported.")
~~~~~
