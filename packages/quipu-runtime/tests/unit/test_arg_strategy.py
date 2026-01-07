import pytest
from pyquipu.runtime.executor import Executor


class TestArgStrategy:
    @pytest.fixture
    def executor(self, tmp_path):
        return Executor(root_dir=tmp_path, yolo=True)

    # --- 1. Hybrid Mode Tests ---

    def test_hybrid_mode_merge(self, executor):
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="hybrid")

        stmts = [{"act": "op inline_1", "contexts": ["block_1"]}]
        executor.execute(stmts)
        assert received_args == ["inline_1", "block_1"]

    def test_hybrid_mode_only_inline(self, executor):
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="hybrid")

        stmts = [{"act": "op inline_1", "contexts": []}]
        executor.execute(stmts)
        assert received_args == ["inline_1"]

    # --- 2. Exclusive Mode Tests (Formerly Smart) ---

    def test_exclusive_mode_inline_priority(self, executor):
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="exclusive")

        stmts = [{"act": "op inline_1 inline_2", "contexts": ["ignored_block"]}]
        executor.execute(stmts)
        # 块被忽略
        assert received_args == ["inline_1", "inline_2"]

    def test_exclusive_mode_fallback_to_block(self, executor):
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="exclusive")

        stmts = [{"act": "op", "contexts": ["valid_block"]}]
        executor.execute(stmts)
        assert received_args == ["valid_block"]

    # --- 3. Block Only Mode Tests ---

    def test_block_only_mode(self, executor):
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="block_only")

        stmts = [{"act": "op ignored_inline", "contexts": ["valid_block"]}]
        executor.execute(stmts)
        # 行内参数被丢弃
        assert received_args == ["valid_block"]

    def test_block_only_no_block(self, executor):
        received_args = []
        executor.register("op", lambda exc, args: received_args.extend(args), arg_mode="block_only")

        stmts = [{"act": "op ignored_inline", "contexts": []}]
        executor.execute(stmts)
        assert received_args == []

    # --- 4. Validation Tests ---

    def test_invalid_mode_registration(self, executor):
        with pytest.raises(ValueError):
            executor.register("op", lambda e, a: None, arg_mode="chaos_mode")
