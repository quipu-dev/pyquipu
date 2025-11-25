### Acts 1: 提交时序性导航功能

将所有已修改和新建的文件添加到暂存区，并创建一个内容详尽的提交。

~~~~~act
git_add
~~~~~

~~~~~text
packages/quipu-engine/src/quipu/core/state_machine.py
packages/quipu-cli/src/quipu/cli/main.py
tests/test_integration_v2.py
tests/test_navigation.py
~~~~~

~~~~~act
git_commit
~~~~~

~~~~~text
feat(navigation): 实现时序性 back/forward 导航功能

本提交引入了类似浏览器的时序性导航功能，以补充现有的基于图谱结构的导航。

核心变更：

1.  **新命令**:
    *   `quipu back`: 导航到上一个访问过的状态。
    *   `quipu forward`: 在 `back` 操作后，导航回之前的状态。

2.  **Engine 增强**:
    *   在 `.quipu/` 目录下引入 `nav_log` (访问历史) 和 `nav_ptr` (当前指针) 文件来持久化导航状态。
    *   `Engine` 类新增 `visit`, `back`, `forward` 方法，封装了导航历史的管理逻辑，包括在新的访问发生时正确截断旧的“前进”历史。

3.  **命令集成**:
    *   将所有改变工作区状态的命令 (`checkout`, `discard`, `undo`, `redo`, `prev`, `next`, `save`, `run`) 全部接入新的 `engine.visit()` 方法，确保所有用户发起的导航和修改操作都能被记录在时序历史中。

4.  **测试**:
    *   新增了 `tests/test_navigation.py`，包含针对 Engine 逻辑的单元测试和针对 CLI 命令的集成测试，确保了功能的健壮性。
~~~~~