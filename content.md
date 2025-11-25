# fix-test: Enforce strict work_dir isolation to prevent test environment leakage

## 用户需求
在运行 `pytest` 时，测试生成的历史记录错误地写入了主开发项目 (`pyquipu/`) 的 `.quipu` 目录，污染了开发环境。这是因为系统在执行时，即使被告知在一个临时的 `work_dir` 中操作，也会自动向上查找并切换到包含 `.git` 的项目根目录。

## 评论
这是一个严重的系统性缺陷，破坏了环境隔离的基本原则，降低了系统的可预测性和作为开发工具的可靠性。必须从根本上修正这种“过于智能”的行为，确保所有状态操作严格限定在用户指定的 `work_dir` 内。

## 目标
1.  修改 `quipu-cli` 的 `factory` 和 `controller`，确保 `Engine` 和 `Executor` 的操作根目录严格绑定到 `work_dir` 参数。
2.  将自动发现的 `project_root` 的作用域限定为仅用于加载项目级插件，使其不再影响核心的状态读写操作。
3.  创建一个新的隔离测试 (`test_isolation.py`)，专门用于验证在嵌套的 Git 仓库中运行时，`quipu` 能够正确地在指定的子目录中创建历史，而不是泄漏到父目录。

## 基本原理
本次修复的核心是分离两个概念：
1.  **操作边界 (`work_dir`)**: 用户通过 `-w` 参数指定的目录，是所有文件读写和状态记录必须被严格限制在其中的“沙盒”。
2.  **上下文根 (`project_root`)**: 一个可选的、通过向上查找 `.git` 发现的目录，其唯一作用是为插件加载器提供一个寻找项目级 `.quipu/acts` 插件的起点。

通过修改 `controller` 和 `factory`，我们将确保 `Engine` 和 `Executor` 实例在创建时只接收 `work_dir`，而 `find_project_root` 的结果仅被传递给插件加载逻辑，从而从架构层面根除环境泄漏的可能性。

## 标签
#comp/engine #comp/cli #comp/tests #scope/core #scope/dx #fix

---

## Script

### Acts 1: 简化 Engine 工厂，强制使用 work_dir

我们首先修改 `create_engine` 函数，移除其自动解析根目录的逻辑，使其严格遵守传入的 `work_dir`。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/factory.py
~~~~~

~~~~~python
import logging
from pathlib import Path
from typing import Optional

from quipu.core.state_machine import Engine

from quipu.core.git_object_storage import GitObjectHistoryReader, GitObjectHistoryWriter
from quipu.core.git_db import GitDB

logger = logging.getLogger(__name__)

def find_project_root(start_path: Path) -> Optional[Path]:
    """向上递归查找包含 .git 的目录作为项目根目录"""
    try:
        current = start_path.resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                return parent
    except Exception:
        pass
    return None

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

### Acts 2: 调整 Controller，分离操作边界与插件上下文

现在，我们在 `run_quipu` 控制器中明确区分 `work_dir` (用于 `Engine` 和 `Executor`) 和 `project_root` (仅用于插件加载)。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/controller.py
~~~~~

~~~~~python
import logging
import os
import sys
from pathlib import Path
from typing import Optional

from quipu.core.result import QuipuResult
from quipu.core.executor import Executor, ExecutionError
from quipu.core.exceptions import ExecutionError as CoreExecutionError
from quipu.core.parser import get_parser, detect_best_parser
from quipu.core.plugin_loader import load_plugins

# 从配置导入
from .config import PROJECT_ROOT
from .factory import find_project_root, create_engine
from quipu.acts import register_core_acts

logger = logging.getLogger(__name__)

def _load_extra_plugins(executor: Executor, work_dir: Path):
    """
    按照层级顺序加载外部插件，高优先级会覆盖低优先级。
    优先级顺序: Project > Env > Home
    """
    plugin_sources = []
    
    # 优先级由低到高添加，后面的会覆盖前面的
    # 1. User Home (Lowest priority)
    home_acts = Path.home() / ".quipu" / "acts"
    plugin_sources.append(("🏠 Global", home_acts))

    # 2. Config / Env
    env_path = os.getenv("AXON_EXTRA_ACTS_DIR")
    if env_path:
        plugin_sources.append(("🔧 Env", Path(env_path)))
    
    # 3. Project Root (Highest priority)
    # 仅在此处使用 find_project_root，且仅用于加载插件
    project_root_for_plugins = find_project_root(work_dir)
    if project_root_for_plugins:
        proj_acts = project_root_for_plugins / ".quipu" / "acts"
        plugin_sources.append(("📦 Project", proj_acts))

    seen_paths = set()
    for label, path in plugin_sources:
        if not path.exists() or not path.is_dir():
            continue
        
        resolved_path = path.resolve()
        if resolved_path in seen_paths:
            continue
        
        load_plugins(executor, path)
        seen_paths.add(resolved_path)

