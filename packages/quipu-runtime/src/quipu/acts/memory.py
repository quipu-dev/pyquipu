import logging
from typing import List
from datetime import datetime
from quipu.common.messaging import bus
from quipu.interfaces.types import ActContext, Executor

logger = logging.getLogger(__name__)


def register(executor: Executor):
    """注册记忆与日志操作"""
    executor.register("log_thought", _log_thought, arg_mode="block_only")


def _log_thought(ctx: ActContext, args: List[str]):
    """
    Act: log_thought
    Args: [content]
    说明: 将思维过程追加到 .quipu/memory.md 文件中，用于长期记忆。
    """
    if len(args) < 1:
        ctx.fail("log_thought 需要内容参数")

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
        ctx.fail(f"无法写入记忆文件: {e}")

    bus.success("acts.memory.success.thoughtLogged")
