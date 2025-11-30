import pytest
from pyquipu.runtime.executor import Executor


class TestArgStrategy:
    @pytest.fixture
    def executor(self, tmp_path):
        """创建一个干净的 Executor 用于测试参数逻辑"""
        return Executor(root_dir=tmp_path, yolo=True)

    # --- 1. Hybrid Mode Tests ---

    def test_hybrid_mode_merge(self, executor):
        """测试 Hybrid 模式：行内 + 块"""
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="hybrid")

        stmts = [{"act": "op inline_1", "contexts": ["block_1"]}]
        executor.execute(stmts)
        assert received_args == ["inline_1", "block_1"]

    def test_hybrid_mode_only_inline(self, executor):
        """测试 Hybrid 模式：仅行内"""
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="hybrid")

        stmts = [{"act": "op inline_1", "contexts": []}]
        executor.execute(stmts)
        assert received_args == ["inline_1"]

    # --- 2. Exclusive Mode Tests (Formerly Smart) ---

    def test_exclusive_mode_inline_priority(self, executor):
        """测试 Exclusive 模式：如果有行内参数，应忽略块"""
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="exclusive")

        stmts = [{"act": "op inline_1 inline_2", "contexts": ["ignored_block"]}]
        executor.execute(stmts)
        # 块被忽略
        assert received_args == ["inline_1", "inline_2"]

    def test_exclusive_mode_fallback_to_block(self, executor):
        """测试 Exclusive 模式：如果无行内参数，应使用块"""
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="exclusive")

        stmts = [{"act": "op", "contexts": ["valid_block"]}]
        executor.execute(stmts)
        assert received_args == ["valid_block"]

    # --- 3. Block Only Mode Tests ---

    def test_block_only_mode(self, executor):
        """测试 Block Only 模式：始终忽略行内参数"""
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="block_only")

        stmts = [{"act": "op ignored_inline", "contexts": ["valid_block"]}]
        executor.execute(stmts)
        # 行内参数被丢弃
        assert received_args == ["valid_block"]

    def test_block_only_no_block(self, executor):
        """测试 Block Only 模式：行内被忽略，且无块 -> 空参数"""
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="block_only")

        stmts = [{"act": "op ignored_inline", "contexts": []}]
        executor.execute(stmts)
        assert received_args == []

    # --- 4. Validation Tests ---

    def test_invalid_mode_registration(self, executor):
        """测试注册非法模式应报错"""
        with pytest.raises(ValueError):
            executor.register("op", lambda e, a: None, arg_mode="chaos_mode")
