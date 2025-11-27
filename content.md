好的，我们开始重构 `GraphViewModel` 以支持传统分页模型，为后续的 UI 开发铺平道路。

这是一个必要的重构，目的是使 `ViewModel` 的接口与 `99_CURRENT_当前任务.md` 中定义的 UI 分页交互模型（上一页/下一页）保持一致。

## refactor: 重构 ViewModel 以支持传统分页

### 用户需求
当前 `packages/quipu-cli/src/quipu/cli/view_model.py` 中 `GraphViewModel` 的实现是基于“无限滚动”模型 (`load_next_page`)，只能不断向后加载数据。然而，UI 升级方案要求实现传统的“上一页”/“下一页”分页功能。因此，需要重构 `ViewModel` 以支持按页码加载。

### 评论
这是一个关键的准备步骤，用于解耦数据逻辑和 UI 展现。完成此重构后，UI 适配工作将可以顺利进行。

### 目标
1.  将 `GraphViewModel` 的分页逻辑从增量加载 (`offset`) 修改为按页码加载。
2.  引入 `page_size`, `total_pages`, `current_page` 等状态属性。
3.  实现核心方法 `load_page(page_number: int)` 来替代 `load_next_page()`。
4.  确保其他接口 (`initialize`, `is_reachable`, `get_content_bundle`) 保持不变。

### 基本原理
遵循 MVVM 设计模式，将分页的状态管理和数据获取逻辑完全封装在 `ViewModel` 中。`View` (TUI) 层只需调用如 `load_page(2)` 这样的高级指令，而无需关心 `limit` 和 `offset` 的计算细节。这使得 UI 层的代码更简洁，且逻辑更清晰。

### 标签
#intent/refine #flow/ready #priority/high
#comp/cli #concept/ui #scope/core
#ai/instruct
#task/state/continue #task-status/active

---

### Script

#### Acts 1: 重构 ViewModel 实现

将 `view_model.py` 的内容完全替换为支持分页的新实现。

~~~~~act
patch_file
~~~~~
~~~~~path
packages/quipu-cli/src/quipu/cli/view_model.py
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
~~~~~python
import math
from typing import List, Optional, Set

from quipu.core.models import QuipuNode
from quipu.core.storage import HistoryReader


class GraphViewModel:
    """
    一个 ViewModel，用于解耦 TUI (View) 和 HistoryReader (Model)。

    它负责管理分页状态、缓存可达性数据，并为 UI 提供简洁的数据接口。
    """

    def __init__(self, reader: HistoryReader, current_hash: Optional[str], page_size: int = 50):
        self.reader = reader
        self.current_hash = current_hash
        self.page_size = page_size

        # 状态属性
        self.total_nodes: int = 0
        self.total_pages: int = 1
        self.current_page: int = 0  # 页码从 1 开始
        self.ancestor_set: Set[str] = set()

    def initialize(self):
        """
        初始化 ViewModel，获取总数并计算可达性缓存。
        这是一个快速操作，因为它不加载任何节点内容。
        """
        self.total_nodes = self.reader.get_node_count()
        if self.page_size > 0 and self.total_nodes > 0:
            self.total_pages = math.ceil(self.total_nodes / self.page_size)
        else:
            self.total_pages = 1

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

    def load_page(self, page_number: int) -> List[QuipuNode]:
        """
        加载指定页码的数据，更新内部状态，并返回该页的节点列表。
        """
        if not (1 <= page_number <= self.total_pages):
            return []  # 页码无效

        self.current_page = page_number
        offset = (self.current_page - 1) * self.page_size

        nodes = self.reader.load_nodes_paginated(limit=self.page_size, offset=offset)
        return nodes

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

### 下一步建议
`ViewModel` 已准备就绪。下一步是实施**阶段三：前端 UI 适配**，修改 `packages/quipu-cli/src/quipu/cli/tui.py` 文件，使其能够使用新的 `GraphViewModel` 来实现分页加载。
