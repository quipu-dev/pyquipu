# fix-test: 修复 pytest 因模块路径问题导致的测试收集失败

## 用户需求
在运行 `pytest` 时，测试收集阶段因 `ModuleNotFoundError: No module named 'quipu.acts'` 而中断。这发生在 `tests/conftest.py` 尝试从项目包 (`quipu-runtime`) 中导入模块时，表明 `pytest` 无法找到项目的源代码。

## 评论
这是一个在 `src` 布局的 monorepo 结构中很常见的路径配置问题。测试运行器默认不知道要去每个 `packages/*/src` 目录下查找模块。最直接和健壮的解决方案是在根 `pyproject.toml` 文件中为 `pytest` 配置 `pythonpath`，明确告知它所有源码目录的位置。

## 目标
修改根目录下的 `pyproject.toml` 文件，添加 `[tool.pytest.ini_options]` 配置节，并将所有四个核心包的 `src` 目录添加到 `pythonpath` 中。这将允许 `pytest` 在测试收集和执行期间正确解析所有 `quipu.*` 模块的导入。

## 基本原理
通过在项目的配置文件中声明测试路径，我们使得测试环境的建立变得声明式且可复现，不再依赖于开发者是否正确激活了通过 `pip install -e` 安装的环境。这是一种更现代、更可靠的 Python 项目测试配置方式，特别适用于复杂的工作区结构。

## 标签
#comp/tests #comp/build #scope/dx

---

## Script

### Acts 1: 配置 Pytest 的 Python 路径

修改根目录的 `pyproject.toml` 文件，为其添加 `pytest` 的 `pythonpath` 配置。

~~~~~act
replace
~~~~~

~~~~~path
pyproject.toml
~~~~~

~~~~~toml
[project]
name = "quipu-monorepo"
version = "0.1.0"
description = "Quipu Development Monorepo"
requires-python = ">=3.10"
dependencies = []

[tool.uv]
# 将 packages 下的所有包纳入工作区管理
workspace.members = ["packages/*"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
~~~~~

~~~~~toml
[project]
name = "quipu-monorepo"
version = "0.1.0"
description = "Quipu Development Monorepo"
requires-python = ">=3.10"
dependencies = []

[tool.uv]
# 将 packages 下的所有包纳入工作区管理
workspace.members = ["packages/*"]

[tool.pytest.ini_options]
pythonpath = [
  "packages/quipu-interfaces/src",
  "packages/quipu-engine/src",
  "packages/quipu-runtime/src",
  "packages/quipu-cli/src",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
~~~~~