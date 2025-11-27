好的，我将执行任务 1.2 和 1.3。这包括为 `ConfigManager` 增加写入能力，并在 `quipu sync` 命令中实现首次使用的用户身份引导流程。

## feat: 实现 sync 命令的用户身份配置与引导流程

### 用户需求
根据 `Quipu Sync 功能开发任务列表`，需要实现任务 1.2 和 1.3：
1.  升级 `ConfigManager` 以支持 `sync` 配置的读取和写入。
2.  在 `quipu sync` 命令中加入一个引导流程，当用户的 `user_id` 未配置时，自动根据其 Git 邮箱生成并保存。

### 评论
这是为 `sync` 功能构建身份基础的关键一步。通过自动从 `git config` 获取信息并持久化，可以为用户提供一个平滑的首次使用体验，同时为后续的 Refspec 构建提供必要的 `user_id`。为 `ConfigManager` 添加写入能力，也使其成为一个更完整的配置管理工具。

### 目标
1.  在 `quipu-engine` 的 `ConfigManager` 中，更新默认配置以包含 `sync` 部分。
2.  为 `ConfigManager` 添加 `set` 和 `save` 方法，使其能够将变更写回 `.quipu/config.yml` 文件。
3.  在 `quipu-cli` 的 `sync` 命令的开头，实现用户身份的检查与自动配置逻辑。

### 基本原理
1.  **身份源**: `git config user.email` 是 Git 生态中最可靠的用户身份来源。我们将以此为基础，通过 `quipu-common` 中已实现的规范化算法生成一个确定性的、对 Git 引用安全的 `user_id`。
2.  **持久化**: 生成的 `user_id` 必须被持久化到 `.quipu/config.yml` 中。这避免了每次 `sync` 都需要重新计算，并允许用户在需要时手动修改。
3.  **原子化配置**: `ConfigManager` 的写入操作将被设计为“加载-修改-保存”模式，确保配置文件的完整性。

### 标签
#intent/build #flow/ready #priority/high 
#comp/engine #comp/cli #comp/common
#concept/config #concept/sync 
#scope/core #scope/dx 
#ai/instruct
#task/domain/sync #task/object/user-identity #task/action/configuration #task/state/continue

---

### Script

#### Acts 1: 升级 `ConfigManager` (quipu-engine)

我们将为 `ConfigManager` 增加写入配置的能力，并更新默认值。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/config.py
~~~~~
~~~~~python
import yaml
from pathlib import Path
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 默认配置，为所有可能的设置提供一个基础
DEFAULTS = {
    "storage": {
        "type": "git_object",  # 可选: "git_object", "sqlite"
    },
    "sync": {
        "remote_name": "origin",
        "persistent_ignores": [".idea", ".vscode", ".envs", "__pycache__", "node_modules", "o.md"],
    },
    "list_files": {"ignore_patterns": [".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"]},
}


class ConfigManager:
    """
    负责加载和管理 .quipu/config.yml 文件。
    """

    def __init__(self, work_dir: Path):
        self.config_path = work_dir.resolve() / ".quipu" / "config.yml"
        self.user_config: Dict[str, Any] = self._load_config()
~~~~~
~~~~~python
import yaml
from pathlib import Path
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# 默认配置，为所有可能的设置提供一个基础
DEFAULTS = {
    "storage": {
        "type": "git_object",  # 可选: "git_object", "sqlite"
    },
    "sync": {
        "remote_name": "origin",
        "persistent_ignores": [".idea", ".vscode", ".envs", "__pycache__", "node_modules", "o.md"],
        "user_id": None,
        "subscriptions": [],
    },
    "list_files": {"ignore_patterns": [".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"]},
}


class ConfigManager:
    """
    负责加载和管理 .quipu/config.yml 文件。
    """

    def __init__(self, work_dir: Path):
        self.config_path = work_dir.resolve() / ".quipu" / "config.yml"
        self.user_config: Dict[str, Any] = self._load_config()
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/config.py
~~~~~
~~~~~python
    def _get_nested(self, data: Dict, key: str) -> Any:
        """使用点状符号安全地访问嵌套字典。"""
        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current
~~~~~
~~~~~python
    def _get_nested(self, data: Dict, key: str) -> Any:
        """使用点状符号安全地访问嵌套字典。"""
        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

    def set(self, key: str, value: Any):
        """
        设置一个配置值，支持点状符号进行嵌套访问。
        如果中间路径的字典不存在，会自动创建。
        """
        keys = key.split(".")
        d = self.user_config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        logger.debug(f"配置已更新: {key} = {value}")

    def save(self):
        """将当前的 user_config 写回到 .quipu/config.yml 文件。"""
        try:
            self.config_path.parent.mkdir(exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.user_config, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"✅ 配置文件已保存至: {self.config_path}")
        except Exception as e:
            logger.error(f"❌ 保存配置文件失败: {e}")
            raise
