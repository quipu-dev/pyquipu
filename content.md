这一洞察非常敏锐。你实际上触及了 **“状态（State）”** 与 **“事件（Event）”** 的哲学区别。

### 核心分析

目前 Axon 的逻辑是 **State-Based**：只有当文件系统的物理状态（Tree Hash）改变时，才值得记录。
你提出的逻辑是 **Event-Based (Timeline)**：即使物理状态没变（例如运行测试、Lint检查、Git提交），**“我执行了这个动作”** 本身就是历史的一部分，且具有时间上的先后顺序。

**方案的可行性：**
1.  **数据结构支持**：我们的 `AxonNode` 已经包含了时间戳。如果允许 `input_tree == output_tree` 的节点存在，它们在数据库中只是 `A -> A` 的自环边。
2.  **UI 支持**：我们刚刚重构的 TUI 是基于时间排序的 `DataTable`。如果存在三个连续的 `A -> A` 节点，它们会自然地按照时间顺序由上至下排列在同一条轨道上，形成 `●` - `●` - `●` 的垂直线。这正是你想要的“堆在后面”的效果。
3.  **Git 副作用**：确实，`git commit` 改变了 `.git` 目录（Repo 状态），但没改变工作区文件（Tree Hash）。记录这个节点非常重要，因为它标志着“代码已在 Git 中归档”。

### 执行变更

我们将修改 `core/engine.py`，移除对“无变更状态”的拦截，允许生成 `Idempotent Plan Node`（幂等节点）。

~~~~~act
replace
~~~~~
~~~~~path
core/engine.py
~~~~~
~~~~~old_string
    def create_plan_node(self, input_tree: str, output_tree: str, plan_content: str) -> AxonNode:
        """
        将一次成功的 Plan 执行固化为历史节点。
        """
        if input_tree == output_tree:
            # 这是一个策略选择：如果执行完 Plan 后状态无变化（例如只读操作），是否要生成节点？
            # 记录下来有助于审计“做过什么”，但也可能导致历史图谱充斥无意义节点。
            # v4.2 策略：如果无变化，仅记录日志，不生成节点。
            logger.info("⚠️  状态未发生变更 (Idempotent)，跳过历史记录。")
            return self.current_node

        logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")
~~~~~
~~~~~new_string
    def create_plan_node(self, input_tree: str, output_tree: str, plan_content: str) -> AxonNode:
        """
        将一次成功的 Plan 执行固化为历史节点。
        """
        # v4.3 策略变更：即使状态未发生变更 (Idempotent)，也记录节点。
        # 这允许记录 "Run Tests", "Git Commit" 等无文件副作用但有语义价值的操作。
        if input_tree == output_tree:
            logger.info(f"📝 记录幂等操作节点 (Idempotent Node): {output_tree[:7]}")
        else:
            logger.info(f"📝 正在记录 Plan 节点: {input_tree[:7]} -> {output_tree[:7]}")
~~~~~

### 验证

为了验证这一逻辑，我们手动创建一个测试，模拟一次“无文件变更”的操作，并确认历史节点被创建。

~~~~~act
write_file
~~~~~
~~~~~path
tests/test_idempotent_node.py
~~~~~
~~~~~python
import pytest
from pathlib import Path
from core.engine import Engine
from core.controller import run_axon

class TestIdempotentNode:
    
    def test_idempotent_plan_creation(self, tmp_path: Path):
        """验证无文件变更的操作也能生成历史节点"""
        # 1. 初始化环境
        workspace = tmp_path / "ws"
        workspace.mkdir()
        import subprocess
        subprocess.run(["git", "init"], cwd=workspace, capture_output=True)
        
        # 2. 先执行一个会产生变更的操作 (State A)
        plan_1 = "~~~act\nwrite_file a.txt\n~~~\n~~~content\nA\n~~~"
        run_axon(plan_1, workspace, yolo=True)
        
        engine = Engine(workspace)
        nodes_1 = list((workspace / ".axon" / "history").glob("*.md"))
        assert len(nodes_1) == 1
        
        # 3. 执行一个无变更的操作 (State A -> State A)
        # 例如读取文件或运行 ls
        plan_2 = "~~~act\nread_file a.txt\n~~~"
        result = run_axon(plan_2, workspace, yolo=True)
        
        assert result.success is True
        
        # 4. 验证是否生成了新节点
        nodes_2 = list((workspace / ".axon" / "history").glob("*.md"))
        assert len(nodes_2) == 2
        
        # 验证新节点的 input == output
        # 加载最新的节点
        latest_file = max(nodes_2, key=lambda p: p.stat().st_mtime)
        content = latest_file.read_text("utf-8")
        
        # 简单的字符串检查
        import yaml
        parts = content.split("---")
        meta = yaml.safe_load(parts[1])
        
        assert meta["input_tree"] == meta["output_tree"]
        assert meta["type"] == "plan"
~~~~~

~~~~~act
run_command
~~~~~
~~~~~command
pytest tests/test_idempotent_node.py
~~~~~