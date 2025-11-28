你完全正确，你的分析一针见血——“这个操作导致很多节点丢失了”。

`rebuild` 命令本身成功了，但它是在一个**已经不完整的历史**上成功的。第一次运行 `migrate-data` 的时候，虽然没有报错，但它实际上只迁移了一部分数据，导致了数据丢失。

这是一个非常隐蔽但严重的 Bug。我们来修复它。

## fix: 完善数据迁移以包含所有旧版引用，防止历史丢失

### 错误分析
1.  **根本原因**: 我之前设计的 `MigrationManager` 犯了一个致命的错误假设。它只查找并迁移了 `refs/quipu/heads/*` 下的引用。然而，Quipu 的旧版（v1.0）核心历史由一个名为 `refs/quipu/history` 的单一引用来维持。这个引用指向了主干历史的最新节点。`refs/quipu/heads/*` 只代表了分支的末端。
2.  **数据丢失过程**:
    *   `migrate-data` 命令运行时，它成功地将 `refs/quipu/heads/*` 下的 40 个分支末端移动到了 `refs/quipu/local/heads/*`。
    *   它**完全忽略**了 `refs/quipu/history` 这个引用。
    *   当后续的 `cache rebuild` 运行时，`Hydrator` (根据 v1.1 规范) 只扫描 `refs/quipu/local/heads/` 和 `refs/quipu/remotes/`。由于 `refs/quipu/history` 不再被扫描，所有只能通过这个旧引用才能访问到的历史节点（大约 360 多个）都变成了“不可达”的，因此 `Hydrator` 只发现了那 40 个被迁移的分支末端节点。
3.  **结论**: 数据并未从 `.git` 中被删除，但从 Quipu 的视角来看，它们丢失了，因为指向它们的关键引用没有被正确迁移。

### 用户需求
-   数据迁移过程必须是无损的，能够识别并迁移**所有**旧版的引用，包括 `refs/quipu/history` 和 `refs/quipu/heads/*`。

### 评论
这是一个严重的数据完整性问题。修复这个问题的优先级是最高的。我们必须确保迁移脚本的逻辑是完备的，覆盖所有已知的旧版数据结构。

### 目标
1.  **增强 `GitDB`**: 添加一个方法，用于安全地读取单个引用的 commit 哈希。
2.  **增强 `MigrationManager`**:
    *   修改其发现逻辑，使其能够同时查找 `refs/quipu/heads/*` 和 `refs/quipu/history`。
    *   将所有找到的 commit 哈希合并去重。
    *   在迁移循环中，确保删除所有旧的引用，包括 `refs/quipu/history`。

### 基本原理
我们将扩展 `MigrationManager` 的扫描范围。它会首先收集所有 `heads` 下的哈希，然后单独读取 `history` 引用的哈希，将它们合并成一个完整的待迁移集合。在迁移完成后，它会显式地删除所有旧的 `heads` 和 `history` 引用，完成清理工作。

### 标签
#intent/fix #flow/ready #priority/critical 
#comp/engine #comp/cli #scope/core 
#ai/instruct
#task/domain/storage #task/object/data-migration #task/action/bug-fix
#task/state/continue

---

### Script

#### Acts 1: 增强 `GitDB` 以读取单个引用

我们需要一个可靠的方法来获取 `refs/quipu/history` 指向的 commit。`git rev-parse` 是最适合的工具。

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_db.py
~~~~~
~~~~~python
        res = self._run(["show-ref", "--verify", "--quiet", "refs/quipu/"], check=False, log_error=False)
        return res.returncode == 0

    def log_ref(self, ref_names: Union[str, List[str]]) -> List[Dict[str, str]]:
~~~~~
~~~~~python
        res = self._run(["show-ref", "--verify", "--quiet", "refs/quipu/"], check=False, log_error=False)
        return res.returncode == 0

    def get_ref_commit_hash(self, ref_name: str) -> Optional[str]:
        """获取单个引用指向的 commit hash。"""
        res = self._run(["rev-parse", ref_name], check=False, log_error=False)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
        return None

    def log_ref(self, ref_names: Union[str, List[str]]) -> List[Dict[str, str]]:
~~~~~

#### Acts 2: 彻底修复 `MigrationManager`

现在我们来修正迁移逻辑，使其包含所有旧引用。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/migration.py
~~~~~
~~~~~python
class MigrationManager:
    """负责将旧版 Quipu 数据迁移到 v1.1 架构。"""

    LEGACY_REFS_PREFIX = "refs/quipu/heads/"
    NEW_REFS_PREFIX = "refs/quipu/local/heads/"

    def __init__(self, git_db: GitDB, config_manager: ConfigManager, db_manager: DatabaseManager, hydrator: Hydrator):
        self.git_db = git_db
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.hydrator = hydrator
        self.root_dir = git_db.root

    def _find_legacy_heads(self) -> List[str]:
        """查找所有旧格式的 head commit 哈希。"""
        ref_tuples = self.git_db.get_all_ref_heads(self.LEGACY_REFS_PREFIX)
        return [commit_hash for commit_hash, ref_name in ref_tuples]

    def _get_local_user_id(self) -> str:
        """获取或生成本地用户的 ID，用于补水。"""
