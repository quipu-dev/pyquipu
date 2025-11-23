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