def run_quipu(
    content: str,
    work_dir: Path,
    parser_name: str = "auto",
    yolo: bool = False
) -> QuipuResult:
    """
    Axon 核心业务逻辑入口。
    
    负责协调 Engine (状态), Parser (解析), Executor (执行) 三者的工作。
    任何异常都会被捕获并转化为失败的 QuipuResult。
    """
    try:
        # --- Phase 1: Engine Initialization & Perception ---
        # 使用工厂创建 Engine，严格在 work_dir 中操作
        engine = create_engine(work_dir)
        
        logger.info(f"Operation boundary set to: {work_dir}")
        
        # --- Phase 2: Decision (Lazy Capture) ---
        current_hash = engine.git_db.get_tree_hash()
        
        # 判断是否 Dirty/Orphan
        # 1. 正常 Clean: current_node 存在且与当前 hash 一致
        is_node_clean = (engine.current_node is not None) and (engine.current_node.output_tree == current_hash)
        
        # 2. 创世 Clean: 历史为空 且 当前是空树 (即没有任何文件被追踪)
        EMPTY_TREE_HASH = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
        is_genesis_clean = (not engine.history_graph) and (current_hash == EMPTY_TREE_HASH)
        
        is_clean = is_node_clean or is_genesis_clean
        
        if not is_clean:
            # 如果环境有漂移（或全新项目且非空），先生成一个 Capture 节点
            # 这确保了后续的 Plan 是基于一个已知的、干净的状态执行的
            engine.capture_drift(current_hash)
            # 捕获后，is_clean 逻辑上变为 True
        
        # 记录执行前的状态，作为 Plan 的 input_tree
        if engine.current_node:
            input_tree_hash = engine.current_node.output_tree
        else:
            # 此处处理极端的创世状态（理论上 capture_drift 应该已经处理了所有情况，除非 capture 失败）
            input_tree_hash = current_hash

        # --- Phase 3: Action (Execution) ---
        
        # 3.1 Parser
        final_parser_name = parser_name
        if parser_name == "auto":
            final_parser_name = detect_best_parser(content)
            if final_parser_name != "backtick":
                logger.info(f"🔍 自动检测到解析器: {final_parser_name}")

        parser = get_parser(final_parser_name)
        statements = parser.parse(content)
        
        if not statements:
            return QuipuResult(
                success=False, 
                exit_code=0, # 没找到指令不算错误，但也无需继续
                message=f"⚠️  使用 '{final_parser_name}' 解析器未找到任何有效的 'act' 操作块。"
            )

        # 3.2 Executor Setup
        # Executor 的根目录也严格为 work_dir
        executor = Executor(root_dir=work_dir, yolo=yolo)
        
        # 加载插件
        register_core_acts(executor) # 内置 (从 runtime 包加载)
        _load_extra_plugins(executor, work_dir) # 外部插件加载逻辑现在封装在辅助函数中

        # 3.3 Execute
        executor.execute(statements)

        # --- Phase 4: Recording (Plan Crystallization) ---
        
        # 执行成功后，计算新的状态
        output_tree_hash = engine.git_db.get_tree_hash()
        
        # 如果状态发生了变化，或者我们想记录即使无变化的 Plan（通常记录一下比较好）
        # 这里我们调用 Engine 的 create_plan_node 方法
        engine.create_plan_node(
            input_tree=input_tree_hash,
            output_tree=output_tree_hash,
            plan_content=content
        )

        return QuipuResult(success=True, exit_code=0, message="✨ 执行成功")

    except (ExecutionError, CoreExecutionError) as e:
        # 预期的执行错误 (如文件找不到，Git 冲突等)
        logger.error(f"❌ 操作失败: {e}")
        return QuipuResult(success=False, exit_code=1, message=str(e), error=e)
        
    except Exception as e:
        # 意外的运行时错误
        logger.error(f"运行时错误: {e}", exc_info=True)
        return QuipuResult(success=False, exit_code=1, message=f"系统错误: {e}", error=e)
~~~~~

### Acts 3: 添加隔离性验证测试

最后，我们创建一个新的测试文件，专门用于验证此修复是否有效，并防止未来发生回归。

~~~~~act
write_file tests/test_isolation.py
~~~~~

~~~~~python
import pytest
import subprocess
from pathlib import Path
from quipu.cli.controller import run_quipu

@pytest.fixture
def nested_git_project(tmp_path: Path):
    """
    创建一个嵌套的 Git 项目结构来模拟隔离问题。
    Structure:
        host_project/
            .git/
            <-- .quipu should NOT be created here
            
            work_dir/
                <-- .quipu SHOULD be created here
    """
    host_project = tmp_path / "host_project"
    host_project.mkdir()
    subprocess.run(["git", "init"], cwd=host_project, check=True, capture_output=True)

    work_dir = host_project / "work_dir"
    work_dir.mkdir()
    
    return host_project, work_dir


class TestWorkDirIsolation:
    
    def test_history_is_created_in_work_dir_not_host_project(self, nested_git_project):
        """
        验证：当在子目录 work_dir 中运行时，Quipu 的历史记录
        (.quipu) 必须在该子目录中创建，而不是在包含 .git 的父目录中。
        """
        host_project, work_dir = nested_git_project
        
        # 一个简单的 plan，用于触发历史记录的创建
        plan_content = """
        ~~~act
        write_file result.txt
        ~~~
        ~~~content
        isolation test
        ~~~
        """
        
        # 关键：调用 run_quipu，将 work_dir 设置为没有 .git 的子目录
        result = run_quipu(
            content=plan_content,
            work_dir=work_dir,
            yolo=True
        )
        
        # --- Assertions ---
        
        assert result.success is True, f"Quipu run failed: {result.message}"
        
        # 1. 验证文件操作发生在 work_dir
        assert (work_dir / "result.txt").exists()
        assert not (host_project / "result.txt").exists()
        
        # 2. 验证历史记录 (.quipu) 创建在 work_dir
        assert (work_dir / ".quipu").is_dir()
        assert (work_dir / ".quipu" / "HEAD").exists()
        
        # 3. 验证宿主项目没有被污染
        assert not (host_project / ".quipu").exists()

~~~~~
