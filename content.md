好的，我们进入第四阶段，对数据持久化和补水层进行核心改造，以支持多用户元数据。

这是一个关键的步骤，它将 Git 物理层面的引用结构（`refs/.../<user_id>/...`）与 SQLite 逻辑层面的数据模型连接起来，为 UI 实现多用户可视化奠定基础。

## feat(engine): 扩展数据模型与补水器以支持所有权

### 用户需求
根据 `Quipu Sync 功能开发任务列表`，需要执行任务 4.1, 4.2 和 4.3：
1.  **扩展数据模型**: 在 `quipu-interfaces` 的 `QuipuNode` 中增加一个可选的 `owner_id` 字段。
2.  **升级数据库 Schema**: 在 `quipu-engine` 的 `nodes` 表中增加 `owner_id` 列，并更新相应的写入方法。
3.  **重构 Hydrator**: 使补水器能够从 Git 引用的路径中解析出 commit 的所有者 (`owner_id`)，并将其存入数据库。

### 评论
这是实现“多维平行宇宙”架构在数据层面闭环的核心工作。通过将 `owner_id` 引入数据模型和数据库，我们赋予了每个历史节点明确的归属。这使得 `Hydrator` 的角色从一个简单的“数据搬运工”升级为能够理解分布式元数据的“信息整合器”，为后续在 UI 层实现按作者着色、过滤等高级功能提供了坚实的数据基础。

### 目标
1.  在 `QuipuNode` (interfaces) 中添加 `owner_id` 属性。
2.  在 `sqlite_db.py` (engine) 中，更新 `nodes` 表的 `CREATE` 语句和 `batch_insert_nodes` 的 `INSERT` 语句以包含 `owner_id`。
3.  修改 `git_db.py` 中的 `get_all_ref_heads` 方法，使其能返回 commit 哈希及其来源的 ref 名称。
4.  彻底重构 `hydrator.py` (engine)，使其能够解析 ref 名称以提取 `owner_id`，并将这些信息传递给数据库。
5.  调整 `state_machine.py` 中的 `align` 方法，以在调用补水器时提供必要的 `user_id` 上下文。

### 基本原理
-   **所有权源头**: `owner_id` 的唯一事实来源是 Git ref 的路径。例如，来自 `refs/quipu/remotes/origin/alice/heads/...` 的 commit，其所有者即为 `alice`。对于 `refs/quipu/local/heads/...`，其所有者是当前本地配置的 `user_id`。
-   **数据流**: `git for-each-ref` -> `Hydrator` (解析 ref 路径) -> `(commit_hash, owner_id)` 元组 -> `SQLite nodes 表`。
-   **解耦**: `Hydrator` 负责从 Git 原始数据中提取并丰富元数据，`SQLiteHistoryReader` 则直接消费这些处理好的、结构化的数据，实现了读写分离和关注点分离。

### 标签
#intent/build #intent/refine #flow/ready #priority/high 
#comp/engine #comp/interfaces 
#concept/sync #concept/history #scope/core #scope/api 
#ai/instruct
#task/domain/sync #task/object/ownership #task/action/implementation #task-state/continue

---

### Script

#### Acts 1: 扩展 QuipuNode 接口 (interfaces)

在 `QuipuNode` dataclass 中增加 `owner_id` 字段。

~~~~~act
patch_file
packages/quipu-interfaces/src/quipu/core/models.py
~~~~~
~~~~~python
    # 从元数据或内容生成的单行摘要
    summary: str = ""

    # --- 图遍历字段 (由加载器填充) ---
    parent: Optional[QuipuNode] = None
~~~~~
~~~~~python
    # 从元数据或内容生成的单行摘要
    summary: str = ""

    # 所有者 ID，从 Git Ref 或数据库中填充
    owner_id: Optional[str] = None

    # --- 图遍历字段 (由加载器填充) ---
    parent: Optional[QuipuNode] = None
~~~~~

#### Acts 2: 升级数据库 Schema 和写入方法 (engine)

