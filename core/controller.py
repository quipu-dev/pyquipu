import logging
import os
import sys
from pathlib import Path
from typing import Optional

from .result import AxonResult
from .engine import Engine
from .executor import Executor, ExecutionError
from .exceptions import ExecutionError as CoreExecutionError # Alias to avoid conflict
from .parser import get_parser, detect_best_parser
from .plugin_loader import load_plugins

# 从配置导入，注意为了解耦，未来可能需要将 config 注入而不是直接导入
from config import PROJECT_ROOT

logger = logging.getLogger(__name__)

def _find_project_root(start_path: Path) -> Optional[Path]:
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
    按照层级顺序加载外部插件。
    优先级：Local > Project > Env > Home
    """
    plugin_dirs = []
    
    # 1. User Home
    home_acts = Path.home() / ".axon" / "acts"
    plugin_dirs.append(("🏠 Global", home_acts))

    # 2. Config / Env
    env_path = os.getenv("AXON_EXTRA_ACTS_DIR")
    if env_path:
        plugin_dirs.append(("🔧 Env", Path(env_path)))

    # 3. Project Root (Context)
    project_root = _find_project_root(work_dir)
    if project_root:
        proj_acts = project_root / ".axon" / "acts"
        if proj_acts != (work_dir / ".axon" / "acts"):
             plugin_dirs.append(("📦 Project", proj_acts))

    # 4. Current Work Dir (Local)
    cwd_acts = work_dir / ".axon" / "acts"
    plugin_dirs.append(("📂 Local", cwd_acts))

    seen_paths = set()
    for label, path in plugin_dirs:
        resolved = path.resolve() if path.exists() else path
        if resolved in seen_paths:
            continue
            
        if path.exists() and path.is_dir():
            load_plugins(executor, path)
            seen_paths.add(resolved)

def run_axon(
    content: str,
    work_dir: Path,
    parser_name: str = "auto",
    yolo: bool = False
) -> AxonResult:
    """
    Axon 核心业务逻辑入口。
    
    负责协调 Engine (状态), Parser (解析), Executor (执行) 三者的工作。
    任何异常都会被捕获并转化为失败的 AxonResult。
    """
    try:
        # --- Phase 1: Engine Initialization & Perception ---
        engine = Engine(work_dir)
        status = engine.align() # "CLEAN", "DIRTY", "ORPHAN"
        
        current_hash = engine.git_db.get_tree_hash()
        
        # --- Phase 2: Decision (Lazy Capture) ---
        if status in ["DIRTY", "ORPHAN"]:
            # 如果环境有漂移（或全新项目），先生成一个 Capture 节点
            # 这确保了后续的 Plan 是基于一个已知的、干净的状态执行的
            engine.capture_drift(current_hash)
            # 捕获后，status 逻辑上变为 CLEAN，current_node 更新为 CaptureNode
        
        # 记录执行前的状态，作为 Plan 的 input_tree
        if not engine.current_node:
             # 理论上 capture_drift 后一定有 node，除非极端的 git 错误
             raise RuntimeError("Engine failed to lock state.")
             
        input_tree_hash = engine.current_node.output_tree

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
            return AxonResult(
                success=False, 
                exit_code=0, # 没找到指令不算错误，但也无需继续
                message=f"⚠️  使用 '{final_parser_name}' 解析器未找到任何有效的 'act' 操作块。"
            )

        # 3.2 Executor Setup
        executor = Executor(root_dir=work_dir, yolo=yolo)
        
        # 加载插件
        load_plugins(executor, PROJECT_ROOT / "acts") # 内置
        _load_extra_plugins(executor, work_dir)       # 外部

        # 3.3 Execute
        executor.execute(statements)

        # --- Phase 4: Recording (Plan Crystallization) ---
        
        # 执行成功后，计算新的状态
        output_tree_hash = engine.git_db.get_tree_hash()
        
        # 如果状态发生了变化，或者我们想记录即使无变化的 Plan（通常记录一下比较好）
        # 这里我们调用 Engine 的 create_plan_node 方法
        # 注意：该方法需要在 Engine 类中实现
        if hasattr(engine, "create_plan_node"):
            engine.create_plan_node(
                input_tree=input_tree_hash,
                output_tree=output_tree_hash,
                plan_content=content
            )
        else:
            logger.warning("⚠️  Engine 尚未实现 'create_plan_node'，跳过历史记录。")

        return AxonResult(success=True, exit_code=0, message="✨ 执行成功")

    except (ExecutionError, CoreExecutionError) as e:
        # 预期的执行错误 (如文件找不到，Git 冲突等)
        logger.error(f"❌ 操作失败: {e}")
        return AxonResult(success=False, exit_code=1, message=str(e), error=e)
        
    except Exception as e:
        # 意外的运行时错误
        logger.error(f"运行时错误: {e}", exc_info=True)
        return AxonResult(success=False, exit_code=1, message=f"系统错误: {e}", error=e)