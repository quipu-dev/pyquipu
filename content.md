# fix-test: 修复命名空间包导入错误

## 目标
通过正确配置 `quipu` 命名空间包，解决所有在 `pytest` 收集阶段出现的 `ModuleNotFoundError`。

## 基本原理
根据 PEP 420，命名空间包的目录不应包含 `__init__.py` 文件。当前项目中 `packages/quipu-interfaces/src/quipu/__init__.py` 的存在，导致 Python 错误地将 `quipu` 识别为一个常规包，从而阻止了对 `quipu-runtime`、`quipu-engine` 等其他部分中模块的发现。

通过删除这个文件，我们将 `quipu` 修正为一个隐式命名空间包，允许 Python 的导入系统正确地从 `pythonpath` 中所有指定的位置加载其组成部分。同时，我们将清理掉项目根目录下已废弃的 `core` 目录。

## 标签
#fix #test #refactor

---

## Script

### Act 1: 移除错误的 __init__.py 以启用命名空间包

此操作将删除导致 `quipu` 包被错误识别为常规包的文件。

~~~~~act
delete_file
~~~~~

~~~~~path
packages/quipu-interfaces/src/quipu/__init__.py
~~~~~

### Act 2: 清理项目根目录下废弃的 core 目录

这是一个清理步骤，移除重构后遗留的空目录。

~~~~~act
delete_file
~~~~~

~~~~~path
core
~~~~~