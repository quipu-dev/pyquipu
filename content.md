# chore: 提交存储集成相关的修复

## 用户需求
用户请求将最近完成的、关于存储层集成和相关测试修复的所有代码变更提交到版本控制中。

## 评论
这个提交将固化我们为集成 Git 对象存储后端所做的工作，包括对测试套件的重构以及在测试过程中发现并修复的关键错误。创建一个清晰的提交点是软件开发中的一个良好实践。

## 目标
将所有已修改的文件暂存，并使用一条清晰的提交信息创建一个新的 Git 提交，以保存当前的工作进度。

## 基本原理
通过标准的 `git add .` 命令暂存工作目录下的所有变更，然后使用 `git_commit` 命令并附上一个描述性的消息来创建一个原子性的提交。

## 标签
#comp/engine #comp/tests #scope/dx

---

## Script

### Acts 1: 暂存并提交所有变更

~~~~~act
git_add .
~~~~~

~~~~~act
git_commit
~~~~~
~~~~~message
fix(engine): Align engine tests with Git Object Storage backend

This commit addresses the test failures that arose after integrating the new Git Object Storage strategy.

Key changes include:
- Refactored `tests/test_engine.py` to use the `GitObjectHistoryReader/Writer` by default, adapting assertions to the new backend's behavior (e.g., checking Git refs instead of `.md` files).
- Fixed an `AttributeError` in `GitObjectHistoryWriter` where capturing a drift without a message would cause a crash.
- Updated the CLI's `_setup_engine` factory to correctly detect and inject the appropriate storage backend based on project state.
- Refactored `Engine` to fully delegate Git commit creation to the `HistoryWriter` interface, cleaning up duplicated logic.
~~~~~