# refactor: 实现基于文件系统的旧版历史读写器

## 用户需求
根据存储层改造计划，需要将现有的、基于文件系统的历史记录读写逻辑，从 `Engine` 和 `history` 模块中剥离出来，封装成符合新定义的 `HistoryReader` 和 `HistoryWriter` 接口的具体实现类。

## 评论
这是解耦过程中的关键一步。通过创建这些具体的实现类，我们为后续在 `Engine` 中使用依赖注入替换它们铺平了道路。此步骤将旧有逻辑进行归集和封装，而不引入任何新功能，是一个纯粹的重构操作。

## 目标
1.  在 `quipu-engine` 包中创建一个新文件 `file_system_storage.py`。
2.  在该文件中，创建 `FileSystemHistoryReader` 类，它实现 `HistoryReader` 接口，并复用现有的 `history.load_all_history_nodes` 函数。
3.  在该文件中，创建 `FileSystemHistoryWriter` 类，它实现 `HistoryWriter` 接口，并封装从 `Engine` 中提取的、用于创建 `.md` 历史文件的逻辑。

## 基本原理
我们正在实施策略模式。`FileSystemHistoryReader` 和 `FileSystemHistoryWriter` 是我们针对“文件系统存储”这一策略的具体实现。这些类将所有与文件系统交互的细节（如文件名格式、YAML Frontmatter 的构建）封装起来，使得上层调用者 (`Engine`) 无需关心这些实现细节，只需与 `HistoryReader` 和 `HistoryWriter` 接口交互即可。

## 标签
#comp/engine #concept/history #scope/core

---

## Script

### Acts 1: 创建文件系统存储实现模块

在 `quipu-engine` 中创建新文件 `file_system_storage.py`，并添加 `FileSystemHistoryReader` 和 `FileSystemHistoryWriter` 两个类的实现。

~~~~~act
write_file
~~~~~

~~~~~path
packages/quipu-engine/src/quipu/core/file_system_storage.py
~~~~~

~~~~~python
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
~~~~~