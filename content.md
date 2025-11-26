# chore: 实现 SQLite 数据补水机制

## 用户需求
当前系统已经实现了向 SQLite 的“双写”，但缺少一个关键机制：无法从一个已有的 Git 历史记录中填充（或“补水”）SQLite 数据库。这导致旧项目无法迁移到新存储后端，也使得从远程拉取的新历史无法被 UI 查询到，从而阻碍了后续读取路径的优化。

## 评论
这是一个至关重要的步骤，它是激活 SQLite 高性能读取路径的基石。实现一个健壮、高效的补水机制，可以确保数据的一致性，并为用户提供管理本地缓存的命令行工具。

## 目标
1.  在 `quipu-engine` 中创建一个 `Hydrator` 类，负责将 Git 历史同步到 SQLite。
2.  实现高效的差异计算和批量数据读写，以确保补水过程性能优良。
3.  在 `Engine` 启动时自动触发增量补水，保证数据新鲜度。
4.  向 `quipu-cli` 添加 `quipu cache` 命令，为用户提供手动管理数据库（如重建）的能力。

## 基本原理
补水机制遵循“Git 为唯一事实来源”的原则。它通过比较 Git 中的全量 Quipu Commits 和 SQLite 中的记录，找出差异，然后通过 Git 的批量读取接口 (`cat-file --batch`) 高效获取缺失节点的数据，最后批量写入 SQLite。这个过程被设计为幂等的，可以安全地反复运行。补水写入的数据内容 (`plan.md`) 将被标记为“冷数据” (`NULL`)，遵循懒加载策略。

## 标签
#intent/tooling #flow/ready #priority/high
#comp/engine #comp/cli #concept/state #concept/history #scope/core
#ai/instruct
#task/domain/storage #task/object/sqlite-backend #task/action/integration
#task/state/continue #task/status/active

---

## Script

### Acts 1: 引擎层 - 创建 Hydrator 及其依赖

我们首先在 `quipu-engine` 中构建补水器的核心逻辑。这包括 `Hydrator` 类本身，以及 `DatabaseManager` 中用于支持高效查询和批量插入的新方法。

~~~~~act
write_file packages/quipu-engine/src/quipu/core/hydrator.py
~~~~~
~~~~~python
import json
import logging
import re
from typing import List, Dict, Set, Tuple

from .git_db import GitDB
from .sqlite_db import DatabaseManager
from .git_object_storage import GitObjectHistoryReader  # Reuse parsing logic

logger = logging.getLogger(__name__)


class Hydrator:
    """
    负责将 Git 对象历史记录同步（补水）到 SQLite 数据库。
    """

    def __init__(self, git_db: GitDB, db_manager: DatabaseManager):
        self.git_db = git_db
        self.db_manager = db_manager
        # 复用 Reader 中的二进制解析逻辑，避免代码重复
        self._parser = GitObjectHistoryReader(git_db)

    def _get_missing_commit_hashes(self) -> Set[str]:
        """
        计算存在于 Git 中但缺失于 SQLite 的 commit 哈希集合。
        """
        logger.debug("正在计算需要补水的 Commit...")
        all_git_heads = self.git_db.get_all_ref_heads("refs/quipu/")
        if not all_git_heads:
            return set()

        git_log_entries = self.git_db.log_ref(all_git_heads)
        git_hashes = {entry["hash"] for entry in git_log_entries}
        
        db_hashes = self.db_manager.get_all_node_hashes()
        
        missing_hashes = git_hashes - db_hashes
        logger.info(f"发现 {len(missing_hashes)} 个需要补水的节点。")
        return missing_hashes

    def sync(self):
        """
        执行增量补水操作。
        """
        missing_hashes = self._get_missing_commit_hashes()
        if not missing_hashes:
            logger.debug("✅ 数据库与 Git 历史一致，无需补水。")
            return

        all_git_logs = self.git_db.log_ref(self.git_db.get_all_ref_heads("refs/quipu/"))
        log_map = {entry["hash"]: entry for entry in all_git_logs}

        # --- 批量准备数据 ---
        nodes_to_insert: List[Tuple] = []
        edges_to_insert: List[Tuple] = []

        # 1. 批量获取 Trees
        tree_hashes = [log_map[h]["tree"] for h in missing_hashes]
        trees_content = self.git_db.batch_cat_file(tree_hashes)

        # 2. 解析 Trees, 批量获取 Metas
        tree_to_meta_blob: Dict[str, str] = {}
        meta_blob_hashes: List[str] = []
        for tree_hash, content_bytes in trees_content.items():
            entries = self._parser._parse_tree_binary(content_bytes)
            if "metadata.json" in entries:
                blob_hash = entries["metadata.json"]
                tree_to_meta_blob[tree_hash] = blob_hash
                meta_blob_hashes.append(blob_hash)

        metas_content = self.git_db.batch_cat_file(meta_blob_hashes)

        # 3. 构建插入数据
        for commit_hash in missing_hashes:
            log_entry = log_map[commit_hash]
            tree_hash = log_entry["tree"]
            
            meta_blob_hash = tree_to_meta_blob.get(tree_hash)
            if not meta_blob_hash:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 metadata.json")
                continue

            meta_bytes = metas_content.get(meta_blob_hash)
            if not meta_bytes:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 metadata blob")
                continue
            
            output_tree = self._parser._parse_output_tree_from_body(log_entry["body"])
            if not output_tree:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 Output-Tree trailer")
                continue

            try:
                meta_data = json.loads(meta_bytes)
                nodes_to_insert.append((
                    commit_hash,
                    output_tree,
                    meta_data.get("type", "unknown"),
                    float(meta_data.get("exec", {}).get("start") or log_entry["timestamp"]),
                    meta_data.get("summary", "No summary"),
                    meta_data.get("generator", {}).get("id"),
                    meta_bytes.decode('utf-8'),
                    None  # plan_md_cache is NULL for cold data
                ))

                # 处理边关系
                parent_hashes = log_entry["parent"].split()
                for p_hash in parent_hashes:
                    edges_to_insert.append((commit_hash, p_hash))
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"解析 {commit_hash[:7]} 的元数据失败: {e}")

        # --- 批量写入数据库 ---
        if nodes_to_insert:
            self.db_manager.batch_insert_nodes(nodes_to_insert)
            logger.info(f"💧 {len(nodes_to_insert)} 个节点元数据已补水。")
        if edges_to_insert:
            self.db_manager.batch_insert_edges(edges_to_insert)
            logger.info(f"💧 {len(edges_to_insert)} 条边关系已补水。")

