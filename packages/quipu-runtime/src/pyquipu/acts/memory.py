import logging
from datetime import datetime
from typing import List

from pyquipu.common.messaging import bus
from pyquipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    executor.register("log_thought", _log_thought, arg_mode="block_only")


def _log_thought(ctx: ActContext, args: List[str]):
    if len(args) < 1:
        ctx.fail(bus.get("acts.memory.error.missingContent"))

    content = args[0]

    memory_dir = ctx.root_dir / ".quipu"
    memory_dir.mkdir(exist_ok=True)

    memory_file = memory_dir / "memory.md"

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n## [{timestamp}]\n{content}\n"

    try:
        with open(memory_file, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        ctx.fail(bus.get("acts.memory.error.writeFailed", error=e))

    bus.success("acts.memory.success.thoughtLogged")
