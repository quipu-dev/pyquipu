import logging
import shutil
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    executor.register("move_file", _move_file, arg_mode="hybrid")
    executor.register("delete_file", _delete_file, arg_mode="exclusive")


def _move_file(ctx: ActContext, args: List[str]):
    if len(args) < 2:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="move_file", count=2, signature="[src, dest]"))

    src_raw, dest_raw = args[0], args[1]
    src_path = ctx.resolve_path(src_raw)
    dest_path = ctx.resolve_path(dest_raw)

    if not src_path.exists():
        ctx.fail(bus.get("acts.refactor.error.srcNotFound", path=src_raw))

    msg = f"Move: {src_raw} -> {dest_raw}"
    ctx.request_confirmation(src_path, "Source Exists", msg)

    try:
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_path), str(dest_path))
    except PermissionError:
        ctx.fail(bus.get("acts.refactor.error.movePermission", src=src_raw, dest=dest_raw))
    except Exception as e:
        ctx.fail(bus.get("acts.refactor.error.moveUnknown", error=e))
    bus.success("acts.refactor.success.moved", source=src_raw, destination=dest_raw)


def _delete_file(ctx: ActContext, args: List[str]):
    if len(args) < 1:
        ctx.fail(bus.get("acts.error.missingArgs", act_name="delete_file", count=1, signature="[path]"))

    raw_path = args[0]
    target_path = ctx.resolve_path(raw_path)

    if not target_path.exists():
        bus.warning("acts.refactor.warning.deleteSkipped", path=raw_path)
        return

    file_type = "目录 (递归删除!)" if target_path.is_dir() else "文件"
    warning = f"🚨 正在删除{file_type}: {target_path}"

    ctx.request_confirmation(target_path, "EXISTING CONTENT", warning)

    try:
        if target_path.is_dir():
            shutil.rmtree(target_path)
        else:
            target_path.unlink()
    except PermissionError:
        ctx.fail(bus.get("acts.refactor.error.deletePermission", path=raw_path))
    except Exception as e:
        ctx.fail(bus.get("acts.refactor.error.deleteUnknown", error=e))

    bus.success("acts.refactor.success.deleted", path=raw_path)
