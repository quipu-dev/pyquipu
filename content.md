# fix: 解决数据库连接未关闭的资源警告

## 用户需求
检查当前的开发状态，并解决 `pytest` 输出中出现的 `ResourceWarning`。

## 评论
当前状态非常好。所有 125 个测试均已通过，这证明了上一阶段对 `test_sqlite_writer.py` 的修复是成功的，并且核心的 SQLite 双写功能已经按预期工作。

同时，测试输出中出现了两条新的 `ResourceWarning: unclosed database`。这是一个明确的信号，表明在某些代码路径中，我们创建了 SQLite 数据库连接，但在测试结束时没有显式地关闭它。这虽然在短期内不影响功能，但属于资源泄漏，是潜在的不稳定因素，必须修复。

问题的根源在于 `factory.py` 中创建了 `DatabaseManager` 实例，但没有一个明确的机制来调用其 `close()` 方法。

## 目标
1.  消除所有 `ResourceWarning`。
2.  建立一个健壮的资源管理模式，确保 `DatabaseManager` 创建的数据库连接总能被安全关闭。

## 基本原理
我们将实施一个简单的资源管理生命周期，确保由 `QuipuApplication` 创建的核心资源 (`Engine`) 能够被妥善清理。

1.  **资源传递**: `Engine` 将直接持有 `DatabaseManager` 实例的引用，而不是通过 `Writer` 间接持有。这使得 `Engine` 成为所有核心资源的统一管理者。
2.  **添加清理接口**: 为 `Engine` 添加一个 `close()` 方法，该方法会调用其持有的 `DatabaseManager` 实例的 `close()` 方法。
3.  **生命周期管理**: 在核心业务逻辑的入口包装器 `run_quipu` (位于 `controller.py`) 中，使用 `try...finally` 结构。无论业务逻辑成功还是失败，`finally` 块都将确保调用 `app.engine.close()`，从而安全地关闭数据库连接。
4.  **安全回退 (Safety Net)**: 在 `DatabaseManager` 中添加一个 `__del__` 方法。这是一个安全措施，如果 `close()` 由于某种原因未能被调用，Python 的垃圾回收机制在销毁对象时会尝试关闭连接，这有助于在非预期的情况下减少资源泄漏。

这个方案将资源管理的责任放在了应用生命周期的最高层，确保了无论发生何种异常，资源清理步骤都会被执行。

## 标签
#intent/fix #flow/ready #priority/high
#comp/engine #comp/cli #concept/state
#ai/delegate
#task/domain/storage #task/object/sqlite-backend #task/action/integration
#task/state/continue #task/status/active

---

## Script

### Acts 1: 增强资源管理

我们将修改 `Engine`、`factory` 和 `controller`，以建立一个明确的资源初始化和清理流程。

~~~~~act
replace packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~
~~~~~python
from .git_db import GitDB
from .config import ConfigManager
from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter

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

    def __init__(self, root_dir: Path, db: Any, reader: HistoryReader, writer: HistoryWriter):
        self.root_dir = root_dir.resolve()
        self.quipu_dir = self.root_dir / ".quipu"
        self.quipu_dir.mkdir(exist_ok=True)  # 确保 .quipu 目录存在
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

        self.git_db = db  # <-- 依赖注入
        self.reader = reader
        self.writer = writer
        self.history_graph: Dict[str, QuipuNode] = {}
        self.current_node: Optional[QuipuNode] = None

        # Only sync ignores if it's a real git repo
        if isinstance(db, GitDB):
            self._sync_persistent_ignores()
