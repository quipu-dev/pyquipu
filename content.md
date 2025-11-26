# refactor: 为 UI 实现 SQLite 分页与私有数据读取

## 用户需求
当前 `quipu ui` 在启动时会加载全部历史记录，当历史记录数量巨大时，会导致启动慢、内存占用高的问题。需要改造 UI 和数据读取层，实现按需分页加载（无限滚动），以达到“秒开”的效果。同时，需要增加在 UI 中展示与节点关联的私有“开发者意图” (`intent.md`) 的功能。

## 评论
这是一个关键的性能和功能增强。通过将 UI 与数据获取逻辑解耦，并充分利用 SQLite 的查询能力，可以极大地提升大规模项目下的用户体验。

## 目标
1.  实现 `quipu ui` 的按需分页加载，解决性能瓶颈。
2.  在 `quipu ui` 的内容预览区，增加对节点私有数据的展示。
3.  重构数据读取层，使其接口更适应分页查询模式。

## 基本原理
本次重构的核心思想是将数据读取逻辑从“一次性全量加载”转变为“按需分页获取”。

1.  **接口先行**: 在 `quipu-interfaces` 中扩展 `HistoryReader` 接口，定义分页查询、总数统计、祖先节点查询和私有数据读取等新契约。
2.  **后端实现**: 在 `quipu-engine` 的 `SQLiteHistoryReader` 中，利用 SQL 的 `LIMIT`, `OFFSET`, `COUNT(*)` 等功能高效实现新接口。同时，通过循环或递归查询 `edges` 表，在后端高效计算节点的可达性，避免在前端加载全量数据。
3.  **兼容性维护**: 为 `GitObjectHistoryReader` 提供新接口的低效（全量加载后切片）实现，以确保其在不使用 SQLite 时的兼容性。

## 标签
#intent/refine #intent/build #flow/ready #priority/high #comp/engine #comp/interfaces #concept/ui #concept/state #scope/core #scope/api #ai/instruct #task/domain/ui #task/object/pagination #task/action/integration #task/state/continue

---

## Script

### Acts 1: 扩展存储接口

首先，我们在 `quipu-interfaces` 中更新 `HistoryReader` 抽象基类，加入分页和私有数据读取所需的方法，为后续实现提供契约。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-interfaces/src/quipu/core/storage.py
~~~~~
~~~~~python
from abc import ABC, abstractmethod
from typing import List, Any, Optional, Set
import re
from .models import QuipuNode


class HistoryReader(ABC):
    """
    一个抽象接口，用于从存储后端读取历史图谱。
    """

    @abstractmethod
    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从存储中加载所有历史事件，构建完整的父子关系图，
        并返回所有节点的列表。
        注意：为了性能，实现可能会选择不立即加载节点的 content 内容。
        """
        pass

    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        """
        获取指定节点的完整内容 (Lazy Loading)。
        如果节点内容已加载，直接返回；否则从存储后端读取。
        """
        pass

    @abstractmethod
    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        """
        根据条件查找历史节点。
        """
        pass

    @abstractmethod
    def get_node_count(self) -> int:
        """
        获取历史节点总数。
        """
        pass

    @abstractmethod
    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """
        按需加载一页节点数据。
        注意：返回的节点应包含与直接父节点的关系，但不一定构建完整的全量图谱。
        """
        pass

    @abstractmethod
    def get_ancestor_hashes(self, commit_hash: str) -> Set[str]:
        """
        获取指定节点的所有祖先节点的哈希集合 (用于可达性分析)。
        """
        pass

    @abstractmethod
    def get_private_data(self, commit_hash: str) -> Optional[str]:
        """
        获取指定节点的私有数据 (如 intent.md)。
        """
        pass


class HistoryWriter(ABC):
~~~~~
~~~~~python
from abc import ABC, abstractmethod
from typing import List, Any, Optional, Set
import re
from .models import QuipuNode


class HistoryReader(ABC):
    """
    一个抽象接口，用于从存储后端读取历史图谱。
    """

    @abstractmethod
    def load_all_nodes(self) -> List[QuipuNode]:
        """
        从存储中加载所有历史事件，构建完整的父子关系图，
        并返回所有节点的列表。
        注意：为了性能，实现可能会选择不立即加载节点的 content 内容。
        """
        pass

    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        """
        获取指定节点的完整内容 (Lazy Loading)。
        如果节点内容已加载，直接返回；否则从存储后端读取。
        """
        pass

    @abstractmethod
    def find_nodes(
        self,
        summary_regex: Optional[str] = None,
        node_type: Optional[str] = None,
        limit: int = 10,
    ) -> List[QuipuNode]:
        """
        根据条件查找历史节点。
        """
        pass

    @abstractmethod
    def get_node_count(self) -> int:
        """
        获取历史节点总数。
        """
        pass

    @abstractmethod
    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """
        按需加载一页节点数据。
        注意：返回的节点应包含与直接父节点的关系，但不一定构建完整的全量图谱。
        """
        pass

    @abstractmethod
    def get_ancestor_hashes(self, commit_hash: str) -> Set[str]:
        """
        获取指定节点的所有祖先节点的哈希集合 (用于可达性分析)。
        """
        pass

    @abstractmethod
    def get_private_data(self, commit_hash: str) -> Optional[str]:
        """
        获取指定节点的私有数据 (如 intent.md)。
        """
        pass


class HistoryWriter(ABC):
~~~~~

### Acts 2: 在 SQLite 后端实现新接口

接下来，我们在 `quipu-engine` 中为 `SQLiteHistoryReader` 实现新定义的方法，使其真正具备分页查询和私有数据读取的能力。

~~~~~act
replace
~~~~~
~~~~~path
packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
    def get_node_count(self) -> int:
        # 待实现
        return 0

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        # 待实现
        return []

    def get_ancestor_hashes(self, commit_hash: str) -> Set[str]:
        # 待实现
        return set()

    def get_private_data(self, commit_hash: str) -> Optional[str]:
        # 待实现
        return None

    def get_node_content(self, node: QuipuNode) -> str:
        """
        实现通读缓存策略来获取节点内容。
