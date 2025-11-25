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
    project_root = find_project_root(work_dir)
    if project_root:
        proj_acts = project_root / ".quipu" / "acts"
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
        # --- Phase 0: Root Canonicalization (根目录规范化) ---
        project_root = find_project_root(work_dir)
        if not project_root:
            # 如果不在 Git 仓库内，则使用原始 work_dir，但 Engine 初始化可能会失败。
            project_root = work_dir
        
        logger.info(f"Project Root resolved to: {project_root}")

        # --- Phase 1: Engine Initialization & Perception ---
        # 使用工厂创建 Engine，这会自动处理存储后端检测和 align
        engine = create_engine(work_dir)
        
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
        executor = Executor(root_dir=project_root, yolo=yolo) # 使用 project_root
        
        # 加载插件
        register_core_acts(executor) # 内置 (从 runtime 包加载)
        _load_extra_plugins(executor, project_root)       # 外部 (也基于 project_root)

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