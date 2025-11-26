# fix: 修正 `view_model.py` 的文件路径

## 错误分析
`pytest` 在收集测试文件 `tests/test_view_model.py` 时报告了 `ModuleNotFoundError: No module named 'quipu.cli.view_model'`。

经过分析，根本原因是我在上一条指令中提供的 `write_file` 路径不正确。我指定的路径是 `src/quipu/cli/view_model.py`，这导致文件被错误地创建在了项目的根目录下的 `src` 文件夹。

根据 `pyproject.toml` 中为 `pytest` 配置的 `pythonpath` (`packages/quipu-cli/src`)，正确的位置应该是 `packages/quipu-cli/src/quipu/cli/view_model.py`。因为路径错误，Python 的导入系统无法找到该模块，导致测试收集失败。

## 用户需求
修正 `view_model.py` 文件的位置，使其符合项目结构和 `pytest` 的 `pythonpath` 配置，从而解决 `ModuleNotFoundError`。

## 评论
这是一个简单的路径错误，通过修正 `write_file` 指令的目标路径即可解决。这个修正将确保模块可以被正确导入，并使 `test_view_model.py` 能够被 `pytest` 正常收集和执行。

## 目标
1.  使用 `write_file` 指令，在正确的路径 `packages/quipu-cli/src/quipu/cli/view_model.py` 创建 `GraphViewModel` 模块。
2.  确保 `test_view_model.py` 的测试用例能够成功执行。

## 基本原理
通过将模块文件放置在 `pytest` `pythonpath` 所指定的 `packages/quipu-cli/src` 目录下的相应包结构中，我们确保了 `import quipu.cli.view_model` 语句能够被 Python 解析器正确处理。

## 标签
#intent/fix #flow/ready #priority/critical
#comp/cli #comp/build #scope/dx
#ai/instruct
#task/domain/ui #task/object/performance #task/action/bug-fix
#task/state/continue #task/status/active

---

### Script

#### Acts 1: 在正确的位置创建 ViewModel 文件

此操作将覆盖或创建 `view_model.py` 文件到正确的模块路径下。

~~~~~act
write_file packages/quipu-cli/src/quipu/cli/view_model.py
~~~~~
~~~~~python
from typing import List, Optional, Set

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader


class GraphViewModel:
    """
    一个 ViewModel，用于解耦 TUI (View) 和 HistoryReader (Model)。

    它负责管理分页加载状态、缓存可达性数据，并为 UI 提供简洁的数据接口。
    """

    def __init__(self, reader: HistoryReader, current_hash: Optional[str]):
        self.reader = reader
        self.current_hash = current_hash
        self.loaded_nodes: List[QuipuNode] = []
        self.ancestor_set: Set[str] = set()
        self.total_count: int = 0
        self.offset: int = 0

    def initialize(self):
        """
        初始化 ViewModel，获取总数并计算可达性缓存。
        这是一个快速操作，因为它不加载任何节点内容。
        """
        self.total_count = self.reader.get_node_count()
        if self.current_hash:
            # 后端直接计算祖先，避免在前端加载整个图谱
            self.ancestor_set = self.reader.get_ancestor_hashes(self.current_hash)
            # 当前节点本身也是可达的
            self.ancestor_set.add(self.current_hash)

    def is_reachable(self, node_hash: str) -> bool:
        """检查一个节点哈希是否在可达性集合中。"""
        if not self.current_hash:
            # 如果没有当前状态 (例如，在创世之前)，将所有内容视为可达，
            # 以避免 UI 显示全灰色。
            return True
        return node_hash in self.ancestor_set

    def has_more_data(self) -> bool:
        """检查是否还有更多数据可以从后端加载。"""
        if self.total_count == 0:
            return False
        return self.offset < self.total_count

    def load_next_page(self, size: int = 50) -> List[QuipuNode]:
        """
        加载下一页数据，更新内部状态，并返回新加载的节点列表。
        """
        if not self.has_more_data():
            return []

        new_nodes = self.reader.load_nodes_paginated(limit=size, offset=self.offset)
        self.loaded_nodes.extend(new_nodes)
        self.offset += len(new_nodes)
        return new_nodes

    def get_content_bundle(self, node: QuipuNode) -> str:
        """
        获取节点的公共内容和私有内容，并将它们格式化成一个单一的字符串用于展示。
        """
        public_content = self.reader.get_node_content(node) or ""
        private_content = self.reader.get_private_data(node.filename.name)

        if not public_content and not private_content:
            return "*此节点无详细内容*"

        # 构建最终的显示内容
        bundle = []
        if public_content:
            bundle.append("== 📜 公共计划内容=========")
            bundle.append(public_content.strip())

        if private_content is not None:
            if public_content:
                bundle.append("\n---\n")
            bundle.append("== 🧠 开发者意图===========")
            bundle.append(private_content.strip())
        elif public_content:
            # 仅当有公共内容时，才显示“无私有数据”的消息
            bundle.append("\n---\n")
            bundle.append("== 🧠 开发者意图===========")
            bundle.append("*此节点无私有数据或来自协作者*")

        return "\n\n".join(bundle)
~~~~~
