import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, List, Optional

import typer
from pyquipu.common.messaging import bus
from pyquipu.interfaces.models import QuipuNode

from ..config import DEFAULT_WORK_DIR
from .helpers import engine_context, filter_nodes, filter_reachable_nodes


def _nodes_to_json_str(nodes: List[QuipuNode]) -> str:
    EXCLUDED_FIELDS = {"parent", "children", "content", "filename"}
    node_list = []
    for node in nodes:
        node_dict = {}
        for field in dataclasses.fields(node):
            if field.name in EXCLUDED_FIELDS:
                continue
            value = getattr(node, field.name)
            if isinstance(value, datetime):
                node_dict[field.name] = value.isoformat()
            else:
                node_dict[field.name] = value

        # Explicitly add properties
        node_dict["short_hash"] = node.short_hash
        node_list.append(node_dict)

    return json.dumps(node_list, indent=2)


def register(app: typer.Typer):
    @app.command(help="按时间倒序显示历史图谱。")
    def log(
        ctx: typer.Context,
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        limit: Annotated[Optional[int], typer.Option("--limit", "-n", help="限制显示的节点数量。")] = None,
        since: Annotated[Optional[str], typer.Option("--since", help="起始时间戳 (YYYY-MM-DD HH:MM)。")] = None,
        until: Annotated[Optional[str], typer.Option("--until", help="截止时间戳 (YYYY-MM-DD HH:MM)。")] = None,
        reachable_only: Annotated[
            bool, typer.Option("--reachable-only", help="仅显示与当前工作区状态直接相关的节点。")
        ] = False,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            if not graph:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.emptyHistory")
                raise typer.Exit(0)

            nodes_to_process = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)

            if reachable_only:
                nodes_to_process = filter_reachable_nodes(engine, nodes_to_process)

            try:
                nodes = filter_nodes(nodes_to_process, limit, since, until)
            except typer.BadParameter as e:
                bus.error("common.error.invalidConfig", error=str(e))
                ctx.exit(1)

            if not nodes:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.noResults")
                raise typer.Exit(0)

            if json_output:
                bus.data(_nodes_to_json_str(nodes))
                raise typer.Exit(0)

            bus.info("query.log.ui.header")
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                tag = f"[{node.node_type.upper()}]"
                summary = node.summary
                # Note: Coloring is a presentation detail handled by renderer, or omitted for data.
                # Here we pass the uncolored data string to the bus.
                data_line = f"{ts} {tag:<9} {node.short_hash} - {summary}"
                bus.data(data_line)

    @app.command(name="find", help="根据摘要或类型搜索历史节点。")
    def find_command(
        ctx: typer.Context,
        summary_regex: Annotated[
            Optional[str], typer.Option("--summary", "-s", help="用于匹配节点摘要的正则表达式 (不区分大小写)。")
        ] = None,
        node_type: Annotated[
            Optional[str], typer.Option("--type", "-t", help="节点类型 ('plan' 或 'capture')。")
        ] = None,
        limit: Annotated[int, typer.Option("--limit", "-n", help="返回的最大结果数量。")] = 10,
        work_dir: Annotated[Path, typer.Option("--work-dir", "-w", help="工作区根目录。")] = DEFAULT_WORK_DIR,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.emptyHistory")
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if json_output:
                    bus.data("[]")
                else:
                    bus.info("query.info.noResults")
                ctx.exit(0)

            if json_output:
                bus.data(_nodes_to_json_str(nodes))
                ctx.exit(0)

            bus.info("query.find.ui.header")
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                tag = f"[{node.node_type.upper()}]"
                data_line = f"{ts} {tag:<9} {node.output_tree} - {node.summary}"
                bus.data(data_line)