~~~~~
~~~~~python
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
        """关闭引擎持有的所有资源，如数据库连接。"""
        if self.db_manager:
            self.db_manager.close()
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/factory.py
~~~~~
~~~~~python
def create_engine(work_dir: Path) -> Engine:
    """
    实例化完整的 Engine 堆栈。

    会自动向上查找项目根目录 (Git Root) 来初始化 Engine。
    此工厂由配置驱动，以决定使用何种存储后端。
    """
    project_root = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(project_root)
    storage_type = config.get("storage.type", "git_object")
    git_db = GitDB(project_root)

    # 默认和备用后端
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    if storage_type == "sqlite":
        if not DatabaseManager or not SQLiteHistoryWriter:
            raise ImportError("SQLite dependencies could not be loaded. Please check your installation.")

        logger.debug("Using SQLite storage format for writes.")
        db_manager = DatabaseManager(project_root)
        db_manager.init_schema()

        # **关键**: 写入路径被替换，读取路径保持不变
        # 这允许我们在后台安全地填充数据库，而不影响现有功能
        writer = SQLiteHistoryWriter(git_writer=writer, db_manager=db_manager)

    elif storage_type != "git_object":
        raise NotImplementedError(f"Storage type '{storage_type}' is not supported.")

    engine = Engine(project_root, db=git_db, reader=reader, writer=writer)
    engine.align()

    return engine
~~~~~
~~~~~python
def create_engine(work_dir: Path) -> Engine:
    """
    实例化完整的 Engine 堆栈。

    会自动向上查找项目根目录 (Git Root) 来初始化 Engine。
    此工厂由配置驱动，以决定使用何种存储后端。
    """
    project_root = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(project_root)
    storage_type = config.get("storage.type", "git_object")
    git_db = GitDB(project_root)
    db_manager = None

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

    # 将所有资源注入 Engine
    engine = Engine(project_root, db=git_db, reader=reader, writer=writer, db_manager=db_manager)
    engine.align()

    return engine
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/controller.py
~~~~~
~~~~~python
def run_quipu(content: str, work_dir: Path, parser_name: str = "auto", yolo: bool = False) -> QuipuResult:
    """
    Quipu 核心业务逻辑的入口包装器。

    实例化并运行 QuipuApplication，捕获所有异常并转化为 QuipuResult。
    """
    try:
        app = QuipuApplication(work_dir=work_dir, yolo=yolo)
        return app.run(content=content, parser_name=parser_name)

    except CoreExecutionError as e:
        # 预期的执行错误 (如文件找不到，Git 冲突等)
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(success=False, exit_code=1, message=str(e), error=e)

    except Exception as e:
        # 意外的运行时错误
        logger.error(f"运行时错误: {e}", exc_info=True)
        return QuipuResult(success=False, exit_code=1, message=f"系统错误: {e}", error=e)
~~~~~
~~~~~python
def run_quipu(content: str, work_dir: Path, parser_name: str = "auto", yolo: bool = False) -> QuipuResult:
    """
    Quipu 核心业务逻辑的入口包装器。

    实例化并运行 QuipuApplication，捕获所有异常并转化为 QuipuResult。
    确保资源被安全释放。
    """
    app = None
    try:
        app = QuipuApplication(work_dir=work_dir, yolo=yolo)
        return app.run(content=content, parser_name=parser_name)

    except CoreExecutionError as e:
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(success=False, exit_code=1, message=str(e), error=e)

    except Exception as e:
        logger.error(f"运行时错误: {e}", exc_info=True)
        return QuipuResult(success=False, exit_code=1, message=f"系统错误: {e}", error=e)
    finally:
        # 确保无论成功或失败，引擎资源都被关闭
        if app and hasattr(app, "engine") and app.engine:
            app.engine.close()
~~~~~

### Acts 2: 增加数据库连接安全网

为了进一步提高健壮性，我们在 `DatabaseManager` 中添加 `__del__` 方法。

~~~~~act
replace packages/quipu-engine/src/quipu/core/sqlite_db.py
~~~~~
~~~~~python
    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("🗃️  数据库连接已关闭。")
~~~~~
~~~~~python
    def close(self):
        """关闭数据库连接。"""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.debug("🗃️  数据库连接已关闭。")

    def __del__(self):
        """析构函数，作为关闭连接的最后一道防线。"""
        self.close()
~~~~~