~~~~~

#### Acts 2: 在 `sync` 命令中实现引导逻辑 (quipu-cli)

我们将在 `sync` 命令的开头插入身份检查和配置流程。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
from quipu.core.state_machine import Engine
from quipu.core.models import QuipuNode
from quipu.core.git_db import GitDB
import inspect
import subprocess
from quipu.core.config import ConfigManager


# 注意：不要在模块级别直接调用 setup_logging()，
# 否则会导致 CliRunner 测试中的 I/O 流过早绑定/关闭问题。
~~~~~
~~~~~python
from quipu.core.state_machine import Engine
from quipu.core.models import QuipuNode
from quipu.core.git_db import GitDB
import inspect
import subprocess
from quipu.core.config import ConfigManager
from quipu.common.identity import get_user_id_from_email


# 注意：不要在模块级别直接调用 setup_logging()，
# 否则会导致 CliRunner 测试中的 I/O 流过早绑定/关闭问题。
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
@app.command()
def sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
    remote: Annotated[Optional[str], typer.Option("--remote", "-r", help="Git 远程仓库的名称 (覆盖配置文件)。")] = None,
):
    """
    与远程仓库同步 Quipu 历史图谱。
    """
    setup_logging()
    # Sync 必须在 git 项目根目录执行
    sync_dir = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(sync_dir)

    if remote is None:
        remote = config.get("sync.remote_name", "origin")
    refspec = "refs/quipu/history:refs/quipu/history"

    def run_git_command(args: list[str]):
~~~~~
~~~~~python
@app.command()
def sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
    remote: Annotated[Optional[str], typer.Option("--remote", "-r", help="Git 远程仓库的名称 (覆盖配置文件)。")] = None,
):
    """
    与远程仓库同步 Quipu 历史图谱。
    """
    setup_logging()
    # Sync 必须在 git 项目根目录执行
    sync_dir = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(sync_dir)

    # --- 1.3: 首次使用的“引导 (Onboarding)”逻辑 ---
    user_id = config.get("sync.user_id")
    if not user_id:
        typer.secho("🤝 首次使用 sync 功能，正在自动配置用户身份...", fg=typer.colors.BLUE, err=True)
        try:
            result = subprocess.run(
                ["git", "config", "user.email"], cwd=sync_dir, capture_output=True, text=True, check=True
            )
            email = result.stdout.strip()
            if not email:
                raise ValueError("Git user.email is empty.")

            user_id = get_user_id_from_email(email)
            config.set("sync.user_id", user_id)
            config.save()
            typer.secho(f"✅ 已根据你的 Git 邮箱 '{email}' 生成并保存用户 ID: {user_id}", fg=typer.colors.GREEN, err=True)

        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            typer.secho("❌ 错误：无法获取你的 Git 用户邮箱。", fg=typer.colors.RED, err=True)
            typer.secho("💡 请先运行以下命令进行设置:", fg=typer.colors.YELLOW, err=True)
            typer.echo("  git config --global user.email \"you@example.com\"")
            ctx.exit(1)

    if remote is None:
        remote = config.get("sync.remote_name", "origin")
    refspec = "refs/quipu/history:refs/quipu/history"

    def run_git_command(args: list[str]):
~~~~~

### 下一步建议

**关于测试的评估：**

现在是为 `ConfigManager` **编写单元测试**的绝佳时机。新添加的 `set` 和 `save` 方法是纯粹的逻辑，不依赖外部状态，非常适合进行单元测试。这可以确保：
1.  嵌套设置 (`a.b.c`) 的功能正确。
2.  `save` 方法能够正确地将内存中的配置写入 YAML 文件。
3.  加载和保存操作是可逆的。

对于 `sync` 命令的引导流程，可以采取两种策略：
1.  **轻量级测试**: 暂时不测试，因为这部分逻辑与 `subprocess` 和文件系统 I/O 紧密耦合，编写单元测试较为复杂（需要 mock）。
2.  **集成测试**: 在后续的 `sync` 功能集成测试中（例如 `tests/integration/test_sync.py`），将首次使用的场景作为一个测试用例来覆盖。

**我的建议是**：
*   **立即执行**: 为 `ConfigManager` 的读写功能添加单元测试。
*   **稍后执行**: 将 `sync` 命令的引导逻辑测试纳入 `sync` 功能的整体集成测试计划中。

因此，下一步建议是创建一个新的 Plan 来为 `ConfigManager` 增加单元测试。