~~~~~
~~~~~act
replace packages/quipu-engine/src/quipu/core/sqlite_db.py
~~~~~
~~~~~python
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Any

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    管理 SQLite 数据库连接和 Schema。
    """

    def __init__(self, work_dir: Path):
        self.db_path = work_dir / ".quipu" / "history.sqlite"
        self.db_path.parent.mkdir(exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接，如果不存在则创建。"""
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                # 开启外键约束
                self._conn.execute("PRAGMA foreign_keys = ON;")
                logger.debug(f"🗃️  成功连接到数据库: {self.db_path}")
            except sqlite3.Error as e:
                logger.error(f"❌ 数据库连接失败: {e}")
                raise
        return self._conn

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("🗃️  数据库连接已关闭。")

    def __del__(self):
        """析构函数，作为关闭连接的最后一道防线。"""
        self.close()

    def init_schema(self):
        """
        初始化数据库 Schema，如果表不存在则创建。
        符合 QLDS v1.0 规范。
        """
        conn = self._get_conn()
        try:
            with conn:
                # nodes 表
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nodes (
                        commit_hash TEXT(40) PRIMARY KEY,
                        output_tree TEXT(40) NOT NULL,
                        node_type TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        summary TEXT NOT NULL,
                        generator_id TEXT,
                        meta_json TEXT NOT NULL,
                        plan_md_cache TEXT
                    );
                    """
                )
                # 索引
                conn.execute("CREATE INDEX IF NOT EXISTS IDX_nodes_timestamp ON nodes(timestamp);")
                conn.execute("CREATE INDEX IF NOT EXISTS IDX_nodes_output_tree ON nodes(output_tree);")

                # edges 表
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS edges (
                        child_hash TEXT(40) NOT NULL,
                        parent_hash TEXT(40) NOT NULL,
                        PRIMARY KEY (child_hash, parent_hash),
                        FOREIGN KEY (child_hash) REFERENCES nodes(commit_hash) ON DELETE CASCADE,
                        FOREIGN KEY (parent_hash) REFERENCES nodes(commit_hash) ON DELETE CASCADE
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS IDX_edges_parent ON edges(parent_hash);")

                # private_data 表
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS private_data (
                        node_hash TEXT(40) PRIMARY KEY,
                        intent_md TEXT,
                        ai_context TEXT,
                        created_at REAL DEFAULT (strftime('%s', 'now')),
                        FOREIGN KEY (node_hash) REFERENCES nodes(commit_hash) ON DELETE CASCADE
                    );
                    """
                )
            logger.debug("✅ 数据库 Schema 已初始化/验证。")
        except sqlite3.Error as e:
            logger.error(f"❌ 初始化 Schema 失败: {e}")
            raise

    def execute_write(self, sql: str, params: tuple = ()):
        """执行写操作的通用方法。"""
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error(f"❌ 数据库写入失败: {e} | SQL: {sql}")
            raise
