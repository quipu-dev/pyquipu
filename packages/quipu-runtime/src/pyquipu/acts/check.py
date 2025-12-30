import logging
import os
from pathlib import Path
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    executor.register("check_files_exist", _check_files_exist, arg_mode="exclusive")
    executor.register("check_cwd_match", _check_cwd_match, arg_mode="exclusive")


def _check_files_exist(ctx: ActContext, args: List[str]):
    if len(args) < 1:
        ctx.fail(
            bus.get("acts.error.missingArgs", act_name="check_files_exist", count=1, signature="[file_list_string]")
        )

    raw_files = args[0].strip().split("\n")
    missing_files = []

    for raw_path in raw_files:
        clean_path = raw_path.strip()
        if not clean_path:
            continue

        target_path = ctx.resolve_path(clean_path)
        if not target_path.exists():
            missing_files.append(clean_path)

    if missing_files:
        file_list_str = "\n".join(f"  - {f}" for f in missing_files)
        ctx.fail(bus.get("acts.check.error.filesMissing", file_list=file_list_str))

    bus.success("acts.check.success.filesExist")


def _check_cwd_match(ctx: ActContext, args: List[str]):
    if len(args) < 1:
        ctx.fail(
            bus.get("acts.error.missingArgs", act_name="check_cwd_match", count=1, signature="[expected_absolute_path]")
        )

    expected_path_str = args[0].strip()
    current_root = ctx.root_dir.resolve()
    expected_path = Path(os.path.expanduser(expected_path_str)).resolve()

    if current_root != expected_path:
        ctx.fail(bus.get("acts.check.error.cwdMismatch", expected=expected_path, actual=current_root))

    bus.success("acts.check.success.cwdMatched", path=current_root)
