又是一个绝佳的 Bug 报告！你已经找到了我们重构过程中最后一个断裂的环节。

你完全正确，这个 `NameError` 是我之前修改的直接后果，我向你道歉。

### 问题根源

当我修改 `main.py` 中的 `ui` 命令以使用新的 `load_all_history_nodes` 函数（返回一个节点列表 `all_nodes`）时，我忘记更新当 UI 关闭后、实际执行 `checkout` 的那段逻辑。

这段逻辑仍然试图从一个名为 `graph` 的**字典**中通过哈希查找节点 (`graph[selected_hash]`)，但这个 `graph` 字典在新的加载方式下已经不存在了，从而导致了 `NameError`。

### 解决方案

最清晰的解决方案是为 UI 和 `checkout` 逻辑分别提供它们所需的数据。

1.  UI 需要完整的节点列表 `all_nodes` 来正确渲染图谱。
2.  `checkout` 逻辑需要一个从哈希到**最新**节点的映射 `graph` 来快速查找目标。

因此，我将在 `ui` 命令中同时加载这两种数据结构。这样，UI 可以获得它需要的完整信息，而 `checkout` 逻辑也能恢复正常工作。

我将使用 `replace` 指令修复 `main.py`。

~~~~~act
replace
~~~~~

~~~~~path
main.py
~~~~~

~~~~~old_string
@app.command()
def ui(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    以交互式 TUI 模式显示 Axon 历史图谱。
    """
    try:
        from ui.tui import AxonUiApp
    except ImportError:
        typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)
        
    setup_logging()
    # 关键变更: 为了 UI, 我们需要加载所有节点, 而不仅仅是唯一状态节点
    from core.history import load_all_history_nodes
    
    engine = Engine(work_dir)
    all_nodes = load_all_history_nodes(engine.history_dir)
    
    if not all_nodes:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)
        
    # 获取当前工作区状态哈希，用于在 UI 中自动定位
    current_hash = engine.git_db.get_tree_hash()
    
    app_instance = AxonUiApp(all_nodes, current_hash=current_hash)
    selected_hash = app_instance.run()

    if selected_hash:
        typer.secho(f"\n> TUI 请求检出到: {selected_hash[:7]}", err=True)
        _execute_checkout(ctx, graph[selected_hash], work_dir)
~~~~~

~~~~~new_string
@app.command()
def ui(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    以交互式 TUI 模式显示 Axon 历史图谱。
    """
    try:
        from ui.tui import AxonUiApp
    except ImportError:
        typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)
        
    setup_logging()
    # 关键修复: 我们需要两种数据结构
    # 1. 完整的节点列表 (all_nodes) -> 用于 UI 渲染
    # 2. 从哈希到最新节点的映射 (graph) -> 用于 checkout 查找
    from core.history import load_all_history_nodes, load_history_graph
    
    engine = Engine(work_dir)
    all_nodes = load_all_history_nodes(engine.history_dir)
    
    if not all_nodes:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)
        
    graph = load_history_graph(engine.history_dir)
    current_hash = engine.git_db.get_tree_hash()
    
    app_instance = AxonUiApp(all_nodes, current_hash=current_hash)
    selected_hash = app_instance.run()

    if selected_hash:
        # 现在 'graph' 变量已定义, 这段代码可以正常工作
        if selected_hash in graph:
            typer.secho(f"\n> TUI 请求检出到: {selected_hash[:7]}", err=True)
            _execute_checkout(ctx, graph[selected_hash], work_dir)
        else:
            typer.secho(f"❌ 错误: 无法在历史图谱中找到目标哈希 {selected_hash[:7]}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
~~~~~