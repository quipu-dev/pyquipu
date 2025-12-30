import logging
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    executor.register("write_file", _write_file, arg_mode="hybrid", summarizer=_summarize_write)
    executor.register("patch_file", _patch_file, arg_mode="hybrid", summarizer=_summarize_patch_file)
    executor.register("append_file", _append_file, arg_mode="hybrid", summarizer=_summarize_append)
    executor.register("end", _end, arg_mode="hybrid")
    executor.register("echo", _echo, arg_mode="hybrid")


def _summarize_write(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"Write: {path}"


def _summarize_patch_file(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"patch_file in: {path}"


def _summarize_append(args: List[str], contexts: List[str]) -> str:
    path = args[0] if args else (contexts[0] if contexts else "???")
    return f"Append to: {path}"


def _end(ctx: ActContext, args: List[str]):
    pass


def _echo(ctx: ActContext, args: List[str]):
    if len(args) < 1:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="echo", count=1, signature="[content]"))

    bus.data(args[0])


def _write_file(ctx: ActContext, args: List[str]):
    if len(args) < 2:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="write_file", count=2, signature="[path, content]"))

    raw_path = args[0]
    content = args[1]

    target_path = ctx.resolve_path(raw_path)

    old_content = ""
    if target_path.exists():
        try:
            old_content = target_path.read_text(encoding="utf-8")
        except Exception:
            old_content = "[Binary or Unreadable]"

    ctx.request_confirmation(target_path, old_content, content)

    try:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(content, encoding="utf-8")
    except PermissionError:
        ctx.fail(bus.get("acts.basic.error.writePermission", path=raw_path))
    except Exception as e:
        ctx.fail(bus.get("acts.basic.error.writeUnknown", error=e))

    bus.success("acts.basic.success.fileWritten", path=target_path.relative_to(ctx.root_dir))


def _patch_file(ctx: ActContext, args: List[str]):
    if len(args) < 3:
        ctx.fail(
            bus.get(
                "acts.error.missingArgs", act_name="patch_file", count=3, signature="[path, old_string, new_string]"
            )
        )

    raw_path, old_str, new_str = args[0], args[1], args[2]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        ctx.fail(bus.get("acts.basic.error.fileNotFound", path=raw_path))

    try:
        content = target_path.read_text(encoding="utf-8")
    except Exception as e:
        ctx.fail(bus.get("acts.basic.error.readFailed", path=raw_path, error=e))

    match_count = content.count(old_str)
    if match_count == 0:
        ctx.fail(bus.get("acts.basic.error.patchContentMismatch", path=raw_path))
    elif match_count > 1:
        ctx.fail(bus.get("acts.basic.error.patchContentAmbiguous", path=raw_path, count=match_count))

    new_content = content.replace(old_str, new_str, 1)

    ctx.request_confirmation(target_path, content, new_content)

    try:
        target_path.write_text(new_content, encoding="utf-8")
    except PermissionError:
        ctx.fail(bus.get("acts.basic.error.patchPermission", path=raw_path))
    except Exception as e:
        ctx.fail(bus.get("acts.basic.error.patchUnknown", error=e))

    bus.success("acts.basic.success.filePatched", path=target_path.relative_to(ctx.root_dir))


def _append_file(ctx: ActContext, args: List[str]):
    if len(args) < 2:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="append_file", count=2, signature="[path, content]"))

    raw_path, content_to_append = args[0], args[1]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        ctx.fail(bus.get("acts.basic.error.fileNotFound", path=raw_path))

    old_content = ""
    try:
        old_content = target_path.read_text(encoding="utf-8")
    except Exception:
        old_content = "[Binary or Unreadable]"

    new_content = old_content + content_to_append

    ctx.request_confirmation(target_path, old_content, new_content)

    try:
        with open(target_path, "a", encoding="utf-8") as f:
            f.write(content_to_append)
    except PermissionError:
        ctx.fail(bus.get("acts.basic.error.appendPermission", path=raw_path))
    except Exception as e:
        ctx.fail(bus.get("acts.basic.error.appendUnknown", error=e))

    bus.success("acts.basic.success.fileAppended", path=target_path.relative_to(ctx.root_dir))
