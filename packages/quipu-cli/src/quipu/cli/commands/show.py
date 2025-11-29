import json
import logging
from pathlib import Path
from typing import Annotated, Optional, Dict, List

import typer
from rich.console import Console
from rich.syntax import Syntax

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR
from quipu.common.messaging import bus

logger = logging.getLogger(__name__)


def _find_target_node(graph: Dict, hash_prefix: str):
    """辅助函数，用于在图中查找唯一的节点。"""
    matches = [
        node
        for node in graph.values()
        if node.commit_hash.startswith(hash_prefix) or node.output_tree.startswith(hash_prefix)
    ]
    if not matches:
        bus.error("show.error.notFound", hash_prefix=hash_prefix)
        raise typer.Exit(1)
    if len(matches) > 1:
        bus.error("show.error.notUnique", hash_prefix=hash_prefix, count=len(matches))
        raise typer.Exit(1)
    return matches[0]


def register(app: typer.Typer):
    @app.command()
    def show(
        ctx: typer.Context,
        hash_prefix: Annotated[str, typer.Argument(help="目标状态节点的 commit_hash 或 output_tree 的哈希前缀。")],
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
            ),
        ] = DEFAULT_WORK_DIR,
        json_output: Annotated[bool, typer.Option("--json", help="以 JSON 格式将结果输出到 stdout。")] = False,
        extract: Annotated[
            Optional[List[str]], typer.Option("--extract", "-e", help="仅提取并显示指定文件的内容 (可多次使用)。")
        ] = None,
    ):
        """
        显示指定历史节点的详细信息，包括所有内部文件。
        """
        with engine_context(work_dir) as engine:
            target_node = _find_target_node(engine.history_graph, hash_prefix)
            blobs = engine.reader.get_node_blobs(target_node.commit_hash)

            if not blobs:
                if json_output:
                    bus.data("{}")
                else:
                    bus.info("show.info.noContent")
                raise typer.Exit()

            # --- Phase 1: Build output dictionary ---
            output_data = {}
            files_to_process = extract if extract else sorted(blobs.keys())

            for filename in files_to_process:
                if filename not in blobs:
                    bus.error("show.error.fileNotInNode", filename=filename)
                    bus.info("show.info.availableFiles", file_list=", ".join(blobs.keys()))
                    raise typer.Exit(1)

                content_bytes = blobs[filename]
                try:
                    output_data[filename] = content_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    output_data[filename] = f"<binary data, {len(content_bytes)} bytes>"

            # --- Phase 2: Render output ---
            if json_output:
                bus.data(json.dumps(output_data, indent=2, ensure_ascii=False))
            else:
                console = Console()
                if extract:
                    # User explicitly extracted files, show them directly
                    for filename, content in output_data.items():
                        if len(extract) > 1:
                            console.rule(f"[bold]{filename}[/bold]", style="blue")

                        # Per user directive, completely disable rich formatting for --extract
                        # to guarantee raw, unmodified output.
                        console.print(content, end="")
                else:
                    # Default view: show summary and all files prettified
                    ts = target_node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                    color = "cyan" if target_node.node_type == "plan" else "magenta"
                    tag = f"[{target_node.node_type.upper()}]"
                    typer.secho(f"[{color}]{ts} {tag:<9} {target_node.short_hash}[/{color}] - {target_node.summary}\n")

                    for filename, content in output_data.items():
                        console.rule(f"[bold]{filename}[/bold]", style="blue")
                        if filename.endswith(".json"):
                            syntax = Syntax(content, "json", theme="default", line_numbers=False, word_wrap=False)
                            console.print(syntax)
                        else:
                            console.print(content.strip())
                        console.print()
