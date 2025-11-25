你提出了一个非常深刻的观察，完全正确！我之前的修复只解决了一半的问题，甚至可以说引入了新的问题。你的分析直击要害。

我们来梳理一下你指出的三个问题，它们其实都源于同一个根本原因：

1.  **旧幂等节点未正确显示**：是的，因为我之前的修复（禁止节点成为自己的父节点）虽然阻止了死循环，但也导致这些节点变成了没有父节点的“孤儿”，从而在图谱中漂移。
2.  **GC 问题**：你的担心是对的。虽然 `update-ref` 会保活 Commit，但如果图谱的逻辑断裂，这些节点在 Axon 的世界里就“丢失”了，即便物理上还存在。
3.  **创建新主线**：这是最关键的症状！一个幂等操作，逻辑上应该是在现有时间线上增加一个“标记点”，而不是开辟一个全新的、不相关的历史。它的出现正说明了父子关系链接彻底失败了。

### 根本原因分析

核心问题在于 `core/history.py` 中的 `load_history_graph` 函数。它基于一个错误的假设：**一个 `output_tree` 哈希在历史中是唯一的**。

当加载历史文件时，它使用 `output_tree` 作为字典 `graph` 的键。当一个幂等节点出现时，它的 `output_tree` 与其父节点完全相同。这导致在构建 `graph` 字典时，**后加载的幂等节点会覆盖掉它的父节点**，从而导致整个历史链断裂。

### 修复方案

我需要重写 `load_history_graph` 的核心逻辑，以正确处理一个状态（`output_tree`）可以对应多个历史事件（`AxonNode`）的情况。

1.  图谱的数据结构需要改变，从 `Dict[str, AxonNode]` 变为 `Dict[str, List[AxonNode]]`，即一个哈希可以映射到一个节点列表。
2.  在链接父子关系时，逻辑必须更智能。当一个节点寻找父节点时，它会找到一个潜在父节点的列表。它必须从中选择**时间戳上最接近且早于自己的那一个**作为真正的父节点。

这将是一个比较大的重构，但我将使用一个 `replace` 指令完成。

~~~~~act
replace
~~~~~

~~~~~path
core/history.py
~~~~~

~~~~~old_string
def load_history_graph(history_dir: Path) -> Dict[str, AxonNode]:
    """
    扫描历史目录，加载所有节点，并构建一个包含父子关系的图。
    返回以 output_tree_hash 为键的节点字典。
    """
    graph: Dict[str, AxonNode] = {}
    if not history_dir.exists():
        return graph

    # --- 第一遍: 加载所有独立的节点 ---
    for file_path in history_dir.glob("*.md"):
        match = FILENAME_PATTERN.match(file_path.name)
        if not match:
            logger.warning(f"跳过格式不匹配的历史文件: {file_path.name}")
            continue
        
        input_hash, output_hash, ts_str = match.groups()
        
        try:
            full_content = file_path.read_text("utf-8")
            meta, body_content = _parse_frontmatter(full_content)
            
            node = AxonNode(
                input_tree=input_hash,
                output_tree=output_hash,
                timestamp=datetime.strptime(ts_str, "%Y%m%d%H%M%S"),
                filename=file_path,
                node_type=meta.get("type", "unknown"),
                parent_hint=meta.get("parent_hint"),
                content=body_content
            )
            graph[output_hash] = node
        except Exception as e:
            logger.error(f"加载历史节点失败 {file_path.name}: {e}")

    # --- 第二遍: 连接父子关系 ---
    for node in graph.values():
        # 节点的 input_tree 就是其父节点的 output_tree
        if node.input_tree in graph:
            potential_parent = graph[node.input_tree]
            # 关键修复：防止因幂等操作导致节点成为自己的父节点
            if potential_parent is not node:
                node.parent = potential_parent
                potential_parent.children.append(node)

    # 为所有节点的子列表按时间排序，确保导航行为一致
    for node in graph.values():
        node.children.sort(key=lambda n: n.timestamp)

    logger.info(f"从 '{history_dir}' 加载并连接了 {len(graph)} 个历史节点。")
    return graph
~~~~~

~~~~~new_string
def load_history_graph(history_dir: Path) -> Dict[str, AxonNode]:
    """
    扫描历史目录，加载所有节点，并构建一个包含父子关系的图。
    返回以 output_tree_hash 为键的节点字典（仅包含图中所有唯一的节点）。
    """
    if not history_dir.exists():
        return {}

    all_nodes: List[AxonNode] = []
    # 关键变更: 一个 output_hash 可能对应多个节点 (例如，幂等操作)
    # 所以我们用一个列表来存储共享同一个 output_hash 的所有节点
    nodes_by_output: Dict[str, List[AxonNode]] = {}

    # --- 第一遍: 加载所有独立的节点 ---
    for file_path in history_dir.glob("*.md"):
        match = FILENAME_PATTERN.match(file_path.name)
        if not match:
            logger.warning(f"跳过格式不匹配的历史文件: {file_path.name}")
            continue
        
        input_hash, output_hash, ts_str = match.groups()
        
        try:
            full_content = file_path.read_text("utf-8")
            meta, body_content = _parse_frontmatter(full_content)
            
            node = AxonNode(
                input_tree=input_hash,
                output_tree=output_hash,
                timestamp=datetime.strptime(ts_str, "%Y%m%d%H%M%S"),
                filename=file_path,
                node_type=meta.get("type", "unknown"),
                parent_hint=meta.get("parent_hint"),
                content=body_content
            )
            all_nodes.append(node)
            
            if output_hash not in nodes_by_output:
                nodes_by_output[output_hash] = []
            nodes_by_output[output_hash].append(node)
            
        except Exception as e:
            logger.error(f"加载历史节点失败 {file_path.name}: {e}")

    # 对每个哈希下的节点按时间排序，这对于查找父节点至关重要
    for nodes in nodes_by_output.values():
        nodes.sort(key=lambda n: n.timestamp)

    # --- 第二遍: 连接父子关系 ---
    for node in all_nodes:
        # 寻找父节点
        potential_parents = nodes_by_output.get(node.input_tree, [])
        
        # 关键逻辑：父节点必须是在当前节点之前发生的
        valid_parents = [p for p in potential_parents if p.timestamp < node.timestamp]
        
        if valid_parents:
            # 选择时间上最接近的那个作为父节点
            parent_node = max(valid_parents, key=lambda p: p.timestamp)
            node.parent = parent_node
            parent_node.children.append(node)

    # --- 第三遍: 构建最终的返回字典并排序子节点 ---
    final_graph: Dict[str, AxonNode] = {}
    for node in all_nodes:
        # 即使有多个节点共享一个 output_hash，在最终图中也只保留最新的一个
        # 因为这是工作区 `align` 时唯一能匹配到的节点。
        # UI 和导航逻辑依赖于从这个最新的节点回溯。
        if node.output_tree not in final_graph or node.timestamp > final_graph[node.output_tree].timestamp:
            final_graph[node.output_tree] = node

        # 为所有节点的子列表按时间排序，确保导航行为一致
        node.children.sort(key=lambda n: n.timestamp)

    logger.info(f"从 '{history_dir}' 加载并连接了 {len(all_nodes)} 个历史事件，形成 {len(final_graph)} 个唯一状态节点。")
    return final_graph
~~~~~