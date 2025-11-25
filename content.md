# fix: 为开发元包添加命令行入口点

## 目标
修改根 `pyproject.toml` 文件，使其在开发安装时能够正确创建 `quipu` 命令行工具，解决 `command not found` 的问题。

## 基本原理
`pip` 在安装一个包时，只会读取该包自身的 `pyproject.toml` 来决定是否创建命令行脚本。我们当前安装的 `quipu-dev` 元包的配置中缺少 `[project.scripts]` 部分，因此 `pip` 没有创建 `quipu` 命令。

通过将 `quipu-cli` 包中定义的 `[project.scripts]` 配置复制到根 `pyproject.toml` 中，我们告诉 `setuptools`：在安装 `quipu-dev` 这个开发环境时，请一并创建指向 `quipu.cli.main:app` 的 `quipu` 命令行入口。

## 标签
#fix #chore #build

---

## Script

### Act 1: 在根 pyproject.toml 中定义命令行脚本

此操作将为我们的 `quipu-dev` 元包添加必要的 `[project.scripts]` 配置。

~~~~~act
replace pyproject.toml
~~~~~

~~~~~toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "quipu-dev"
version = "0.1.0"
description = "Metapackage for the Quipu monorepo development environment."
requires-python = ">=3.8"

[tool.setuptools]
py-modules = []

[tool.setuptools.packages.find]
where = ["packages"]
include = ["quipu*"]

[tool.pytest.ini_options]
pythonpath = [
    ".",
    "packages/quipu-interfaces/src",
    "packages/quipu-engine/src",
    "packages/quipu-runtime/src",
    "packages/quipu-cli/src",
]
testpaths = ["tests"]
log_cli = true
log_cli_level = "INFO"
~~~~~

~~~~~toml
[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[project]
name = "quipu-dev"
version = "0.1.0"
description = "Metapackage for the Quipu monorepo development environment."
requires-python = ">=3.8"

[project.scripts]
quipu = "quipu.cli.main:app"

[tool.setuptools]
py-modules = []

[tool.setuptools.packages.find]
where = ["packages"]
include = ["quipu*"]

[tool.pytest.ini_options]
pythonpath = [
    ".",
    "packages/quipu-interfaces/src",
    "packages/quipu-engine/src",
    "packages/quipu-runtime/src",
    "packages/quipu-cli/src",
]
testpaths = ["tests"]
log_cli = true
log_cli_level = "INFO"
~~~~~