好的，我们立即开始创建 `pyquipu-application` 包。

这是一个奠定未来架构基础的关键步骤。我们将创建必要的文件和目录，并更新工作区的配置，为后续的逻辑迁移做好准备。

## [WIP] feat: 创建核心业务逻辑包 `pyquipu-application`

### 用户需求
为了实现 `cli` 和 `webapi` 等不同入口的逻辑复用，并遵循 DRY (Don't Repeat Yourself) 原则，需要创建一个新的核心包 `pyquipu-application`，用于承载与具体表现层（如 CLI 或 Web）无关的通用业务逻辑。

### 评论
这是对项目架构的一次重要重构。通过将应用逻辑从 `pyquipu-cli` 中剥离出来，我们建立了一个清晰、单向的依赖关系，极大地提升了项目的可维护性、可测试性和未来的可扩展性。

### 目标
1.  创建 `packages/quipu-application` 目录结构。
2.  为新包创建 `pyproject.toml` 文件，并定义其对 `engine`, `runtime`, `interfaces` 和 `common` 包的依赖。
3.  更新根 `pyproject.toml`，将新包纳入 UV 工作区管理和 Pytest 的 `pythonpath` 中。
4.  更新 `dev-requirements.txt`，将新包加入开发环境。

### 基本原理
通过在 `packages` 目录下新增一个标准的 Python 包，并调整 monorepo 的相关配置（`pyproject.toml`, `dev-requirements.txt`），我们可以将 `pyquipu-application` 无缝地集成到现有的开发工作流中。这为下一步从 `pyquipu-cli` 中安全地迁移代码提供了必要的基础设施。

### 标签
#intent/architect #flow/ready #priority/high #comp/build #scope/core #dx #ai/instruct #task/domain/architecture #task/object/core-application-layer #task/action/creation #task/state/begin

---

### Script

#### Acts 1: 创建 `pyquipu-application` 包的 `pyproject.toml`

这是新包的核心定义文件。

~~~~~act
write_file
packages/quipu-application/pyproject.toml
~~~~~
~~~~~toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "pyquipu-application"
version = "0.1.0"
authors = [
  { name="doucx", email="doucxldh@gmail.com" },
]
description = "Core application logic for the Quipu ecosystem, coordinating the engine and runtime."
requires-python = ">=3.10"
license = { text = "Apache-2.0" }
classifiers = [
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: Apache Software License",
    "Operating System :: OS Independent",
]
dependencies = [
    "pyquipu-interfaces",
    "pyquipu-engine",
    "pyquipu-runtime",
    "pyquipu-common",
]

[tool.uv.sources]
pyquipu-interfaces = { workspace = true }
pyquipu-engine = { workspace = true }
pyquipu-runtime = { workspace = true }
pyquipu-common = { workspace = true }

[tool.setuptools.packages.find]
where = ["src"]
namespaces = true
~~~~~

#### Acts 2: 创建包的源代码目录结构

建立标准的 `src/pyquipu/application` 目录结构。

~~~~~act
write_file
packages/quipu-application/src/pyquipu/application/__init__.py
~~~~~
~~~~~python
# This file makes 'pyquipu.application' a package.
~~~~~

#### Acts 3: 更新根 `pyproject.toml` 以集成新包

将 `pyquipu-application` 添加到 UV 工作区和 Pytest 的 Python 路径中，使其能够被其他包发现和测试。

~~~~~act
patch_file
pyproject.toml
~~~~~
~~~~~toml
[tool.uv]
# 将 packages 下的所有包纳入工作区管理
workspace.members = ["packages/*", "packages/quipu-common"]

[tool.pytest.ini_options]
addopts = "-ra --cov=pyquipu --cov-report=term-missing"
pythonpath = [
  "packages/quipu-interfaces/src",
  "packages/quipu-engine/src",
  "packages/quipu-runtime/src",
  "packages/quipu-cli/src",
  "packages/quipu-common/src",
]
~~~~~
~~~~~toml
[tool.uv]
# 将 packages 下的所有包纳入工作区管理
workspace.members = ["packages/*"]

[tool.pytest.ini_options]
addopts = "-ra --cov=pyquipu --cov-report=term-missing"
pythonpath = [
  "packages/quipu-interfaces/src",
  "packages/quipu-engine/src",
  "packages/quipu-runtime/src",
  "packages/quipu-cli/src",
  "packages/quipu-common/src",
  "packages/quipu-application/src",
]
~~~~~

#### Acts 4: 更新开发依赖文件

将新包添加到 `dev-requirements.txt` 中，以便在开发环境中以可编辑模式安装。

~~~~~act
patch_file
dev-requirements.txt
~~~~~
~~~~~text
-e packages/pyquipu-interfaces
-e packages/pyquipu-engine
-e packages/pyquipu-runtime
-e packages/pyquipu-cli
-e packages/pyquipu-common
~~~~~
~~~~~text
-e packages/pyquipu-interfaces
-e packages/pyquipu-engine
-e packages/quipu-runtime
-e packages/pyquipu-cli
-e packages/quipu-common
-e packages/quipu-application
~~~~~

### 下一步建议
包的基础结构已经搭建完毕。下一步，我们将开始把 `controller.py`, `factory.py` 和 `plugin_manager.py` 从 `pyquipu-cli` 包中迁移到新的 `pyquipu-application` 包中。