~~~~~
~~~~~python
import sqlite3
import logging
from pathlib import Path
from typing import Optional, Any, Set, List, Tuple

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    管理 SQLite 数据库连接和 Schema。
    """

    def __init__(self, work_dir: Path):
        self.db_path = work_dir / ".quipu" / "history.sqlite"
        self.db_path.parent.mkdir(exist_ok=True)
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        """获取数据库连接，如果不存在则创建。"""
        if self._conn is None:
            try:
                self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
                self._conn.row_factory = sqlite3.Row
                # 开启外键约束
                self._conn.execute("PRAGMA foreign_keys = ON;")
                logger.debug(f"🗃️  成功连接到数据库: {self.db_path}")
            except sqlite3.Error as e:
                logger.error(f"❌ 数据库连接失败: {e}")
                raise
        return self._conn

    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("🗃️  数据库连接已关闭。")

    def __del__(self):
        """析构函数，作为关闭连接的最后一道防线。"""
        self.close()

    def init_schema(self):
        """
        初始化数据库 Schema，如果表不存在则创建。
        符合 QLDS v1.0 规范。
        """
        conn = self._get_conn()
        try:
            with conn:
                # nodes 表
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nodes (
                        commit_hash TEXT(40) PRIMARY KEY,
                        output_tree TEXT(40) NOT NULL,
                        node_type TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        summary TEXT NOT NULL,
                        generator_id TEXT,
                        meta_json TEXT NOT NULL,
                        plan_md_cache TEXT
                    );
                    """
                )
                # 索引
                conn.execute("CREATE INDEX IF NOT EXISTS IDX_nodes_timestamp ON nodes(timestamp);")
                conn.execute("CREATE INDEX IF NOT EXISTS IDX_nodes_output_tree ON nodes(output_tree);")

                # edges 表
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS edges (
                        child_hash TEXT(40) NOT NULL,
                        parent_hash TEXT(40) NOT NULL,
                        PRIMARY KEY (child_hash, parent_hash),
                        FOREIGN KEY (child_hash) REFERENCES nodes(commit_hash) ON DELETE CASCADE,
                        FOREIGN KEY (parent_hash) REFERENCES nodes(commit_hash) ON DELETE CASCADE
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS IDX_edges_parent ON edges(parent_hash);")

                # private_data 表
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS private_data (
                        node_hash TEXT(40) PRIMARY KEY,
                        intent_md TEXT,
                        ai_context TEXT,
                        created_at REAL DEFAULT (strftime('%s', 'now')),
                        FOREIGN KEY (node_hash) REFERENCES nodes(commit_hash) ON DELETE CASCADE
                    );
                    """
                )
            logger.debug("✅ 数据库 Schema 已初始化/验证。")
        except sqlite3.Error as e:
            logger.error(f"❌ 初始化 Schema 失败: {e}")
            raise

    def execute_write(self, sql: str, params: tuple = ()):
        """执行写操作的通用方法。"""
        conn = self._get_conn()
        try:
            with conn:
                conn.execute(sql, params)
        except sqlite3.Error as e:
            logger.error(f"❌ 数据库写入失败: {e} | SQL: {sql}")
            raise

    def get_all_node_hashes(self) -> Set[str]:
        """获取数据库中所有节点的 commit_hash。"""
        conn = self._get_conn()
        try:
            cursor = conn.execute("SELECT commit_hash FROM nodes;")
            return {row[0] for row in cursor.fetchall()}
        except sqlite3.Error as e:
            logger.error(f"❌ 查询节点哈希失败: {e}")
            return set()

    def batch_insert_nodes(self, nodes: List[Tuple]):
        """批量插入节点。"""
        conn = self._get_conn()
        sql = """
            INSERT OR IGNORE INTO nodes 
            (commit_hash, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with conn:
                conn.executemany(sql, nodes)
        except sqlite3.Error as e:
            logger.error(f"❌ 批量插入节点失败: {e}")
            raise

    def batch_insert_edges(self, edges: List[Tuple]):
        """批量插入边。"""
        conn = self._get_conn()
        sql = "INSERT OR IGNORE INTO edges (child_hash, parent_hash) VALUES (?, ?)"
        try:
            with conn:
                conn.executemany(sql, edges)
        except sqlite3.Error as e:
            logger.error(f"❌ 批量插入边失败: {e}")
            raise
~~~~~

### Acts 2: 引擎集成与 CLI 命令

现在，我们将 `Hydrator` 集成到 `Engine` 的启动流程中，并添加 `quipu cache` 子命令。

~~~~~act
replace packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~
~~~~~python
import logging
import re
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime

from .git_db import GitDB
from .config import ConfigManager
from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter

# 导入类型以进行类型提示
try:
    from .sqlite_db import DatabaseManager
except ImportError:
    DatabaseManager = None

logger = logging.getLogger(__name__)


class Engine:
    """
    Axon 状态引擎。
    负责协调 Git 物理状态和 Axon 逻辑图谱。
    """
~~~~~
~~~~~python
import logging
import re
from pathlib import Path
from typing import Dict, Optional, List, Tuple, Any
from datetime import datetime

from .git_db import GitDB
from .config import ConfigManager
from .hydrator import Hydrator
from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter

# 导入类型以进行类型提示
try:
    from .sqlite_db import DatabaseManager
except ImportError:
    DatabaseManager = None

logger = logging.getLogger(__name__)


class Engine:
    """
    Axon 状态引擎。
    负责协调 Git 物理状态和 Axon 逻辑图谱。
    """
~~~~~
~~~~~act
replace packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~
~~~~~python
    def align(self) -> str:
        all_nodes = self.reader.load_all_nodes()
        final_graph: Dict[str, QuipuNode] = {}
        for node in all_nodes:
            if node.output_tree not in final_graph or node.timestamp > final_graph[node.output_tree].timestamp:
                final_graph[node.output_tree] = node
        self.history_graph = final_graph
        if all_nodes:
            logger.info(f"从存储中加载了 {len(all_nodes)} 个历史事件，形成 {len(final_graph)} 个唯一状态节点。")

        current_hash = self.git_db.get_tree_hash()
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
~~~~~
~~~~~python
    def align(self) -> str:
        # 如果使用 SQLite，先进行数据补水
        if self.db_manager:
            try:
                hydrator = Hydrator(self.git_db, self.db_manager)
                hydrator.sync()
            except Exception as e:
                logger.error(f"❌ 自动数据补水失败: {e}", exc_info=True)

        all_nodes = self.reader.load_all_nodes()
        final_graph: Dict[str, QuipuNode] = {}
        for node in all_nodes:
            if node.output_tree not in final_graph or node.timestamp > final_graph[node.output_tree].timestamp:
                final_graph[node.output_tree] = node
        self.history_graph = final_graph
        if all_nodes:
            logger.info(f"从存储中加载了 {len(all_nodes)} 个历史事件，形成 {len(final_graph)} 个唯一状态节点。")

        current_hash = self.git_db.get_tree_hash()
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
~~~~~
~~~~~act
replace packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
# 注意：不要在模块级别直接调用 setup_logging()，
# 否则会导致 CliRunner 测试中的 I/O 流过早绑定/关闭问题。
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, name="quipu")


def _prompt_for_confirmation(message: str, default: bool = False) -> bool:
~~~~~
~~~~~python
# 注意：不要在模块级别直接调用 setup_logging()，
# 否则会导致 CliRunner 测试中的 I/O 流过早绑定/关闭问题。
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, name="quipu")
cache_app = typer.Typer(name="cache", help="管理本地 SQLite 缓存。")
app.add_typer(cache_app)


