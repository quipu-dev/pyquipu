# chore: 为引擎层解耦创建 Git 提交

## 目标
将已完成的“阶段 1.2：界定引擎层”的重构工作固化为一个 Git 提交。

## 基本原理
本次重构成功地将引擎相关的核心模块 (`engine`, `git_db`, `history`, `config_manager`) 从其他逻辑中分离出来，并通过 `eng_` 前缀进行了标识。所有相关引用也已更新，测试套件验证通过。现在需要创建一个清晰的 Git 提交来记录这一进展。

## 标签
 #git #chore

---

## Script

### Act 1: 暂存所有变更

将所有修改过的文件和重命名的文件添加到 Git 暂存区。

~~~~~act
git_add .
~~~~~

### Act 2: 提交变更

创建一条符合规范的 Git 提交信息，总结本次重构的内容。

~~~~~act
git_commit
~~~~~

~~~~~
refactor(core): Define engine layer with `eng_*` prefix

This commit completes Phase 1.2 of the Quipu refactoring plan. It logically isolates the engine-related components within the `core/` directory.

- Renamed `engine.py`, `git_db.py`, `history.py`, and `config_manager.py` to use the `eng_` prefix.
- Updated all corresponding import statements throughout the codebase.

This change establishes a clear boundary for the engine layer, preventing illegal imports from the runtime layer and preparing for the physical package split in Phase 2.
~~~~~