~~~~~
~~~~~python
    def get_node_count(self) -> int:
        """从数据库获取历史节点总数。"""
        conn = self.db_manager._get_conn()
        cursor = conn.execute("SELECT COUNT(*) FROM nodes;")
        count = cursor.fetchone()
        return count

    def load_nodes_paginated(self, limit: int, offset: int) -> List[QuipuNode]:
        """按需从数据库加载一“页”节点数据。"""
        conn = self.db_manager._get_conn()

        # 步骤 1: 获取一页节点元数据
        nodes_cursor = conn.execute(
            "SELECT * FROM nodes ORDER BY timestamp DESC LIMIT ? OFFSET ?", (limit, offset)
        )
        nodes_data = nodes_cursor.fetchall()

        if not nodes_data:
            return []

        temp_nodes: Dict[str, QuipuNode] = {}
        commit_hashes_in_page = []
        for row in nodes_data:
            commit_hash = row["commit_hash"]
            node = QuipuNode(
                input_tree="",  # 稍后链接
                output_tree=row["output_tree"],
                timestamp=datetime.fromtimestamp(row["timestamp"]),
                filename=Path(f".quipu/git_objects/{commit_hash}"),
                node_type=row["node_type"],
                summary=row["summary"],
                content=row["plan_md_cache"] if row["plan_md_cache"] is not None else "",
            )
            temp_nodes[commit_hash] = node
            commit_hashes_in_page.append(commit_hash)

        # 步骤 2: 高效获取这些特定节点的关系
        placeholders = ",".join("?" for _ in commit_hashes_in_page)
        edges_cursor = conn.execute(
            f"SELECT child_hash, parent_hash FROM edges WHERE child_hash IN ({placeholders})",
            commit_hashes_in_page,
        )
        edges_data = edges_cursor.fetchall()

        # 步骤 3: 链接父节点
        # 这是一个简化的方法，足以渲染图谱线条。
        for row in edges_data:
            child_hash, parent_hash = row["child_hash"], row["parent_hash"]
            if child_hash in temp_nodes:
                parent_cursor = conn.execute("SELECT output_tree FROM nodes WHERE commit_hash = ?", (parent_hash,))
                parent_row = parent_cursor.fetchone()
                if parent_row:
                    temp_nodes[child_hash].input_tree = parent_row["output_tree"]

        return list(temp_nodes.values())

    def get_ancestor_hashes(self, commit_hash: str) -> Set[str]:
        """
        高效地使用 SQL 获取指定提交的所有祖先哈希。
        """
        conn = self.db_manager._get_conn()
        ancestors = set()
        queue = [commit_hash]

        while queue:
            current_hash = queue.pop(0)
            if current_hash in ancestors:
                continue

            cursor = conn.execute("SELECT parent_hash FROM edges WHERE child_hash = ?", (current_hash,))
            parents = [row for row in cursor.fetchall()]

            for parent_hash in parents:
                if parent_hash not in ancestors:
                    ancestors.add(parent_hash)
                    queue.append(parent_hash)

        return ancestors

    def get_private_data(self, commit_hash: str) -> Optional[str]:
        """从数据库获取指定节点的私有开发者意图数据。"""
        conn = self.db_manager._get_conn()
        cursor = conn.execute("SELECT intent_md FROM private_data WHERE node_hash = ?", (commit_hash,))
        row = cursor.fetchone()
        return row if row else None

    def get_node_content(self, node: QuipuNode) -> str:
        """
        实现通读缓存策略来获取节点内容。
~~~~~
