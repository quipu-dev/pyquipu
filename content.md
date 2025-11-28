好的，这是一个关于如何将旧版本 Quipu 数据迁移到新版本 v1.1 架构的完整分析和执行计划。

此计划将遵循你项目中的 [结构化计划模板](02_PROMPTS/04_Quipu结构化计划模板.md) 格式。

---

我将为你生成一个完整的迁移方案。核心任务是将旧的、单用户模式的 Git 引用 (`refs/quipu/heads/*`) 迁移到新的、支持多用户的本地命名空间 (`refs/quipu/local/heads/*`)，并确保 SQLite 缓存能正确识别和补水这些数据。

## feat: 为 v1.1 架构创建数据迁移工具

### 用户需求
用户需要一个可靠的、一次性的工具，将现有的、基于旧版（v1.0）引用规范的 Quipu 历史数据，无损地迁移到 v1.1 规范。迁移过程应当是自动化的，并能正确处理用户身份 (`owner_id`) 的分配。

### 评论
这是一个关键的赋能型任务，确保了项目的向后兼容性和用户数据的平滑过渡。由于变更直接触及底层的 Git 引用，因此操作必须是原子的、幂等的，并有充分的安全检查。

### 目标
1.  创建一个新的 CLI 命令 `quipu migrate-data`，专门用于执行一次性迁移。
2.  该命令能自动检测旧版（v1.0）的引用格式。
3.  将所有旧的 `refs/quipu/heads/{hash}` 引用，移动到新的 `refs/quipu/local/heads/{hash}` 路径下。
4.  在迁移后，触发 SQLite 的数据补水 (`Hydrator`)，以确保 `nodes` 表中的新 `owner_id` 字段被正确填充。
5.  在执行破坏性操作（删除旧引用）前，必须有明确的用户确认环节。

### 基本原理
迁移的核心在于移动 Git 的指针（引用），而非修改 Git 的数据对象（commits, trees, blobs）。此过程分为三步：
1.  **识别 (Identify)**: 扫描 `.git/refs/quipu/heads/` 目录，找到所有代表旧版历史分支末端的 commit 哈希。
2.  **重定位 (Relocate)**: 为每一个找到的 commit 哈希，在新的 `refs/quipu/local/heads/` 目录下创建一个同名的新引用，然后安全地删除旧引用。
3.  **补水 (Hydrate)**: 在引用重定位后，原有的 SQLite 缓存可能已过时或不包含 `owner_id`。通过运行 `Hydrator`，可以强制它重新扫描所有 `refs/quipu/` 下的引用（包括新路径），并根据引用路径（本地分支归属于当前用户）来增量更新数据库，填入正确的 `owner_id`。

### 标签
#intent/build #flow/ready #priority/critical 
#comp/cli #comp/engine #concept/history #scope/core 
#ai/brainstorm
#task/domain/storage #task/object/data-migration #task/action/build
#task/state/begin

---

### Script

我们将创建一个新的 `migration.py` 模块来封装迁移逻辑，并在 `main.py` 中添加对应的命令入口。

#### Acts 1: 在 `quipu-cli` 中创建迁移逻辑模块

首先，我们需要一个专门处理迁移过程的文件。

~~~~~act
write_file
packages/quipu-cli/src/quipu/cli/migration.py
~~~~~
~~~~~python
import logging
import subprocess
from typing import List, Optional

from quipu.core.git_db import GitDB
from quipu.core.hydrator import Hydrator
from quipu.core.config import ConfigManager
from quipu.common.identity import get_user_id_from_email

logger = logging.getLogger(__name__)


class MigrationManager:
    """负责将旧版 Quipu 数据迁移到 v1.1 架构。"""

    LEGACY_REFS_PREFIX = "refs/quipu/heads/"
    NEW_REFS_PREFIX = "refs/quipu/local/heads/"

    def __init__(self, git_db: GitDB, config_manager: ConfigManager, hydrator: Hydrator):
        self.git_db = git_db
        self.config_manager = config_manager
        self.hydrator = hydrator
        self.root_dir = git_db.root

    def _find_legacy_heads(self) -> List[str]:
        """查找所有旧格式的 head commit 哈希。"""
        ref_tuples = self.git_db.get_all_ref_heads(self.LEGACY_REFS_PREFIX)
        return [commit_hash for commit_hash, ref_name in ref_tuples]

    def _get_local_user_id(self) -> str:
        """获取或生成本地用户的 ID，用于补水。"""
        user_id = self.config_manager.get("sync.user_id")
        if user_id:
            return user_id

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
                return get_user_id_from_email(email)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning("无法从 git config 获取 user.email，将使用默认值。")
        
        return "unknown-local-user"

    def run(self) -> bool:
        """执行完整的迁移流程。"""
        legacy_heads = self._find_legacy_heads()
        if not legacy_heads:
            logger.info("✅ 未找到旧版（v1.0）数据引用，无需迁移。")
            return True

        logger.info(f"🔍 发现 {len(legacy_heads)} 个旧版历史分支，准备迁移...")

        # 核心迁移逻辑
        for commit_hash in legacy_heads:
            old_ref = f"{self.LEGACY_REFS_PREFIX}{commit_hash}"
            new_ref = f"{self.NEW_REFS_PREFIX}{commit_hash}"
            
            logger.debug(f"  - 正在移动: {old_ref} -> {new_ref}")
            # 1. 创建新引用
            self.git_db.update_ref(new_ref, commit_hash)
            # 2. 删除旧引用
            self.git_db.delete_ref(old_ref)

        logger.info("✅ Git 引用已成功迁移到 v1.1 格式。")

        # 触发数据补水
        logger.info("💧 正在将迁移后的数据同步到 SQLite 缓存...")
        user_id = self._get_local_user_id()
        self.hydrator.sync(local_user_id=user_id)
        
        logger.info("🎉 迁移完成！")
        return True

