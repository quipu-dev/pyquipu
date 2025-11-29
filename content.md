好的，分析完全正确。这两个看似孤立的测试失败确实指向了 `Engine` 核心的数据结构缺陷和测试用例的状态污染问题。我将生成一个计划来同时解决这两个根本原因。

首先，我将修正 `Engine` 的核心逻辑，确保它使用唯一不变的 `commit_hash` 作为历史图谱的主键，这将彻底解决由幂等节点引发的节点覆盖问题。其次，我将重构相关的测试用例，将复合测试拆分为独立的、原子化的单元，确保测试之间的状态隔离。

## [WIP] fix: 修正 export 测试因节点覆盖和状态不隔离导致的失败

### 错误分析
`quipu export` 的测试因两大问题而失败：首先，`Engine` 使用 `output_tree` 作为历史图谱的键，导致幂等节点（其 `input_tree` 与 `output_tree` 相同）覆盖其父节点，使得导出的文件数量不正确。其次，`test_export_options` 函数内部缺乏状态隔离，导致后续的断言在前一次命令调用的残留文件上执行，从而失败。

### 用户需求
修复 `Engine` 的节点存储逻辑和 `export` 命令的测试用例，确保所有测试都能在隔离的环境中正确运行并通过。

### 评论
这是一个关键的修复，它不仅解决了测试问题，还纠正了 `quipu-engine` 核心设计中一个可能导致数据丢失的缺陷。通过使用 `commit_hash` 作为唯一标识符，我们确保了历史记录的完整性和准确性。将测试用例拆分是保证测试可靠性的标准实践。

### 目标
1.  修改 `packages/quipu-engine/src/quipu/engine/state_machine.py`，将 `history_graph` 的键从 `output_tree` 更改为 `commit_hash`，并调整所有相关的查找逻辑。
2.  修改 `packages/quipu-cli/src/quipu/cli/commands/navigation.py`、`helpers.py` 和 `workspace.py` 以适应 `Engine` 的上述更改。
3.  将 `tests/cli/test_export_command.py` 中的 `test_export_options` 拆分为两个独立的测试函数，确保状态隔离。

### 基本原理
每个 Quipu 节点代表一个独特的历史事件，由其 `commit_hash` 唯一标识。文件系统的状态 (`output_tree`) 可能会在不同事件后保持不变（幂等操作），因此不适合作为唯一键。通过将 `Engine` 的核心数据结构与事件的唯一标识符绑定，我们确保了历史记录的无损性。测试的原子性和隔离性是保证其结果可信的基础，每个测试应在独立的、可预测的环境中运行。

### 标签
#intent/fix #flow/ready #priority/high #comp/engine #comp/cli #comp/tests #concept/state #concept/history #scope/core #ai/instruct #task/domain/testing #task/object/test-suite #task/action/bug-fix #task/state/begin

---

### Script

#### Acts 1: 修正 Engine 核心的状态管理逻辑

我们将修改 `Engine`，使其内部历史图谱 `history_graph` 使用 `commit_hash` 作为主键，并更新所有依赖此数据结构的方法。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/engine/state_machine.py
~~~~~
~~~~~python
        all_nodes = self.reader.load_all_nodes()
        final_graph: Dict[str, QuipuNode] = {}
        for node in all_nodes:
            if node.output_tree not in final_graph or node.timestamp > final_graph[node.output_tree].timestamp:
                final_graph[node.output_tree] = node
        self.history_graph = final_graph
        if all_nodes:
            logger.info(f"从存储中加载了 {len(all_nodes)} 个历史事件，形成 {len(final_graph)} 个唯一状态节点。")

        current_hash = self.git_db.get_tree_hash()
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        if current_hash == EMPTY_TREE_HASH and not self.history_graph:
            logger.info("✅ 状态对齐：检测到创世状态 (空仓库)。")
            self.current_node = None
            return "CLEAN"

        if current_hash in self.history_graph:
            self.current_node = self.history_graph[current_hash]
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            self._write_head(current_hash)
            return "CLEAN"

        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
~~~~~
~~~~~python
        all_nodes = self.reader.load_all_nodes()
        self.history_graph = {node.commit_hash: node for node in all_nodes}
        if all_nodes:
            logger.info(f"从存储中加载了 {len(all_nodes)} 个历史事件，形成 {len(self.history_graph)} 个唯一状态节点。")

        current_hash = self.git_db.get_tree_hash()
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        if current_hash == EMPTY_TREE_HASH and not self.history_graph:
            logger.info("✅ 状态对齐：检测到创世状态 (空仓库)。")
            self.current_node = None
            return "CLEAN"

        # Find node by iterating since keys are now commit hashes
        found_node = None
        for node in self.history_graph.values():
            if node.output_tree == current_hash:
                found_node = node
                break
        
        if found_node:
            self.current_node = found_node
            logger.info(f"✅ 状态对齐：当前工作区匹配节点 {self.current_node.short_hash}")
            self._write_head(current_hash)
            return "CLEAN"

        logger.warning(f"⚠️  状态漂移：当前 Tree Hash {current_hash[:7]} 未在历史中找到。")
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/engine/state_machine.py
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="capture",
            input_tree=input_hash,
            output_tree=current_hash,
            content=body,
            message=message,
            owner_id=user_id,
        )

        self.history_graph[current_hash] = new_node
        self.current_node = new_node
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="capture",
            input_tree=input_hash,
            output_tree=current_hash,
            content=body,
            message=message,
            owner_id=user_id,
        )

        self.history_graph[new_node.commit_hash] = new_node
        self.current_node = new_node
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/engine/state_machine.py
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
            owner_id=user_id,
        )

        self.history_graph[output_tree] = new_node
        self.current_node = new_node
