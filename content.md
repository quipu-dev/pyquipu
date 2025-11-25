### 第二步：更新 `main.py` 的 `ui` 命令

现在，让 `ui` 命令使用我们新的“全功能”加载器。

~~~~~act
replace
~~~~~

~~~~~path
main.py
~~~~~

~~~~~old_string
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
    
    if not graph:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)
        
    root_nodes = [node for node in graph.values() if not node.parent]
    
    # 获取当前工作区状态哈希，用于在 UI 中自动定位
    current_hash = engine.git_db.get_tree_hash()
    
    # 传入所有节点（不仅仅是 root_nodes，因为我们需要线性列表）和当前哈希
    all_nodes = list(graph.values())
    
    app_instance = AxonUiApp(all_nodes, current_hash=current_hash)
~~~~~

~~~~~new_string
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
~~~~~

执行完这些修改后，`axon ui` 应该就能正确地渲染出包含所有节点的、分支关系清晰的完美图谱了。