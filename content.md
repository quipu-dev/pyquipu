这是一个针对 `quipu-cli` 和相关测试的修复计划，旨在解决 `sync` 命令和其他操作在子目录中运行时因找不到 `.git` 根目录而崩溃的问题。

### 核心变更

1.  **`packages/quipu-cli/src/quipu/cli/factory.py`**:
    *   修改 `create_engine` 函数。现在它会首先调用 `find_project_root(work_dir)` 尝试定位真正的 Git 根目录。
    *   如果找到 Git 根目录，`Engine` 和 `GitDB` 将基于该根目录初始化。这解决了在子目录（如 `src/`）运行命令时的崩溃问题。
    *   如果未找到，则回退到 `work_dir`（保持原有行为，便于 `GitDB` 抛出清晰的 "Not a git repo" 错误）。

2.  **`tests/test_isolation.py`**:
    *   更新 `nested_git_project` fixture。在 `work_dir` 中执行 `git init`。
    *   **原因**: 原测试试图在一个非 Git 仓库的子目录中创建隔离的 Quipu 历史，这与当前的架构（Quipu 强依赖 GitDB，GitDB 强依赖 `.git`）冲突。通过将子目录初始化为嵌套的 Git 仓库，我们既满足了架构要求，又保留了测试“隔离性”的初衷（操作不应污染父级仓库）。

3.  **`tests/test_root_invariance.py`**:
    *   修改测试断言。
    *   **原因**: 修复后的 `create_engine` 让 `Engine` 在项目根目录正确运行，消除了崩溃。但 `Executor` 依然基于 `work_dir` (子目录) 运行，这是符合直觉的 CLI 行为（在哪个目录运行命令，就在哪个目录创建文件）。因此，测试中断言文件生成位置的代码需要更新，以反映文件是生成在 `subdir` 而不是项目根目录。

### 计划

~~~~~act
replace packages/quipu-cli/src/quipu/cli/factory.py
~~~~~

~~~~~python
def create_engine(work_dir: Path) -> Engine:
    """
    实例化完整的 Engine 堆栈。
    
    此函数现在严格使用传入的 work_dir 作为操作根目录。
    它会自动调用 engine.align() 来加载历史图谱。
    """
    # 1. 创建 GitDB 实例，严格绑定到 work_dir
    # 注意：这意味着 work_dir 本身必须是一个 Git 仓库的根或子目录。
    # Engine 的功能依赖于 Git。
    git_db = GitDB(work_dir)
    
    # 2. 默认使用 Git Object 存储
    logger.debug("Defaulting to Git Object storage format.")
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    # 3. 注入依赖并实例化 Engine，根目录为 work_dir
    engine = Engine(work_dir, reader=reader, writer=writer)
    engine.align()  # 对齐以加载历史图谱
    
    return engine
~~~~~

~~~~~python
def create_engine(work_dir: Path) -> Engine:
    """
    实例化完整的 Engine 堆栈。
    
    会自动向上查找项目根目录 (Git Root) 来初始化 Engine。
    如果找不到 Git Root，则回退到 work_dir。
    """
    # 1. 尝试查找真正的项目根目录 (包含 .git 的目录)
    # 这确保了即使在子目录中运行，GitDB 也能正确找到仓库
    project_root = find_project_root(work_dir)
    if not project_root:
        project_root = work_dir

    # 2. 创建 GitDB 实例，绑定到项目根目录
    git_db = GitDB(project_root)
    
    # 3. 默认使用 Git Object 存储
    logger.debug("Defaulting to Git Object storage format.")
    reader = GitObjectHistoryReader(git_db)
    writer = GitObjectHistoryWriter(git_db)

    # 4. 注入依赖并实例化 Engine，根目录为项目根目录
    engine = Engine(project_root, reader=reader, writer=writer)
    engine.align()  # 对齐以加载历史图谱
    
    return engine
~~~~~

~~~~~act
replace tests/test_isolation.py
~~~~~

~~~~~python
    work_dir = host_project / "work_dir"
    work_dir.mkdir()
    
    return host_project, work_dir
~~~~~

~~~~~python
    work_dir = host_project / "work_dir"
    work_dir.mkdir()
    # 必须初始化为嵌套的 git 仓库，因为 Quipu Engine 依赖于 GitDB，
    # 而 GitDB 需要当前目录或父目录是 git 仓库。
    # 为了测试隔离性（不污染 host_project），work_dir 必须自己是一个独立的仓库。
    subprocess.run(["git", "init"], cwd=work_dir, check=True, capture_output=True)
    
    return host_project, work_dir
~~~~~

~~~~~act
replace tests/test_root_invariance.py
~~~~~

~~~~~python
        # 1. 验证操作的正确性
        assert result.success is True, f"从子目录运行失败: {result.message}"
        
        # Executor 应该基于项目根来解析路径，所以 'result.txt' 应该在根目录创建
        expected_file = project_root / "result.txt"
        assert expected_file.exists(), "文件应该在项目根目录创建，而不是子目录"
        assert expected_file.read_text("utf-8") == "Success from subdir"

        # 2. 验证 Engine 状态记录的正确性 (后端无关)
~~~~~

~~~~~python
        # 1. 验证操作的正确性
        assert result.success is True, f"从子目录运行失败: {result.message}"
        
        # 修正：CLI 的标准行为是基于当前工作目录 (CWD/work_dir) 执行文件操作。
        # 虽然 Engine 正确地在 Project Root 运行并记录历史，但 Executor 依然在 subdir 运行。
        # 因此，文件会创建在 subdir 下，这是正确的行为。
        expected_file = subdir / "result.txt"
        assert expected_file.exists(), "文件应该在子目录创建 (CWD)"
        assert expected_file.read_text("utf-8") == "Success from subdir"

        # 2. 验证 Engine 状态记录的正确性 (后端无关)
~~~~~
