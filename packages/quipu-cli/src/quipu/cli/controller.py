import logging
import os
import sys
from pathlib import Path
from typing import Optional

from quipu.core.result import QuipuResult
from quipu.core.state_machine import Engine
from quipu.core.executor import Executor, ExecutionError
from quipu.core.exceptions import ExecutionError as CoreExecutionError
from quipu.core.parser import get_parser, detect_best_parser
from quipu.core.plugin_loader import load_plugins
from quipu.core.file_system_storage import FileSystemHistoryReader, FileSystemHistoryWriter

# 从配置导入，注意为了解耦，未来可能需要将 config 注入而不是直接导入
from .config import PROJECT_ROOT
from quipu.acts import register_core_acts

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
        # 无论用户从哪个子目录启动，都必须找到并使用唯一的项目根。
        # 这是确保 Engine 和 Executor 上下文一致性的关键。
        project_root = find_project_root(work_dir)
        if not project_root:
            # 如果不在 Git 仓库内，则使用原始 work_dir，但 Engine 初始化会失败。
            # 这是预期的行为，因为 Axon 强依赖 Git。
            project_root = work_dir
        
        logger.info(f"Project Root resolved to: {project_root}")

        # --- Phase 1: Engine Initialization & Perception ---
        # 注意：所有核心组件都必须使用规范化后的 project_root 初始化！
        history_dir = project_root / ".quipu" / "history"
        reader = FileSystemHistoryReader(history_dir)
        writer = FileSystemHistoryWriter(history_dir)
        engine = Engine(project_root, reader=reader, writer=writer)

        status = engine.align() # "CLEAN", "DIRTY", "ORPHAN"
        
        current_hash = engine.git_db.get_tree_hash()
        
        # --- Phase 2: Decision (Lazy Capture) ---
        if status in ["DIRTY", "ORPHAN"]:
            # 如果环境有漂移（或全新项目），先生成一个 Capture 节点
            # 这确保了后续的 Plan 是基于一个已知的、干净的状态执行的
            engine.capture_drift(current_hash)
            # 捕获后，status 逻辑上变为 CLEAN，current_node 更新为 CaptureNode
        
        # 记录执行前的状态，作为 Plan 的 input_tree
        if engine.current_node:
            input_tree_hash = engine.current_node.output_tree
        else:
            # 此处处理创世状态：当 align() 返回 CLEAN 但 current_node 为 None 时。
            # 输入哈希就是当前的（空的）哈希。
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
        # 注意：该方法需要在 Engine 类中实现
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