import logging
import re
import shutil
from pathlib import Path
from typing import Annotated, Dict, List, Optional, Set

import typer
import yaml
from pyquipu.common.messaging import bus
from pyquipu.engine.state_machine import Engine
from pyquipu.interfaces.models import QuipuNode

from ..config import DEFAULT_WORK_DIR
from ..ui_utils import prompt_for_confirmation
from .helpers import engine_context, filter_nodes, filter_reachable_nodes

logger = logging.getLogger(__name__)


def _sanitize_summary(summary: str) -> str:
    if not summary:
        return "no-summary"
    sanitized = re.sub(r"[\\/:#\[\]|]", "_", summary)
    sanitized = re.sub(r"[\s_]+", "_", sanitized)
    return sanitized[:60]


def _generate_filename(node: QuipuNode) -> str:
    ts = node.timestamp.strftime("%y%m%d-%H%M")
    short_hash = node.commit_hash[:7]
    sanitized_summary = _sanitize_summary(node.summary)
    return f"{ts}-{short_hash}-{sanitized_summary}.md"


def _format_frontmatter(node: QuipuNode) -> str:
    data = {
        "commit_hash": node.commit_hash,
        "output_tree": node.output_tree,
        "input_tree": node.input_tree,
        "timestamp": node.timestamp.isoformat(),
        "node_type": node.node_type,
    }
    if node.owner_id:
        data["owner_id"] = node.owner_id
    yaml_str = yaml.dump(data, Dumper=yaml.SafeDumper, default_flow_style=False, sort_keys=False)
    return f"---\n{yaml_str}---"


def _generate_navbar(
    current_node: QuipuNode,
    exported_hashes_set: Set[str],
    filename_map: Dict[str, str],
    hidden_link_types: Set[str],
) -> str:
    nav_links = []

    # 1. 总结节点 (↑)
    if "summary" not in hidden_link_types:
        ancestor = current_node.parent
        while ancestor:
            if ancestor.input_tree == ancestor.output_tree and ancestor.commit_hash in exported_hashes_set:
                nav_links.append(f"> ↑ [总结节点]({filename_map[ancestor.commit_hash]})")
                break
            ancestor = ancestor.parent

    # 2. 上一分支点 (↓)
    if "branch" not in hidden_link_types:
        ancestor = current_node.parent
        found_branch_point = None
        while ancestor:
            if len(ancestor.children) > 1 and ancestor.commit_hash in exported_hashes_set:
                found_branch_point = ancestor
                break
            ancestor = ancestor.parent
        if (
            found_branch_point
            and current_node.parent
            and found_branch_point.commit_hash != current_node.parent.commit_hash
        ):
            nav_links.append(f"> ↓ [上一分支点]({filename_map[found_branch_point.commit_hash]})")

    # 3. 父节点 (←)
    if "parent" not in hidden_link_types:
        if current_node.parent and current_node.parent.commit_hash in exported_hashes_set:
            nav_links.append(f"> ← [父节点]({filename_map[current_node.parent.commit_hash]})")

    # 4. 子节点 (→)
    if "child" not in hidden_link_types:
        for child in current_node.children:
            if child.commit_hash in exported_hashes_set:
                nav_links.append(f"> → [子节点]({filename_map[child.commit_hash]})")

    if not nav_links:
        return ""

    return "\n\n" + "> [!nav] 节点导航\n" + "\n".join(nav_links)


def _generate_file_content(
    node: QuipuNode,
    engine: Engine,
    no_frontmatter: bool,
    no_nav: bool,
    exported_hashes_set: Set[str],
    filename_map: Dict[str, str],
    hidden_link_types: Set[str],
) -> str:
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
        navbar_str = _generate_navbar(node, exported_hashes_set, filename_map, hidden_link_types)
        content_str += navbar_str

    return content_str


def register(app: typer.Typer):
    @app.command(name="export", help="将历史图谱中的节点导出为 Markdown 文件。")
    def export_command(
        ctx: typer.Context,
        work_dir: Annotated[
            Path, typer.Option("--work-dir", "-w", help="工作区根目录", resolve_path=True)
        ] = DEFAULT_WORK_DIR,
        output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="导出目录", resolve_path=True)] = Path(
            "./.quipu/export"
        ),
        limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="限制最新节点数量")] = None,
        since: Annotated[Optional[str], typer.Option("--since", help="起始时间戳 (YYYY-MM-DD HH:MM)")] = None,
        until: Annotated[Optional[str], typer.Option("--until", help="截止时间戳 (YYYY-MM-DD HH:MM)")] = None,
        zip_output: Annotated[bool, typer.Option("--zip", help="压缩导出目录")] = False,
        no_nav: Annotated[bool, typer.Option("--no-nav", help="禁用导航栏")] = False,
        no_frontmatter: Annotated[bool, typer.Option("--no-frontmatter", help="禁用 Frontmatter")] = False,
        hide_link_type: Annotated[
            Optional[List[str]],
            typer.Option(
                "--hide-link-type", help="禁用特定类型的导航链接 (可多次使用: summary, branch, parent, child)"
            ),
        ] = None,
        reachable_only: Annotated[
            bool, typer.Option("--reachable-only", help="仅导出与当前工作区状态直接相关的节点。")
        ] = False,
    ):
        hidden_types = set(hide_link_type) if hide_link_type else set()

        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                bus.info("export.info.emptyHistory")
                ctx.exit(0)

            nodes_to_process = sorted(engine.history_graph.values(), key=lambda n: n.timestamp, reverse=True)

            if reachable_only:
                nodes_to_process = filter_reachable_nodes(engine, nodes_to_process)

            try:
                # filter_nodes returns preserving input order (reverse chrono),
                # but export expects chronological order for file generation/processing
                filtered = filter_nodes(nodes_to_process, limit, since, until)
                nodes_to_export = list(reversed(filtered))
            except typer.BadParameter as e:
                bus.error("export.error.badParam", error=str(e))
                ctx.exit(1)

            if not nodes_to_export:
                bus.info("export.info.noMatchingNodes")
                ctx.exit(0)

            if output_dir.exists() and any(output_dir.iterdir()):
                prompt = bus.get("export.prompt.overwrite", path=output_dir)
                if not prompt_for_confirmation(prompt, default=False):
                    bus.warning("common.prompt.cancel")
                    raise typer.Abort()
                shutil.rmtree(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

            bus.info("export.info.starting", count=len(nodes_to_export), path=output_dir)

            # 预计算文件名和节点集合以供导航栏使用
            filename_map = {node.commit_hash: _generate_filename(node) for node in nodes_to_export}
            exported_hashes_set = {node.commit_hash for node in nodes_to_export}

            with typer.progressbar(nodes_to_export, label="导出进度") as progress:
                for node in progress:
                    filename = filename_map[node.commit_hash]
                    content = _generate_file_content(
                        node, engine, no_frontmatter, no_nav, exported_hashes_set, filename_map, hidden_types
                    )
                    (output_dir / filename).write_text(content, encoding="utf-8")

            if zip_output:
                bus.info("export.info.zipping")
                zip_path = shutil.make_archive(str(output_dir), "zip", output_dir)
                shutil.rmtree(output_dir)
                bus.success("export.success.zip", path=zip_path)
            else:
                bus.success("export.success.dir")
