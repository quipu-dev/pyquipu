import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, List, Dict, Set

import typer
import yaml

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from quipu.interfaces.models import QuipuNode
from quipu.engine.state_machine import Engine

logger = logging.getLogger(__name__)


def _sanitize_summary(summary: str) -> str:
    """净化摘要以用作安全的文件名部分。"""
    if not summary:
        return "no-summary"
    sanitized = re.sub(r'[\\/:#\[\]|]', '_', summary)
    sanitized = re.sub(r'[\s_]+', '_', sanitized)
    return sanitized[:60]


def _generate_filename(node: QuipuNode) -> str:
    """根据规范生成文件名。"""
    ts = node.timestamp.strftime("%y%m%d-%H%M")
    short_hash = node.commit_hash[:7]
    sanitized_summary = _sanitize_summary(node.summary)
    return f"{ts}-{short_hash}-{sanitized_summary}.md"


def _format_frontmatter(node: QuipuNode) -> str:
    """生成 YAML Frontmatter 字符串。"""
    data = {
        "commit_hash": node.commit_hash, "output_tree": node.output_tree, "input_tree": node.input_tree,
        "timestamp": node.timestamp.isoformat(), "node_type": node.node_type,
    }
    if node.owner_id:
        data["owner_id"] = node.owner_id
    yaml_str = yaml.dump(data, Dumper=yaml.SafeDumper, default_flow_style=False, sort_keys=False)
    return f"---\n{yaml_str}---"


def _filter_nodes(
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
    return list(reversed(filtered))


def _generate_navbar(
    current_node: QuipuNode, exported_hashes_set: Set[str], filename_map: Dict[str, str]
) -> str:
    """生成导航栏 Markdown 字符串。"""
    nav_links = []

    # 1. 总结节点 (↑)
    ancestor = current_node.parent
    while ancestor:
        if ancestor.input_tree == ancestor.output_tree and ancestor.commit_hash in exported_hashes_set:
            nav_links.append(f"> ↑ [总结节点]({filename_map[ancestor.commit_hash]})")
            break
        ancestor = ancestor.parent

    # 2. 上一分支点 (↓)
    ancestor = current_node.parent
    while ancestor:
        if len(ancestor.children) > 1 and ancestor.commit_hash in exported_hashes_set:
            nav_links.append(f"> ↓ [上一分支点]({filename_map[ancestor.commit_hash]})")
            break
        ancestor = ancestor.parent

    # 3. 父节点 (←)
    if current_node.parent and current_node.parent.commit_hash in exported_hashes_set:
        nav_links.append(f"> ← [父节点]({filename_map[current_node.parent.commit_hash]})")

    # 4. 子节点 (→)
    # 子节点已按时间升序排列
    for child in current_node.children:
        if child.commit_hash in exported_hashes_set:
            nav_links.append(f"> → [子节点]({filename_map[child.commit_hash]})")

    if not nav_links:
        return ""
    
    return "\n\n" + "> [!nav] 节点导航\n" + "\n".join(nav_links)


def _generate_file_content(
    node: QuipuNode, engine: Engine, no_frontmatter: bool, no_nav: bool,
    exported_hashes_set: Set[str], filename_map: Dict[str, str]
) -> str:
    """构建单个 Markdown 文件的完整内容。"""
    parts = []
    if not no_frontmatter:
        parts.append(_format_frontmatter(node))

    public_content = engine.reader.get_node_content(node) or ""
    parts.append("# content.md")
    parts.append(public_content.strip())

    private_content = engine.reader.get_private_data(node.commit_hash)
    if private_content:
        parts.append("# 开发者意图")
        parts.append(private_content.strip())
        
    content_str = "\n\n".join(parts)

    if not no_nav:
        navbar_str = _generate_navbar(node, exported_hashes_set, filename_map)
        content_str += navbar_str
        
    return content_str


def register(app: typer.Typer):
    @app.command(name="export")
    def export_command(
        ctx: typer.Context,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录", resolve_path=True)] = DEFAULT_WORK_DIR,
        output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="导出目录", resolve_path=True)] = Path("./.quipu/export"),
        limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="限制最新节点数量")] = None,
        since: Annotated[Optional[str], typer.Option("--since", help="起始时间戳 (YYYY-MM-DD HH:MM)")] = None,
        until: Annotated[Optional[str], typer.Option("--until", help="截止时间戳 (YYYY-MM-DD HH:MM)")] = None,
        zip_output: Annotated[bool, typer.Option("--zip", help="压缩导出目录")] = False,
        no_nav: Annotated[bool, typer.Option("--no-nav", help="禁用导航栏")] = False,
        no_frontmatter: Annotated[bool, typer.Option("--no-frontmatter", help="禁用 Frontmatter")] = False,
    ):
        """将 Quipu 历史记录导出为一组人类可读的 Markdown 文件。"""
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                typer.secho("📜 历史记录为空，无需导出。", fg=typer.colors.YELLOW, err=True); ctx.exit(0)

            all_nodes = sorted(engine.history_graph.values(), key=lambda n: n.timestamp, reverse=True)
            try:
                nodes_to_export = _filter_nodes(all_nodes, limit, since, until)
            except typer.BadParameter as e:
                typer.secho(f"❌ 参数错误: {e}", fg=typer.colors.RED, err=True); ctx.exit(1)

            if not nodes_to_export:
                typer.secho("🤷 未找到符合条件的节点。", fg=typer.colors.YELLOW, err=True); ctx.exit(0)

            if output_dir.exists() and any(output_dir.iterdir()):
                if not typer.confirm(f"⚠️ 目录 '{output_dir}' 非空，是否清空并继续?", abort=True):
                    return
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            typer.secho(f"🚀 正在导出 {len(nodes_to_export)} 个节点到 '{output_dir}'...", fg=typer.colors.BLUE, err=True)

            # 预计算文件名和节点集合以供导航栏使用
            filename_map = {node.commit_hash: _generate_filename(node) for node in nodes_to_export}
            exported_hashes_set = {node.commit_hash for node in nodes_to_export}

            with typer.progressbar(nodes_to_export, label="导出进度") as progress:
                for node in progress:
                    filename = filename_map[node.commit_hash]
                    content = _generate_file_content(node, engine, no_frontmatter, no_nav, exported_hashes_set, filename_map)
                    (output_dir / filename).write_text(content, encoding="utf-8")

            if zip_output:
                typer.secho("📦 正在压缩导出文件...", fg=typer.colors.BLUE, err=True)
                zip_path = shutil.make_archive(str(output_dir), 'zip', output_dir)
                shutil.rmtree(output_dir)
                typer.secho(f"\n✅ 导出成功，已保存为压缩包: {zip_path}", fg=typer.colors.GREEN, err=True)
            else:
                typer.secho(f"\n✅ 导出成功完成。", fg=typer.colors.GREEN, err=True)