~~~~~

#### Acts 2: 在 `main.py` 中添加 `migrate-data` 命令

现在，我们将这个迁移逻辑暴露为一个用户可以执行的 CLI 命令。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
from .utils import find_git_repository_root
from .view_model import GraphViewModel
from quipu.core.plugin_loader import load_plugins
from quipu.core.executor import Executor
~~~~~
~~~~~python
from .utils import find_git_repository_root
from .view_model import GraphViewModel
from quipu.core.plugin_loader import load_plugins
from quipu.core.executor import Executor
from .migration import MigrationManager
from quipu.core.hydrator import Hydrator
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
@cache_app.command("rebuild")
def cache_rebuild(
    ctx: typer.Context,
~~~~~
~~~~~python
@app.command("migrate-data")
def migrate_data(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
    force: Annotated[bool, typer.Option("--force", "-f", help="强制执行，跳过确认提示。")] = False,
):
    """
    将旧版（v1.0）的 Quipu 数据迁移到新的 v1.1 格式。
    这是一个一次性操作。
    """
    setup_logging()
    project_root = find_git_repository_root(work_dir) or work_dir
    
    if not force:
        prompt = (
            "🚨 即将开始数据迁移。此操作将重命名内部 Git 引用以兼容新版本。\n"
            "   该过程通常是安全的，但建议在执行前备份您的 .git 目录。\n"
            "   是否继续？"
        )
        if not _prompt_for_confirmation(prompt, default=False):
            typer.secho("\n🚫 操作已取消。", fg=typer.colors.YELLOW, err=True)
            raise typer.Abort()

    engine = None
    try:
        # 我们需要一个 engine 实例来获取其内部组件
        engine = create_engine(project_root, lazy=True)
        config = ConfigManager(project_root)
        hydrator = Hydrator(engine.git_db, engine.db_manager)
        
        manager = MigrationManager(engine.git_db, config, hydrator)
        success = manager.run()
        
        if success:
            typer.secho("✅ 数据迁移成功完成。", fg=typer.colors.GREEN, err=True)
        else:
            typer.secho("❌ 数据迁移过程中发生错误。", fg=typer.colors.RED, err=True)
            ctx.exit(1)
            
    except Exception as e:
        typer.secho(f"❌ 迁移失败，发生意外错误: {e}", fg=typer.colors.RED, err=True)
        logger.error("Migration failed", exc_info=True)
        ctx.exit(1)
    finally:
        if engine:
            engine.close()


@cache_app.command("rebuild")
def cache_rebuild(
    ctx: typer.Context,
~~~~~

#### Acts 3: 验证 `Hydrator` 对新本地路径的支持

检查 `hydrator.py` 中的 `_get_owner_from_ref` 函数是否能正确处理 `refs/quipu/local/heads/` 路径。

根据你提供的 `packages/quipu-engine/src/quipu/core/hydrator.py` 文件内容：
```python
    def _get_owner_from_ref(self, ref_name: str, local_user_id: str) -> Optional[str]:
        """从 Git ref 路径中解析 owner_id。"""
        # ... (remote match)

        # 匹配 local heads
        if ref_name.startswith("refs/quipu/local/heads/"):
            return local_user_id

        return None
```
该函数已经能够正确处理新的本地引用路径。因此，我们无需修改 `quipu-engine`，迁移脚本可以直接复用现有的补水逻辑。这是一个好消息，它简化了迁移过程。

### 下一步建议
1.  **编写集成测试**: 为 `MigrationManager` 编写一个集成测试，模拟一个包含旧版引用的 Git 仓库，运行迁移，并断言新引用已创建、旧引用已删除、SQLite 数据库中的节点具有正确的 `owner_id`。
2.  **更新文档**: 在用户文档中增加一个“版本升级”章节，说明何时以及如何运行 `quipu migrate-data` 命令。
