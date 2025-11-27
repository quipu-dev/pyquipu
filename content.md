好的，分析收到了。

你的分析是正确的。目前的可达性判断确实只考虑了祖先节点，缺少了后代节点，导致在检出到旧节点时，其后续的分支被错误地标记为不可达。这是一个逻辑缺陷。

我们将通过以下步骤修复这个问题，确保可达性分析包含当前节点的祖先和所有后代，从而在 `quipu ui` 中正确地高亮整个分支。

## fix: 修复可达性分析，使其包含后代节点

### 错误分析
当前 `GraphViewModel` 在初始化时，只调用了 `reader.get_ancestor_output_trees` 方法来计算可达节点集合。这导致了可达性判断是单向的，只能从当前节点回溯历史。当用户检出一个较早的节点时，所有从该节点派生出的新节点（即后代）都不在该集合内，因此在 UI 中被渲染为不可达状态。

### 用户需求
用户希望在 `quipu ui` 中，当检出到任意一个节点时，所有与该节点有直接血缘关系（无论是祖先还是后代）的节点都应该被高亮为“可达”。

### 评论
这是一个很明确的 Bug 修复。修复后将显著提升 `quipu ui` 在历史分支间导航时的体验，使其行为更符合直觉。

### 目标
1.  扩展 `HistoryReader` 接口，增加一个用于查找所有后代节点的方法。
2.  在 `SQLiteHistoryReader` 和 `GitObjectHistoryReader` 中实现该方法。
3.  更新 `GraphViewModel`，使其在计算可达性时，合并祖先和后代两个集合。

### 基本原理
我们将采用与 `get_ancestor_output_trees` 类似的策略来实现 `get_descendant_output_trees`。对于 SQLite 后端，我们会使用另一个递归 `CTE` 查询来高效地遍历图的“向下”关系（从父到子）。对于 Git Object 后端，我们会在内存中遍历图的 `children` 属性。最后，在 `ViewModel` 中将祖先集、后代集和当前节点本身合并，形成完整的可达节点集。

### 标签
#intent/fix #flow/ready #priority/high #comp/engine #comp/cli #concept/history #scope/ux #ai/instruct #task/domain/ui #task/object/reachability #task/action/bug-fix #task/state/begin

---

### Script

#### Acts 1: 更新接口定义

首先，我们在 `HistoryReader` 接口中添加 `get_descendant_output_trees` 方法，以确保架构的清晰和一致。

~~~~~act
patch_file
packages/quipu-interfaces/src/quipu/core/storage.py
~~~~~
~~~~~python
    @abstractmethod
    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """
        获取指定节点的私有数据 (如 intent.md)。
        """
        pass
~~~~~
~~~~~python
    @abstractmethod
    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """
        获取指定节点的私有数据 (如 intent.md)。
        """
        pass

    @abstractmethod
    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        获取指定状态节点的所有后代节点的 output_tree 哈希集合。
        """
        pass
~~~~~

#### Acts 2: 在 GitObject 后端实现接口

接着，我们在 `GitObjectHistoryReader` 中为这个新接口提供一个基于内存图遍历的实现。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~
~~~~~python
    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """Git后端: 不支持私有数据"""
        return None
~~~~~
~~~~~python
    def get_private_data(self, node_commit_hash: str) -> Optional[str]:
        """Git后端: 不支持私有数据"""
        return None

    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """Git后端: 在内存中遍历图谱以查找后代"""
        all_nodes = self.load_all_nodes()
        node_map = {n.output_tree: n for n in all_nodes}

        descendants = set()
        queue = []

        if start_output_tree_hash in node_map:
            queue.append(node_map[start_output_tree_hash])

        while queue:
            current_node = queue.pop(0)
            for child in current_node.children:
                c_hash = child.output_tree
                if c_hash not in descendants:
                    descendants.add(c_hash)
                    queue.append(child)

        return descendants
~~~~~

#### Acts 3: 在 SQLite 后端实现接口

现在，我们在 `SQLiteHistoryReader` 中提供一个高效的、基于 SQL 递归查询的实现。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        获取指定状态节点的所有祖先节点的 output_tree 哈希集合 (用于可达性分析)。
        使用三步策略：
        1. 将 output_tree 哈希翻译为 commit_hash。
        2. 使用递归 CTE 查找所有祖先的 commit_hash。
        3. 将祖先 commit_hash 集合翻译回 output_tree 哈希集合。
        """