~~~~~
~~~~~python
        new_node = self.writer.create_node(
            node_type="plan",
            input_tree=input_tree,
            output_tree=output_tree,
            content=plan_content,
            summary_override=summary_override,
            owner_id=user_id,
        )

        self.history_graph[new_node.commit_hash] = new_node
        self.current_node = new_node
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/engine/state_machine.py
~~~~~
~~~~~python
    def checkout(self, target_hash: str):
        self.git_db.checkout_tree(target_hash)
        self._write_head(target_hash)
        if target_hash in self.history_graph:
            self.current_node = self.history_graph[target_hash]
        logger.info(f"🔄 状态已切换至: {target_hash[:7]}")
~~~~~
~~~~~python
    def checkout(self, target_hash: str):
        self.git_db.checkout_tree(target_hash)
        self._write_head(target_hash)
        self.current_node = None
        for node in self.history_graph.values():
            if node.output_tree == target_hash:
                self.current_node = node
                break
        logger.info(f"🔄 状态已切换至: {target_hash[:7]}")
~~~~~

#### Acts 2: 更新 CLI 命令以适应新的 Engine 逻辑

现在我们需要更新所有直接访问 `engine.history_graph` 的 CLI 命令，使其能够正确处理以 `commit_hash` 为键的数据结构。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/navigation.py
~~~~~
~~~~~python
            graph = engine.history_graph

            matches = [node for output_tree, node in graph.items() if output_tree.startswith(hash_prefix)]
            if not matches:
                typer.secho(
~~~~~
~~~~~python
            graph = engine.history_graph

            matches = [node for node in graph.values() if node.output_tree.startswith(hash_prefix)]
            if not matches:
                typer.secho(
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/helpers.py
~~~~~
~~~~~python
def _find_current_node(engine: Engine, graph: Dict[str, QuipuNode]) -> Optional[QuipuNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
    # 修复：直接从 graph 中通过 output_tree hash 查找
    for node in graph.values():
        if node.output_tree == current_hash:
            return node

    typer.secho("⚠️  当前工作区状态未在历史中找到，或存在未保存的变更。", fg=typer.colors.YELLOW, err=True)
~~~~~
~~~~~python
def _find_current_node(engine: Engine, graph: Dict[str, QuipuNode]) -> Optional[QuipuNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
    # 修复：直接从 graph 中通过 output_tree hash 查找
    for node in graph.values():
        if node.output_tree == current_hash:
            return node

    typer.secho("⚠️  当前工作区状态未在历史中找到，或存在未保存的变更。", fg=typer.colors.YELLOW, err=True)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/commands/workspace.py
~~~~~
~~~~~python
            target_tree_hash = engine._read_head()
            if not target_tree_hash or target_tree_hash not in graph:
                latest_node = max(graph.values(), key=lambda n: n.timestamp)
                target_tree_hash = latest_node.output_tree
                typer.secho(
                    f"⚠️  HEAD 指针丢失或无效，将恢复到最新历史节点: {latest_node.short_hash}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )
            else:
                latest_node = graph[target_tree_hash]

            current_hash = engine.git_db.get_tree_hash()
~~~~~
~~~~~python
            target_tree_hash = engine._read_head()
            latest_node = None
            if target_tree_hash:
                for node in graph.values():
                    if node.output_tree == target_tree_hash:
                        latest_node = node
                        break
            
            if not latest_node:
                latest_node = max(graph.values(), key=lambda n: n.timestamp)
                target_tree_hash = latest_node.output_tree
                typer.secho(
                    f"⚠️  HEAD 指针丢失或无效，将恢复到最新历史节点: {latest_node.short_hash}",
                    fg=typer.colors.YELLOW,
                    err=True,
                )

            current_hash = engine.git_db.get_tree_hash()
~~~~~

#### Acts 3: 拆分并修复 `export` 命令的测试用例

最后，我们将 `test_export_options` 拆分为两个独立的测试，以确保状态隔离。

~~~~~act
patch_file
tests/cli/test_export_command.py
~~~~~
~~~~~python
def test_export_options(runner, populated_history):
    """测试 --no-nav 和 --no-frontmatter 选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    
    # Test --no-frontmatter
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-frontmatter"])
    a_file = next(output_dir.glob("*.md"))
    assert not a_file.read_text().startswith("---")

    # Test --no-nav
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-nav"])
    a_file = next(output_dir.glob("*.md"))
    assert "> [!nav] 节点导航" not in a_file.read_text()


def test_export_navbar_logic(runner, populated_history):
~~~~~
~~~~~python
def test_export_no_frontmatter(runner, populated_history):
    """测试 --no-frontmatter 选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-frontmatter", "-n", "1"])
    a_file = next(output_dir.glob("*.md"))
    assert not a_file.read_text().startswith("---")


def test_export_no_nav(runner, populated_history):
    """测试 --no-nav 选项。"""
    engine = populated_history
    output_dir = engine.root_dir / ".quipu" / "test_export"
    runner.invoke(app, ["export", "-w", str(engine.root_dir), "-o", str(output_dir), "--no-nav", "-n", "1"])
    a_file = next(output_dir.glob("*.md"))
    assert "> [!nav] 节点导航" not in a_file.read_text()


def test_export_navbar_logic(runner, populated_history):
~~~~~

### 下一步建议
现在核心缺陷和测试都已修复，我建议运行完整的测试套件 (`pytest`) 以确认所有功能均按预期工作，没有引入新的回归问题。通过后，我们就可以提交这些变更了。