更新 `sqlite_db.py` 以支持 `owner_id` 列。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/sqlite_db.py
~~~~~
~~~~~python
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nodes (
                        commit_hash TEXT(40) PRIMARY KEY,
                        output_tree TEXT(40) NOT NULL,
                        node_type TEXT NOT NULL,
~~~~~
~~~~~python
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS nodes (
                        commit_hash TEXT(40) PRIMARY KEY,
                        owner_id TEXT,
                        output_tree TEXT(40) NOT NULL,
                        node_type TEXT NOT NULL,
~~~~~

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/sqlite_db.py
~~~~~
~~~~~python
    def batch_insert_nodes(self, nodes: List[Tuple]):
        """批量插入节点。"""
        conn = self._get_conn()
        sql = """
            INSERT OR IGNORE INTO nodes 
            (commit_hash, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with conn:
                conn.executemany(sql, nodes)
~~~~~
~~~~~python
    def batch_insert_nodes(self, nodes: List[Tuple]):
        """批量插入节点。"""
        conn = self._get_conn()
        sql = """
            INSERT OR IGNORE INTO nodes 
            (commit_hash, owner_id, output_tree, node_type, timestamp, summary, generator_id, meta_json, plan_md_cache)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        try:
            with conn:
                conn.executemany(sql, nodes)
~~~~~

#### Acts 3: 增强 GitDB 的 Ref 查询能力 (engine)

修改 `get_all_ref_heads` 以返回 ref 名称，这对解析 `owner_id` 至关重要。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
    def get_all_ref_heads(self, prefix: str) -> List[str]:
        """查找指定前缀下的所有 ref heads 并返回其 commit 哈希。"""
        res = self._run(["for-each-ref", f"--format=%(objectname)", prefix], check=False)
        if res.returncode != 0 or not res.stdout.strip():
            return []
        return res.stdout.strip().splitlines()
~~~~~
~~~~~python
    def get_all_ref_heads(self, prefix: str) -> List[Tuple[str, str]]:
        """
        查找指定前缀下的所有 ref heads。
        返回 (commit_hash, ref_name) 元组列表。
        """
        res = self._run(["for-each-ref", f"--format=%(objectname) %(refname)", prefix], check=False)
        if res.returncode != 0 or not res.stdout.strip():
            return []
        
        results = []
        for line in res.stdout.strip().splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                results.append((parts[0], parts[1]))
        return results
~~~~~

#### Acts 4: 适配 `GitObjectHistoryReader` (engine)

由于上一步修改了 `get_all_ref_heads` 的返回值，我们需要更新调用点。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~
~~~~~python
        # Step 1: Get Commits
        all_heads = self.git_db.get_all_ref_heads("refs/quipu/")
        if not all_heads:
            return []

        log_entries = self.git_db.log_ref(all_heads)
~~~~~
~~~~~python
        # Step 1: Get Commits
        ref_tuples = self.git_db.get_all_ref_heads("refs/quipu/")
        if not ref_tuples:
            return []
        
        all_heads = list(set(t[0] for t in ref_tuples))
        log_entries = self.git_db.log_ref(all_heads)
~~~~~

#### Acts 5: 重构 Hydrator 以处理所有权 (engine)

这是核心修改。我们将重写 `Hydrator` 的大部分逻辑。

~~~~~act
write_file
packages/quipu-engine/src/quipu/core/hydrator.py
~~~~~
~~~~~python
import json
import logging
import re
from typing import List, Dict, Set, Tuple, Optional

from .git_db import GitDB
from .sqlite_db import DatabaseManager
from .git_object_storage import GitObjectHistoryReader  # Reuse parsing logic

logger = logging.getLogger(__name__)


class Hydrator:
    """
    负责将 Git 对象历史记录同步（补水）到 SQLite 数据库。
    """

    def __init__(self, git_db: GitDB, db_manager: DatabaseManager):
        self.git_db = git_db
        self.db_manager = db_manager
        # 复用 Reader 中的二进制解析逻辑，避免代码重复
        self._parser = GitObjectHistoryReader(git_db)

    def _get_owner_from_ref(self, ref_name: str, local_user_id: str) -> Optional[str]:
        """从 Git ref 路径中解析 owner_id。"""
        # 匹配 remote 镜像: refs/quipu/remotes/<remote_name>/<user_id>/heads/...
        remote_match = re.match(r"refs/quipu/remotes/[^/]+/([^/]+)/heads/.*", ref_name)
        if remote_match:
            return remote_match.group(1)

        # 匹配 local heads
        if ref_name.startswith("refs/quipu/local/heads/"):
            return local_user_id

        return None

    def _get_missing_commits_with_owner(self, local_user_id: str) -> Dict[str, str]:
        """
        计算 Git 中存在但 SQLite 缺失的 commit，并确定其所有者。
        返回 {commit_hash: owner_id} 字典。
        """
        logger.debug("正在计算需要补水的 Commit 及其所有者...")
        ref_tuples = self.git_db.get_all_ref_heads("refs/quipu/")
        if not ref_tuples:
            return {}

        commit_to_owner: Dict[str, str] = {}
        for commit_hash, ref_name in ref_tuples:
            # 一个 commit 可能被多个 ref 指向 (e.g., local 和 remote mirror)
            # 只要能确定一个所有者即可。
            if commit_hash in commit_to_owner:
                continue
            
            owner_id = self._get_owner_from_ref(ref_name, local_user_id)
            if owner_id:
                commit_to_owner[commit_hash] = owner_id

        if not commit_to_owner:
            return {}

        db_hashes = self.db_manager.get_all_node_hashes()
        
        missing_commits = {
            commit: owner for commit, owner in commit_to_owner.items() if commit not in db_hashes
        }
        
        logger.info(f"发现 {len(missing_commits)} 个需要补水的节点。")
        return missing_commits

    def sync(self, local_user_id: str):
        """
        执行增量补水操作。
        """
        missing_commits = self._get_missing_commits_with_owner(local_user_id)
        if not missing_commits:
            logger.debug("✅ 数据库与 Git 历史一致，无需补水。")
            return

        missing_hashes = list(missing_commits.keys())
        all_git_logs = self.git_db.log_ref(missing_hashes) # Log only missing commits for efficiency
        log_map = {entry["hash"]: entry for entry in all_git_logs}

        # --- 批量准备数据 ---
        nodes_to_insert: List[Tuple] = []
        edges_to_insert: List[Tuple] = []

        # 1. 批量获取 Trees
        tree_hashes = [log_map[h]["tree"] for h in missing_hashes if h in log_map]
        trees_content = self.git_db.batch_cat_file(tree_hashes)

        # 2. 解析 Trees, 批量获取 Metas
        tree_to_meta_blob: Dict[str, str] = {}
        meta_blob_hashes: List[str] = []
        for tree_hash, content_bytes in trees_content.items():
            entries = self._parser._parse_tree_binary(content_bytes)
            if "metadata.json" in entries:
                blob_hash = entries["metadata.json"]
                tree_to_meta_blob[tree_hash] = blob_hash
                meta_blob_hashes.append(blob_hash)

        metas_content = self.git_db.batch_cat_file(meta_blob_hashes)

        # 3. 构建插入数据
        for commit_hash in missing_hashes:
            if commit_hash not in log_map: continue
            
            log_entry = log_map[commit_hash]
            tree_hash = log_entry["tree"]
            owner_id = missing_commits[commit_hash]

            meta_blob_hash = tree_to_meta_blob.get(tree_hash)
            if not meta_blob_hash:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 metadata.json")
                continue

            meta_bytes = metas_content.get(meta_blob_hash)
            if not meta_bytes:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 metadata blob")
                continue

            output_tree = self._parser._parse_output_tree_from_body(log_entry["body"])
            if not output_tree:
                logger.warning(f"跳过 {commit_hash[:7]}: 找不到 Output-Tree trailer")
                continue

            try:
                meta_data = json.loads(meta_bytes)
                nodes_to_insert.append(
                    (
                        commit_hash,
                        owner_id,
                        output_tree,
                        meta_data.get("type", "unknown"),
                        float(meta_data.get("exec", {}).get("start") or log_entry["timestamp"]),
                        meta_data.get("summary", "No summary"),
                        meta_data.get("generator", {}).get("id"),
                        meta_bytes.decode("utf-8"),
                        None,  # plan_md_cache is NULL for cold data
                    )
                )

                # 处理边关系
                parent_hashes = log_entry["parent"].split()
                for p_hash in parent_hashes:
                    edges_to_insert.append((commit_hash, p_hash))
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"解析 {commit_hash[:7]} 的元数据失败: {e}")

        # --- 批量写入数据库 ---
        if nodes_to_insert:
            self.db_manager.batch_insert_nodes(nodes_to_insert)
            logger.info(f"💧 {len(nodes_to_insert)} 个节点元数据已补水。")
        if edges_to_insert:
            self.db_manager.batch_insert_edges(edges_to_insert)
            logger.info(f"💧 {len(edges_to_insert)} 条边关系已补水。")
~~~~~

#### Acts 6: 更新 Engine 的 `align` 方法 (engine)

最后，我们需要让 `Engine.align` 在调用补水器时，传入 `user_id`。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/state_machine.py
~~~~~
~~~~~python
    def align(self) -> str:
        # 如果使用 SQLite，先进行数据补水
        if self.db_manager:
            try:
                hydrator = Hydrator(self.git_db, self.db_manager)
                hydrator.sync()
            except Exception as e:
                logger.error(f"❌ 自动数据补水失败: {e}", exc_info=True)

        all_nodes = self.reader.load_all_nodes()
~~~~~
~~~~~python
    def align(self) -> str:
        # 如果使用 SQLite，先进行数据补水
        if self.db_manager:
            try:
                config = ConfigManager(self.root_dir)
                user_id = config.get("sync.user_id")
                if not user_id:
                    # 在 align 阶段，我们假设 user_id 应该已经存在。
                    # 如果不存在（例如，用户从未运行过 sync），补水器将无法正确识别本地节点所有者。
                    # 这是一个合理的回退，因为在 sync 之前，所有节点都应该是本地的。
                    logger.debug("补水时未找到 user_id，本地所有权可能无法确定。")
                    user_id = "unknown-local-user"

                hydrator = Hydrator(self.git_db, self.db_manager)
                hydrator.sync(local_user_id=user_id)
            except Exception as e:
                logger.error(f"❌ 自动数据补水失败: {e}", exc_info=True)

        all_nodes = self.reader.load_all_nodes()
~~~~~

### 下一步建议
我们已经完成了数据后端的改造。现在，数据库（如果使用 SQLite）中已经包含了 `owner_id` 信息。

下一步是让读取和展示层能够利用这些新信息。我们将执行任务 **4.4 和 5.1**。