~~~~~
~~~~~python
    def get_descendant_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        获取指定状态节点的所有后代节点的 output_tree 哈希集合。
        与 get_ancestors 逻辑相反。
        """
        conn = self.db_manager._get_conn()
        try:
            # 1. 查找起点的 commit_hash
            cursor = conn.execute("SELECT commit_hash FROM nodes WHERE output_tree = ?", (start_output_tree_hash,))
            row = cursor.fetchone()
            if not row:
                return set()
            start_commit_hash = row[0]

            # 2. 使用递归 CTE 查找所有后代 commit_hash
            sql = """
            WITH RECURSIVE descendants(h) AS (
                SELECT child_hash FROM edges WHERE parent_hash = ?
                UNION ALL
                SELECT e.child_hash FROM edges e, descendants d WHERE e.parent_hash = d.h AND e.child_hash IS NOT NULL
            )
            SELECT h FROM descendants WHERE h IS NOT NULL;
            """
            cursor = conn.execute(sql, (start_commit_hash,))
            descendant_commit_hashes = {row[0] for row in cursor.fetchall()}

            if not descendant_commit_hashes:
                return set()

            # 3. 将 commit_hash 集合转换为 output_tree 集合
            placeholders = ",".join("?" * len(descendant_commit_hashes))
            sql_out = f"SELECT output_tree FROM nodes WHERE commit_hash IN ({placeholders})"
            cursor = conn.execute(sql_out, tuple(descendant_commit_hashes))
            return {row[0] for row in cursor.fetchall()}

        except sqlite3.Error as e:
            logger.error(f"Failed to get descendants for {start_output_tree_hash[:7]}: {e}")
            return set()

    def get_ancestor_output_trees(self, start_output_tree_hash: str) -> Set[str]:
        """
        获取指定状态节点的所有祖先节点的 output_tree 哈希集合 (用于可达性分析)。
        使用三步策略：
        1. 将 output_tree 哈希翻译为 commit_hash。
        2. 使用递归 CTE 查找所有祖先的 commit_hash。
        3. 将祖先 commit_hash 集合翻译回 output_tree 哈希集合。
        """
~~~~~

#### Acts 4: 更新 ViewModel 以使用新逻辑

最后，我们更新 `GraphViewModel` 来调用新方法，并将祖先和后代集合并，形成完整的可达性集合。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/view_model.py
~~~~~
~~~~~python
        # 状态属性
        self.total_nodes: int = 0
        self.total_pages: int = 1
        self.current_page: int = 0  # 页码从 1 开始
        self.ancestor_set: Set[str] = set()
~~~~~
~~~~~python
        # 状态属性
        self.total_nodes: int = 0
        self.total_pages: int = 1
        self.current_page: int = 0  # 页码从 1 开始
        self.reachable_set: Set[str] = set()
~~~~~
~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/view_model.py
~~~~~
~~~~~python
        if self.current_output_tree_hash:
            # 后端直接计算祖先，避免在前端加载整个图谱
            self.ancestor_set = self.reader.get_ancestor_output_trees(self.current_output_tree_hash)
            # 当前节点本身也是可达的
            self.ancestor_set.add(self.current_output_tree_hash)

    def is_reachable(self, output_tree_hash: str) -> bool:
        """检查一个节点哈希是否在可达性集合中。"""
        if not self.current_output_tree_hash:
            # 如果没有当前状态 (例如，在创世之前)，将所有内容视为可达，
            # 以避免 UI 显示全灰色。
            return True
        return output_tree_hash in self.ancestor_set
~~~~~
~~~~~python
        if self.current_output_tree_hash:
            # 后端直接计算祖先和后代，避免在前端加载整个图谱
            ancestors = self.reader.get_ancestor_output_trees(self.current_output_tree_hash)
            descendants = self.reader.get_descendant_output_trees(self.current_output_tree_hash)
            
            # 合并祖先、后代和当前节点自身，形成完整的可达集合
            self.reachable_set = ancestors.union(descendants)
            self.reachable_set.add(self.current_output_tree_hash)

    def is_reachable(self, output_tree_hash: str) -> bool:
        """检查一个节点哈希是否在可达性集合中。"""
        if not self.current_output_tree_hash:
            # 如果没有当前状态 (例如，在创世之前)，将所有内容视为可达，
            # 以避免 UI 显示全灰色。
            return True
        return output_tree_hash in self.reachable_set
~~~~~

### 下一步建议
这个计划已经准备就绪，可以执行。执行完毕后，`quipu ui` 的可达性高亮行为将符合预期。
