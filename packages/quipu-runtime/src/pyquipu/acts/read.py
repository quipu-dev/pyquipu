import argparse
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.exceptions import ExecutionError
from pyquipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    executor.register("read_file", _read_file, arg_mode="hybrid")
    executor.register("list_files", _list_files, arg_mode="exclusive")
    executor.register("search_files", _search_files, arg_mode="exclusive")


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ExecutionError(f"参数解析错误: {message}")

    def exit(self, status=0, message=None):
        if message:
            raise ExecutionError(message)


def _search_files(ctx: ActContext, args: List[str]):
    parser = SafeArgumentParser(prog="search_files", add_help=False)
    parser.add_argument("pattern", help="搜索内容的正则表达式")
    parser.add_argument("--path", "-p", default=".", help="搜索的根目录")

    try:
        parsed_args = parser.parse_args(args)
    except ExecutionError as e:
        ctx.fail(str(e))
    except Exception as e:
        ctx.fail(f"参数解析异常: {e}")

    search_path = ctx.resolve_path(parsed_args.path)
    if not search_path.exists():
        ctx.fail(bus.get("acts.read.error.pathNotFound", path=search_path))

    bus.info("acts.read.info.searching", pattern=parsed_args.pattern, path=search_path)

    if shutil.which("rg"):
        bus.info("acts.read.info.useRipgrep")
        try:
            cmd = ["rg", "-n", "--no-heading", "--color=never", parsed_args.pattern, str(search_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=ctx.root_dir)
            if result.stdout:
                bus.data(result.stdout.strip())
            else:
                bus.info("acts.read.info.noMatchRipgrep")
            return
        except Exception as e:
            bus.warning("acts.read.warning.ripgrepFailed", error=str(e))

    bus.info("acts.read.info.usePythonSearch")
    _python_search(ctx, search_path, parsed_args.pattern)


def _python_search(ctx: ActContext, start_path: Path, pattern_str: str):
    try:
        regex = re.compile(pattern_str)
    except re.error as e:
        ctx.fail(bus.get("acts.read.error.invalidRegex", pattern=pattern_str, error=e))

    matches = []
    for root, dirs, files in os.walk(start_path):
        dirs[:] = [d for d in dirs if d not in {".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"}]
        for file in files:
            file_path = Path(root) / file
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if regex.search(line):
                            clean_line = line.strip()
                            relative_path = file_path.relative_to(ctx.root_dir)
                            matches.append(f"{relative_path}:{i}:{clean_line[:200]}")
            except (UnicodeDecodeError, PermissionError):
                continue

    if matches:
        bus.data("\n".join(matches))
    else:
        bus.info("acts.read.info.noMatchPython")


def _read_file(ctx: ActContext, args: List[str]):
    if not args:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="read_file", count=1, signature="[path]"))

    target_path = ctx.resolve_path(args[0])
    if not target_path.exists():
        ctx.fail(bus.get("acts.read.error.targetNotFound", path=args[0]))
    if target_path.is_dir():
        ctx.fail(bus.get("acts.read.error.targetIsDir", path=args[0]))

    try:
        content = target_path.read_text(encoding="utf-8")
        bus.info("acts.read.info.readingFile", filename=target_path.name)
        bus.data(content)
    except UnicodeDecodeError:
        bus.error("acts.read.error.binaryOrEncoding", filename=args[0])
    except Exception as e:
        ctx.fail(bus.get("acts.read.error.readFailed", error=e))


def _list_files(ctx: ActContext, args: List[str]):
    parser = SafeArgumentParser(prog="list_files", add_help=False)
    parser.add_argument("path", nargs="?", default=".", help="目标目录")
    parser.add_argument("--tree", "-t", action="store_true", help="以树状结构递归显示")

    try:
        parsed_args = parser.parse_args(args)
    except Exception as e:
        ctx.fail(f"参数解析异常: {e}")

    target_dir = ctx.resolve_path(parsed_args.path)
    if not target_dir.is_dir():
        ctx.fail(bus.get("acts.read.error.dirNotFound", path=target_dir))

    output = []
    if parsed_args.tree:
        bus.info("acts.read.info.listingTree", path=target_dir)
        for path_object in sorted(target_dir.rglob("*")):
            if ".git" in path_object.parts or ".quipu" in path_object.parts:
                continue
            depth = len(path_object.relative_to(target_dir).parts) - 1
            indent = "    " * depth
            output.append(f"{indent}└── {path_object.name}{'/' if path_object.is_dir() else ''}")
    else:
        bus.info("acts.read.info.listingDir", path=target_dir)
        items = sorted(list(target_dir.iterdir()), key=lambda p: (p.is_file(), p.name.lower()))
        for item in items:
            if item.name.startswith("."):
                continue
            output.append(f"📁 {item.name}/" if item.is_dir() else f"📄 {item.name}")

    if not output:
        output.append("(Empty directory)")
    bus.data("\n".join(output))
