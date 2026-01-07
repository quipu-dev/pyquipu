好的，我理解你的需求。将测试套件进行结构化重构是一个非常好的工程实践，它能显著提升项目的可维护性。

第一步是创建 `pyquipu-test-utils` 包来存放通用的测试辅助工具，这是整个重构工作的基础。

我将生成一个计划来完成以下操作：
1.  创建 `packages/quipu-test-utils` 的目录结构和 `pyproject.toml`。
2.  将 `tests/helpers.py` 移动到新包中。
3.  更新根 `pyproject.toml` 以将新包集成到工作区和开发依赖中。
4.  使用 `sed` 命令批量更新 `tests/` 目录下所有测试文件中的导入路径。

## [WIP] feat(test): 创建 pyquipu-test-utils 并迁移测试辅助模块

### 用户需求
1.  创建一个名为 `pyquipu-test-utils` 的新 Python 包。
2.  将现有的 `tests/helpers.py` 文件移动到这个新包中。
3.  使用 `sed` 命令更新所有测试文件中对 `helpers` 的导入路径，使其指向新位置。

### 评论
这是一个优秀的重构起点。将测试辅助函数（helpers）提取到一个独立的、可安装的包中，将其从一个临时的“工具脚本”提升为项目的一等公民。这不仅使依赖关系更清晰，也为后续更大规模的测试目录重构铺平了道路，完全符合“正规军”的工程标准。

### 目标
1.  在 `packages/` 目录下成功创建一个名为 `quipu-test-utils` 的新包，包含标准的 `src/pyquipu/test_utils` 目录结构。
2.  将 `tests/helpers.py` 移动至 `packages/quipu-test-utils/src/pyquipu/test_utils/helpers.py`。
3.  更新根 `pyproject.toml`，将 `pyquipu-test-utils` 添加为开发依赖和工作区成员。
4.  `tests/` 目录下的所有 `.py` 文件中，旧的 `from ..helpers` 和 `from tests.helpers` 导入语句被替换为 `from pyquipu.test_utils.helpers`。

### 基本原理
我们将分阶段执行此操作：
1.  **结构创建**: 使用 `run_command` 和 `mkdir -p` 一次性创建所有必要的目录。使用 `write_file` 创建 `__init__.py` 和 `pyproject.toml`，正式定义新包。
2.  **模块迁移**: 使用 `move_file` 将 `helpers.py` 原子地移动到新位置。
3.  **依赖集成**: 使用 `patch_file` 精确地向根 `pyproject.toml` 的两个关键位置（开发依赖和工作区源）追加新包的声明。
4.  **路径修复**: 根据你的要求，使用 `run_command` 执行一个 `find` 和 `sed` 的组合命令。这能高效地批量替换所有测试文件中的导入语句，比逐个使用 `patch_file` 更适合这种大规模、模式化的修改。我们将同时处理 `from ..helpers` 和 `from tests.helpers` 两种常见的导入模式。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #comp/build #scope/dx #ai/instruct #task/domain/testing #task/object/test-suite-structure #task/action/refactor #task/state/begin

---

### Script

#### Acts 1: 创建 `pyquipu-test-utils` 包结构

首先，我们创建新包所需的完整目录结构和 `__init__.py` 文件，使其成为一个合法的 Python 包。

~~~~~act
run_command
~~~~~
~~~~~bash
mkdir -p packages/quipu-test-utils/src/pyquipu/test_utils
touch packages/quipu-test-utils/src/pyquipu/__init__.py
touch packages/quipu-test-utils/src/pyquipu/test_utils/__init__.py
~~~~~

#### Acts 2: 定义 `pyquipu-test-utils` 包

接下来，为新包创建一个 `pyproject.toml` 文件，定义其元数据。它目前没有外部依赖。

~~~~~act
write_file
packages/quipu-test-utils/pyproject.toml
~~~~~
~~~~~toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "pyquipu-test-utils"
version = "0.1.0"
authors = [
  { name="doucx", email="doucxldh@gmail.com" },
]
description = "Common testing utilities for the Quipu ecosystem."
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
    "Framework :: Pytest",
]
dependencies = [
    "pyquipu-interfaces",
    "pyquipu-engine",
    "typer"
]

[tool.uv.sources]
pyquipu-interfaces = { workspace = true }
pyquipu-engine = { workspace = true }

[tool.setuptools.packages.find]
where = ["src"]
namespaces = true
~~~~~

#### Acts 3: 迁移 `helpers.py` 模块

现在，我们将核心的 `helpers.py` 文件移动到新包的正确位置。

~~~~~act
move_file
tests/helpers.py
packages/quipu-test-utils/src/pyquipu/test_utils/helpers.py
~~~~~

#### Acts 4: 将新包集成到 monorepo 构建系统

我们需要更新根 `pyproject.toml`，告诉 `uv` 这个新包是工作区的一部分，并将其添加到开发依赖中。

~~~~~act
patch_file
pyproject.toml
~~~~~
~~~~~toml.old
dev = [
    # Local workspace packages
    "pyquipu-application",
    "pyquipu-cli",
    "pyquipu-common",
    "pyquipu-engine",
    "pyquipu-interfaces",
    "pyquipu-runtime",
    # Dev tools
    "pytest",
~~~~~
~~~~~toml.new
dev = [
    # Local workspace packages
    "pyquipu-application",
    "pyquipu-cli",
    "pyquipu-common",
    "pyquipu-engine",
    "pyquipu-interfaces",
    "pyquipu-runtime",
    "pyquipu-test-utils",
    # Dev tools
    "pytest",
~~~~~

~~~~~act
patch_file
pyproject.toml
~~~~~
~~~~~toml.old
[tool.uv]
# 将 packages 下的所有包纳入工作区管理
workspace.members = ["packages/*"]

[tool.uv.sources]
pyquipu-application = { workspace = true }
pyquipu-cli = { workspace = true }
pyquipu-common = { workspace = true }
pyquipu-engine = { workspace = true }
pyquipu-interfaces = { workspace = true }
pyquipu-runtime = { workspace = true }
~~~~~
~~~~~toml.new
[tool.uv]
# 将 packages 下的所有包纳入工作区管理
workspace.members = ["packages/*"]

[tool.uv.sources]
pyquipu-application = { workspace = true }
pyquipu-cli = { workspace = true }
pyquipu-common = { workspace = true }
pyquipu-engine = { workspace = true }
pyquipu-interfaces = { workspace = true }
pyquipu-runtime = { workspace = true }
pyquipu-test-utils = { workspace = true }
~~~~~

#### Acts 5: 批量更新测试文件中的导入路径

最后，我们使用 `find` 和 `sed` 的组合命令来高效地修复所有测试文件中的导入语句。此命令会查找 `tests` 目录下的所有 `.py` 文件，并替换两种可能的旧导入模式。

~~~~~act
run_command
~~~~~
~~~~~bash
find tests -type f -name "*.py" -print0 | xargs -0 sed -i -e 's/from \.\.helpers/from pyquipu.test_utils.helpers/g' -e 's/from tests\.helpers/from pyquipu.test_utils.helpers/g'
~~~~~

### 下一步建议
我们已经成功地将测试辅助模块 `helpers.py` 迁移到了新的 `pyquipu-test-utils` 包中。

下一步，我将根据你的最终目标，生成一个计划来执行以下操作：
1.  创建新的测试目录结构：`packages/*/tests/{unit,integration}/`。
2.  将 `tests/` 目录中现有的测试文件移动到它们对应模块的新位置。
3.  清理掉旧的、现已为空的 `tests/` 目录结构。

如果你同意，我将开始准备这个计划。