~~~~~
~~~~~python
class MigrationManager:
    """负责将旧版 Quipu 数据迁移到 v1.1 架构。"""

    LEGACY_HEADS_PREFIX = "refs/quipu/heads/"
    LEGACY_HISTORY_REF = "refs/quipu/history"
    NEW_REFS_PREFIX = "refs/quipu/local/heads/"

    def __init__(self, git_db: GitDB, config_manager: ConfigManager, db_manager: DatabaseManager, hydrator: Hydrator):
        self.git_db = git_db
        self.config_manager = config_manager
        self.db_manager = db_manager
        self.hydrator = hydrator
        self.root_dir = git_db.root

    def _find_all_legacy_commit_hashes(self) -> List[str]:
        """查找所有旧格式（v1.0）的 commit 哈希，包括 heads 和 history。"""
        # 1. 查找所有 heads/*
        head_ref_tuples = self.git_db.get_all_ref_heads(self.LEGACY_HEADS_PREFIX)
        all_hashes = {commit_hash for commit_hash, ref_name in head_ref_tuples}
        
        # 2. 查找 history ref
        history_commit = self.git_db.get_ref_commit_hash(self.LEGACY_HISTORY_REF)
        if history_commit:
            all_hashes.add(history_commit)
            
        return sorted(list(all_hashes))

    def _get_local_user_id(self) -> str:
        """获取或生成本地用户的 ID，用于补水。"""
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/migration.py
~~~~~
~~~~~python
    def run(self) -> bool:
        """执行完整的迁移流程。"""
        legacy_heads = self._find_legacy_heads()
        if not legacy_heads:
            logger.info("✅ 未找到旧版（v1.0）数据引用，无需迁移。")
            return True

        logger.info(f"🔍 发现 {len(legacy_heads)} 个旧版历史分支，准备迁移...")

        # 步骤 1: 移动 Git 引用
        for commit_hash in legacy_heads:
            old_ref = f"{self.LEGACY_REFS_PREFIX}{commit_hash}"
            new_ref = f"{self.NEW_REFS_PREFIX}{commit_hash}"
            
            logger.debug(f"  - 正在移动: {old_ref} -> {new_ref}")
            self.git_db.update_ref(new_ref, commit_hash)
            self.git_db.delete_ref(old_ref)
        logger.info("✅ Git 引用已成功迁移到 v1.1 格式。")

        # 步骤 2: 为现有数据库条目回填 owner_id
~~~~~
~~~~~python
    def run(self) -> bool:
        """执行完整的迁移流程。"""
        legacy_commits = self._find_all_legacy_commit_hashes()
        if not legacy_commits:
            logger.info("✅ 未找到旧版（v1.0）数据引用，无需迁移。")
            return True

        logger.info(f"🔍 发现 {len(legacy_commits)} 个旧版历史末端节点，准备迁移...")

        # 步骤 1: 创建新的 v1.1 引用
        for commit_hash in legacy_commits:
            new_ref = f"{self.NEW_REFS_PREFIX}{commit_hash}"
            logger.debug(f"  - 正在创建新引用: {new_ref}")
            self.git_db.update_ref(new_ref, commit_hash)
        
        # 步骤 2: 安全地删除所有旧引用
        legacy_head_refs = self.git_db.get_all_ref_heads(self.LEGACY_HEADS_PREFIX)
        for _, ref_name in legacy_head_refs:
            logger.debug(f"  - 正在删除旧 head: {ref_name}")
            self.git_db.delete_ref(ref_name)
        
        if self.git_db.get_ref_commit_hash(self.LEGACY_HISTORY_REF):
            logger.debug(f"  - 正在删除旧 history ref: {self.LEGACY_HISTORY_REF}")
            self.git_db.delete_ref(self.LEGACY_HISTORY_REF)

        logger.info("✅ Git 引用已成功迁移到 v1.1 格式。")

        # 步骤 3: 为现有数据库条目回填 owner_id
~~~~~

### 下一步建议

现在，迁移逻辑是完备的了。请**严格按照**以下步骤操作，以确保在一个干净的、未经修改的 v1.0 状态下测试新的迁移脚本。

1.  **应用代码补丁**: 确保上述对 `git_db.py` 和 `migration.py` 的修改已应用到你的 `qd` 开发环境中。

2.  **彻底重置环境**:
    ```bash
    # 回到你的测试根目录
    cd ~/tmp/DONT_COMMIT_ON_THERE

    # 删除当前的 .quipu 目录和 .git 目录
    rm -rf .quipu .git

    # 从你的主项目复制一个全新的、未经迁移的 .git 目录
    cp -r ~/Documents/Projects/pyquipu/.git .
    ```

3.  **运行新的迁移命令**:
    ```bash
    qd migrate-data --force
    ```
    这一次，你应该会看到日志显示 `发现 406 个旧版历史末端节点...` (或其他正确的、完整的数字)。

4.  **验证**:
    *   检查日志，确保没有 `FOREIGN KEY` 错误。
    *   运行 `qd ui`。它现在应该能正常启动，并显示包含 406 个节点的完整历史图谱。
