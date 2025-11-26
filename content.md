# 为什么在 test_engine.py 中不使用 InMemoryDB

你的判断是正确的：**在你引用的那行代码中，使用的并不是 `InMemoryDB`，而是真实的 `GitDB`。**

让我来解释一下为什么这是正确的，以及我们的测试策略是如何分层的。

### 1. 测试分层：集成测试 vs. 单元/逻辑测试

通过上一步的重构，我们现在拥有了两种测试 `Engine` 的能力：

*   **集成测试 (Integration Tests)**:
    *   **目的**: 验证 `Engine` 与其**真实依赖** (即 `GitDB` 和物理上的 Git 仓库) 之间的协作是否正确。
    *   **实现**: 使用 `GitDB` 作为后端。这些测试会真实地创建 `.git` 目录，调用 `git` 命令，读写磁盘文件。
    *   **例子**: `tests/test_engine.py`, `tests/test_navigation.py` 等**原有的测试文件**都属于这一类。它们速度较慢，但对于确保端到端功能的正确性至关重要。

*   **单元/逻辑测试 (Unit/Logic Tests)**:
    *   **目的**: 在**完全隔离**的环境中，快速验证 `Engine` 的**内部业务逻辑**是否正确，而无需关心底层的存储实现。
    *   **实现**: 使用我们新创建的 `InMemoryDB` 作为后端。这些测试运行在内存中，速度极快，且不受外部环境影响。
    *   **例子**: 我们为此新创建了 `tests/test_engine_memory.py` 文件。

### 2. 你引用的代码属于“集成测试”

你引用的代码片段来自 `tests/test_engine.py`：

```python
# tests/test_engine.py

@pytest.fixture
def engine_setup(tmp_path):
    # ...
    git_db = GitDB(repo_path)  # <-- 创建真实的 GitDB
    # ...
    engine = Engine(repo_path, db=git_db, ...) # <-- 注入真实的 GitDB
    return engine, repo_path

class TestPersistentIgnores:
    def test_sync_creates_file_if_not_exists(self, engine_setup):
        engine, repo_path = engine_setup
        # ...
        # 重新初始化 Engine 以触发同步逻辑
        engine = Engine(repo_path, db=engine.git_db, ...) # <-- 这里使用的是 fixture 提供的真实 git_db
```

这里的逻辑是完全正确的：

1.  `engine_setup` fixture 创建了一个**真实的** `GitDB` 实例。
2.  `TestPersistentIgnores` 测试的目的是验证 `_sync_persistent_ignores` 方法，这个方法需要向真实的 `.git/info/exclude` 文件写入内容。
3.  因此，当它重新实例化 `Engine` 时，它**必须**继续使用那个真实的 `git_db` 实例，否则测试就失去了意义。

### 3. `InMemoryDB` 在哪里被使用？

`InMemoryDB` 在我们新创建的 `tests/test_engine_memory.py` 文件中，由一个名为 `memory_engine` 的新 fixture 提供：

```python
# tests/test_engine_memory.py

@pytest.fixture
def memory_engine(tmp_path: Path) -> Engine:
    """创建一个使用完整内存后端的 Engine 实例。"""
    db = InMemoryDB()  # <-- 在这里创建 InMemoryDB
    history_manager = InMemoryHistoryManager(db)
    engine = Engine(root_dir=tmp_path, db=db, reader=history_manager, writer=history_manager)
    return engine

class TestEngineWithMemoryBackend:
    def test_align_clean_genesis(self, memory_engine: Engine):
        # 这个测试用例接收的是 memory_engine fixture
        # 因此它内部所有的操作都是在内存中完成的
        status = memory_engine.align()
        assert status == "CLEAN"
```

### 总结

我们的测试策略是：

*   对于需要验证**与 Git 和文件系统交互**的功能 (如 `sync_persistent_ignores`, 真实的文件 `checkout`)，我们使用**集成测试**和 `GitDB`。
*   对于验证 `Engine` 的**核心状态管理逻辑** (如图谱构建、状态切换、漂移检测的内部逻辑)，我们优先使用**单元测试**和 `InMemoryDB` 以追求速度和稳定性。

所以，你的观察非常敏锐且准确。你看到的代码确实没有使用 `InMemoryDB`，因为它所属的测试场景要求它必须使用 `GitDB`。

```act
end
```