def _prompt_for_confirmation(message: str, default: bool = False) -> bool:
~~~~~
~~~~~act
replace packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
    ctx.exit(result.exit_code)


if __name__ == "__main__":
    app()
~~~~~
~~~~~python
    ctx.exit(result.exit_code)


@cache_app.command("sync")
def cache_sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
):
    """
    将 Git 历史增量同步到 SQLite 缓存。
    此操作在大多数命令执行时会自动触发。
    """
    setup_logging()
    typer.secho("💧 正在执行增量数据补水...", fg=typer.colors.BLUE, err=True)
    try:
        engine = create_engine(work_dir)
        # create_engine 内部的 align() 已经触发了 sync()
        typer.secho("✅ 数据同步完成。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        typer.secho(f"❌ 数据同步失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)


@cache_app.command("rebuild")
def cache_rebuild(
    ctx: typer.Context,
    force: Annotated[bool, typer.Option("--force", "-f", help="强制执行，跳过确认提示。")] = False,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
):
    """
    强制全量重建 SQLite 缓存。
    这将删除现有的数据库文件，并从 Git 历史中完全重新生成。
    """
    setup_logging()
    
    db_path = work_dir.resolve() / ".quipu" / "history.sqlite"
    if not db_path.exists():
        typer.secho("🤷 数据库文件不存在，将直接创建。无需重建。", fg=typer.colors.YELLOW, err=True)
        cache_sync(ctx, work_dir)
        return

    if not force:
        prompt = f"🚨 即将删除并重建数据库 {db_path}。\n所有私有数据（如开发者意图）将丢失！此操作不可逆。是否继续？"
        if not _prompt_for_confirmation(prompt, default=False):
            typer.secho("\n🚫 操作已取消。", fg=typer.colors.YELLOW, err=True)
            raise typer.Abort()
    
    try:
        db_path.unlink()
        typer.secho("🗑️  旧数据库已删除。", err=True)
    except Exception as e:
        typer.secho(f"❌ 删除旧数据库失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)

    # 调用 sync 会自动完成重建
    cache_sync(ctx, work_dir)


if __name__ == "__main__":
    app()
~~~~~

### Acts 3: 测试

最后，我们需要为新的补水机制添加测试，确保其在各种场景下都能正确工作。

~~~~~act
write_file tests/test_hydration.py
~~~~~
~~~~~python
import pytest
import subprocess
from pathlib import Path

from quipu.core.git_db import GitDB
from quipu.core.sqlite_db import DatabaseManager
from quipu.core.hydrator import Hydrator
from quipu.core.git_object_storage import GitObjectHistoryWriter

@pytest.fixture
def hydrator_setup(tmp_path: Path):
    """
    创建一个包含 Git 仓库、DB 管理器和 Hydrator 实例的测试环境。
    """
    repo_path = tmp_path / "hydro_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    db_manager = DatabaseManager(repo_path)
    db_manager.init_schema()
    
    writer = GitObjectHistoryWriter(git_db)
    hydrator = Hydrator(git_db, db_manager)

    return hydrator, writer, git_db, db_manager, repo_path

class TestHydration:
    def test_full_hydration_from_scratch(self, hydrator_setup):
        """测试从一个空的数据库开始，完整补水一个已有的 Git 历史。"""
        hydrator, writer, git_db, db_manager, repo = hydrator_setup

        # 1. 在 Git 中创建两个节点
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", "genesis", hash_a, "Node A")
        
        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Node B")

        # 2. 初始状态下 DB 为空
        assert len(db_manager.get_all_node_hashes()) == 0

        # 3. 执行补水
        hydrator.sync()

        # 4. 验证
        db_hashes = db_manager.get_all_node_hashes()
        assert len(db_hashes) == 2
        
        conn = db_manager._get_conn()
        # 验证 Node B 的内容
        node_b_row = conn.execute("SELECT * FROM nodes WHERE summary = ?", ("Node B",)).fetchone()
        assert node_b_row is not None
        assert node_b_row["plan_md_cache"] is None  # 必须是冷数据

        # 验证边关系
        edge_row = conn.execute("SELECT * FROM edges WHERE child_hash = ?", (node_b_row["commit_hash"],)).fetchone()
        assert edge_row is not None

    def test_incremental_hydration(self, hydrator_setup):
        """测试只补水增量部分。"""
        hydrator, writer, git_db, db_manager, repo = hydrator_setup

        # 1. 创建节点 A 并立即补水
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", "genesis", hash_a, "Node A")
        hydrator.sync()
        assert len(db_manager.get_all_node_hashes()) == 1

        # 2. 创建节点 B
        (repo / "b.txt").touch()
        hash_b = git_db.get_tree_hash()
        writer.create_node("plan", hash_a, hash_b, "Node B")
        
        # 3. 再次补水
        hydrator.sync()

        # 4. 验证，总数应为 2
        assert len(db_manager.get_all_node_hashes()) == 2
        
        conn = db_manager._get_conn()
        node_b_row = conn.execute("SELECT * FROM nodes WHERE summary = ?", ("Node B",)).fetchone()
        assert node_b_row is not None

    def test_hydration_idempotency(self, hydrator_setup):
        """测试重复运行补水不会产生副作用。"""
        hydrator, writer, git_db, db_manager, repo = hydrator_setup
        
        (repo / "a.txt").touch()
        hash_a = git_db.get_tree_hash()
        writer.create_node("plan", "genesis", hash_a, "Node A")

        # 运行两次
        hydrator.sync()
        hydrator.sync()

        assert len(db_manager.get_all_node_hashes()) == 1
~~~~~
