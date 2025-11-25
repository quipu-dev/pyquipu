# refactor-runtime 迁移核心 Acts 到 Runtime 包

## 目标
将根目录下的 `acts/` 模块迁移至 `packages/quipu-runtime/src/quipu/acts/`，并修改 `quipu-cli` 的加载逻辑，使其直接从 `quipu-runtime` 包中加载核心 Acts。

## 基本原理
当前核心 Acts（如 `write_file`, `replace`）作为松散文件存在于根目录，导致通过 `pip` 安装 `quipu-runtime` 后，用户缺少这些基础能力。将它们打包进 `quipu-runtime` 并提供统一的注册入口，可以确保用户环境开箱即用，并符合 Monorepo 的模块化设计。

## 标签
#refactor #runtime #cli

---

## Script

### Act 1: 创建 Runtime Acts 注册入口

在 `quipu-runtime` 包中创建 `__init__.py`，负责导入并注册所有核心 Act 模块。

~~~~~act
write_file
~~~~~

~~~~~path
packages/quipu-runtime/src/quipu/acts/__init__.py
~~~~~

~~~~~python
from . import basic, check, git, memory, read, refactor, shell

def register_core_acts(executor):
    """注册所有核心 Acts"""
    basic.register(executor)
    check.register(executor)
    git.register(executor)
    memory.register(executor)
    read.register(executor)
    refactor.register(executor)
    shell.register(executor)
~~~~~

### Act 2: 迁移 Act 文件

将 7 个核心 Act 模块从根目录移动到 `quipu-runtime` 包内。

~~~~~act
move_file acts/basic.py packages/quipu-runtime/src/quipu/acts/basic.py
~~~~~

~~~~~act
move_file acts/check.py packages/quipu-runtime/src/quipu/acts/check.py
~~~~~

~~~~~act
move_file acts/git.py packages/quipu-runtime/src/quipu/acts/git.py
~~~~~

~~~~~act
move_file acts/memory.py packages/quipu-runtime/src/quipu/acts/memory.py
~~~~~

~~~~~act
move_file acts/read.py packages/quipu-runtime/src/quipu/acts/read.py
~~~~~

~~~~~act
move_file acts/refactor.py packages/quipu-runtime/src/quipu/acts/refactor.py
~~~~~

~~~~~act
move_file acts/shell.py packages/quipu-runtime/src/quipu/acts/shell.py
~~~~~

### Act 3: 更新 CLI Controller

修改控制器，不再从文件系统加载根目录的 `acts`，而是调用 `quipu.acts.register_core_acts`。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/controller.py
~~~~~

~~~~~python
from .config import PROJECT_ROOT

logger = logging.getLogger(__name__)
~~~~~

~~~~~python
from .config import PROJECT_ROOT
from quipu.acts import register_core_acts

logger = logging.getLogger(__name__)
~~~~~

~~~~~act
replace packages/quipu-cli/src/quipu/cli/controller.py
~~~~~

~~~~~python
        # 加载插件
        load_plugins(executor, PROJECT_ROOT / "acts") # 内置
        _load_extra_plugins(executor, project_root)       # 外部 (也基于 project_root)
~~~~~

~~~~~python
        # 加载插件
        register_core_acts(executor) # 内置 (从 runtime 包加载)
        _load_extra_plugins(executor, project_root)       # 外部 (也基于 project_root)
~~~~~

### Act 4: 更新 CLI Config

修改项目根目录查找逻辑，移除对 `acts` 目录存在的依赖。

~~~~~act
replace packages/quipu-cli/src/quipu/cli/config.py
~~~~~

~~~~~python
    """
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "acts").exists() and (parent / "packages").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            # 简单的检查，看是否是顶层配置
~~~~~

~~~~~python
    """
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "packages").exists() and (parent / "pyproject.toml").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            # 简单的检查，看是否是顶层配置
~~~~~

### Act 5: 清理旧 Acts 目录

删除根目录下残留的 `acts` 目录（包含旧的 `__init__.py`）。

~~~~~act
delete_file acts
~~~~~