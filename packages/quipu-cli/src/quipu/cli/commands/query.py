import dataclasses
import json
from datetime import datetime
from pathlib import Path
from typing import Annotated, Optional, List

import typer

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from quipu.core.models import QuipuNode


def _nodes_to_json_str(nodes: List[QuipuNode]) -> str:
    """
    Dynamically serializes a list of QuipuNode objects to a JSON string,
    avoiding hardcoded fields for better maintainability.
    """
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
    @app.command()
    def log(
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式输出结果。")] = False,
    ):
        """
        显示 Quipu 历史图谱日志。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            if not graph:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                raise typer.Exit(0)

            nodes = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)

            if json_output:
                typer.echo(_nodes_to_json_str(nodes))
                raise typer.Exit(0)

            typer.secho("--- Quipu History Log ---", bold=True, err=True)
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                color = typer.colors.CYAN if node.node_type == "plan" else typer.colors.MAGENTA
                tag = f"[{node.node_type.upper()}]"
                summary = node.summary
                typer.secho(f"{ts} {tag:<9} {node.short_hash}", fg=color, nl=False)
                typer.echo(f" - {summary}")

    @app.command(name="find")
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
        """
        根据条件查找历史节点。
        """
        with engine_context(work_dir) as engine:
            if not engine.history_graph:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            nodes = engine.find_nodes(summary_regex=summary_regex, node_type=node_type, limit=limit)

            if not nodes:
                if json_output:
                    typer.echo("[]")
                else:
                    typer.secho("🤷 未找到符合条件的历史节点。", fg=typer.colors.YELLOW, err=True)
                ctx.exit(0)

            if json_output:
                typer.echo(_nodes_to_json_str(nodes))
                ctx.exit(0)

            typer.secho("--- 查找结果 ---", bold=True, err=True)
            for node in nodes:
                ts = node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                color = typer.colors.CYAN if node.node_type == "plan" else typer.colors.MAGENTA
                tag = f"[{node.node_type.upper()}]"
                typer.secho(f"{ts} {tag:<9} {node.output_tree}", fg=color, nl=False)
                typer.echo(f" - {node.summary}")
