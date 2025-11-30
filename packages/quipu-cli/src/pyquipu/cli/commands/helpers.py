import logging
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List, Optional

import typer
from pyquipu.common.messaging import bus
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode

from ..factory import create_engine
from ..logger_config import setup_logging

logger = logging.getLogger(__name__)


@contextmanager
def engine_context(work_dir: Path) -> Generator[Engine, None, None]:
    """Context manager to set up logging, create, and automatically close a Quipu engine."""
    setup_logging()
    engine = None
    try:
        engine = create_engine(work_dir)
        yield engine
    finally:
        if engine:
            engine.close()


def _find_current_node(engine: Engine, graph: Dict[str, QuipuNode]) -> Optional[QuipuNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
    # 修复：直接从 graph 中通过 output_tree hash 查找
    for node in graph.values():
        if node.output_tree == current_hash:
            return node

    bus.warning("navigation.warning.workspaceDirty")
    bus.info("navigation.info.saveHint")
    return None


def _execute_visit(ctx: typer.Context, engine: Engine, target_hash: str, msg_id: str, **kwargs):
    """辅助函数：执行 engine.visit 并处理结果"""
    bus.info(msg_id, **kwargs)
    try:
        engine.visit(target_hash)
        bus.success("navigation.success.visit", short_hash=target_hash[:7])
    except Exception as e:
        logger.error(f"导航操作失败 (目标哈希: {target_hash[:12]})", exc_info=True)
        bus.error("navigation.error.generic", error=str(e))
        ctx.exit(1)


def filter_nodes(
    nodes: List[QuipuNode], limit: Optional[int], since: Optional[str], until: Optional[str]
) -> List[QuipuNode]:
    """根据时间戳和数量过滤节点列表。"""
    filtered = nodes
    if since:
        try:
            since_dt = datetime.fromisoformat(since.replace(" ", "T"))
            filtered = [n for n in filtered if n.timestamp >= since_dt]
        except ValueError:
            raise typer.BadParameter("无效的 'since' 时间戳格式。请使用 'YYYY-MM-DD HH:MM'。")
    if until:
        try:
            until_dt = datetime.fromisoformat(until.replace(" ", "T"))
            filtered = [n for n in filtered if n.timestamp <= until_dt]
        except ValueError:
            raise typer.BadParameter("无效的 'until' 时间戳格式。请使用 'YYYY-MM-DD HH:MM'。")
    if limit is not None and limit > 0:
        filtered = filtered[:limit]
    return filtered


def filter_reachable_nodes(engine: Engine, nodes: List[QuipuNode]) -> List[QuipuNode]:
    """仅保留与当前工作区状态直接相关的节点（祖先和后代）。"""
    current_node = _find_current_node(engine, engine.history_graph)
    if not current_node:
        # 如果工作区是脏的，无法确定起点，返回所有节点
        return nodes

    current_hash = current_node.output_tree
    ancestors = engine.reader.get_ancestor_output_trees(current_hash)
    descendants = engine.reader.get_descendant_output_trees(current_hash)
    reachable_set = ancestors.union(descendants)
    reachable_set.add(current_hash)

    return [node for node in nodes if node.output_tree in reachable_set]
