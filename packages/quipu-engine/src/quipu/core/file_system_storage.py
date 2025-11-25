import logging
import yaml
from pathlib import Path
from datetime import datetime
from typing import List, Any

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader, HistoryWriter
from .history import load_all_history_nodes

logger = logging.getLogger(__name__)


class FileSystemHistoryReader(HistoryReader):
    """
    一个从文件系统 (.quipu/history/*.md) 读取历史的实现。
    """
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir

    def load_all_nodes(self) -> List[QuipuNode]:
        """
        通过调用现有的 `load_all_history_nodes` 函数来加载图谱。
        """
        return load_all_history_nodes(self.history_dir)


class FileSystemHistoryWriter(HistoryWriter):
    """
    一个将历史节点写入文件系统 (.quipu/history/*.md) 的实现。
    """
    def __init__(self, history_dir: Path):
        self.history_dir = history_dir
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def create_node(
        self,
        node_type: str,
        input_tree: str,
        output_tree: str,
        content: str,
        **kwargs: Any,
    ) -> QuipuNode:
        """
        在 history 目录中创建一个新的 .md 文件来持久化节点。
        """
        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d%H%M%S")
        filename = self.history_dir / f"{input_tree}_{output_tree}_{ts_str}.md"

        meta = {
            "type": node_type,
            "input_tree": input_tree,
            "output_tree": output_tree,
        }
        # 将 kwargs 中的额外元数据也合并进去
        meta.update(kwargs)

        # 确保 content 末尾有换行符，以分隔 frontmatter
        body = f"{content.strip()}\n"
        frontmatter = f"---\n{yaml.dump(meta, sort_keys=False)}---\n\n"

        try:
            filename.write_text(frontmatter + body, "utf-8")
            logger.debug(f"History node written to {filename}")
        except Exception as e:
            # 考虑在这里抛出一个自定义的 StorageWriteError
            logger.error(f"Failed to write history node to {filename}: {e}")
            raise

        return QuipuNode(
            input_tree=input_tree,
            output_tree=output_tree,
            timestamp=timestamp,
            filename=filename,
            node_type=node_type,
            content=body,
        )