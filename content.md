你的诊断是正确的。我之前的 `patch` 意图在 *创建新节点时* 进行修剪，但它并没有处理已经存在的 294 个冗余引用。并且，从你的执行结果来看（294 -> 295），我的 `patch` 逻辑存在缺陷，未能正确删除父节点的引用。

我们分两步走：
1.  **修正错误**：修复 `GitObjectHistoryWriter` 中错误的修剪逻辑。
2.  **手动清理**：为你提供一个一次性的清理命令，来处理掉现存的所有冗余引用。

我将先提供清理命令的计划，因为它能立刻解决你的磁盘空间问题。

---

## [WIP] feat: 添加用于清理冗余引用的 `cache prune-refs` 命令

### 用户需求
提供一个手动命令，用于清理 `.git/refs/quipu/local/heads/` 目录下的所有冗余引用，只保留历史图谱中叶子节点的引用。

### 评论
这是一个必要的维护工具。它不仅可以修复历史问题，还能在未来任何引用策略调整或意外情况下，为用户提供一个恢复仓库健康的手段。

### 目标
1.  在 `quipu cache` 子命令组下添加一个新命令 `prune-refs`。
2.  该命令会加载完整的历史图谱。
3.  识别出所有非叶子节点（即有子节点的节点）。
4.  删除所有指向这些非叶子节点的 `head` 引用。
5.  在执行删除前，向用户展示将被删除的引用列表并请求确认。

### 基本原理
1.  加载完整的 `engine.history_graph`，这是一个包含了所有父子关系的图谱数据结构。
2.  遍历图中的所有节点，如果一个节点 `node.children` 列表不为空，那么它就是一个非叶子节点。
3.  获取所有 `refs/quipu/local/heads/*` 下的引用。
4.  对于每一个引用，检查它指向的 commit hash 是否对应一个非叶子节点。
5.  如果是，则将该引用加入待删除列表。
6.  在用户确认后，批量执行 `git update-ref -d <ref_name>`。

### 标签
#intent/build #intent/fix #flow/ready #priority/high 
#comp/cli #comp/engine #concept/state #scope/core 
#ai/instruct
#task/domain/storage
#task/object/ref-management
#task-action/optimize
#task/state/continue

---

### Script

#### Acts 1: 在 `cache.py` 中实现 `prune-refs` 命令

我们将向 `packages/quipu-cli/src/pyquipu/cli/commands/cache.py` 文件中添加新的 `prune-refs` 命令及其实现逻辑。

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/cache.py
~~~~~
~~~~~python
from ..ui_utils import prompt_for_confirmation
from .helpers import engine_context

logger = logging.getLogger(__name__)

cache_app = typer.Typer(name="cache", help="管理本地 SQLite 缓存。")
~~~~~
~~~~~python
from ..ui_utils import prompt_for_confirmation
from .helpers import engine_context

logger = logging.getLogger(__name__)

cache_app = typer.Typer(name="cache", help="管理本地 SQLite 缓存及 Git 元数据。")
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/pyquipu/cli/commands/cache.py
~~~~~
~~~~~python
    except (OSError, PermissionError) as e:
        logger.error(f"删除旧数据库文件 '{db_path}' 失败", exc_info=True)
        bus.error("cache.rebuild.error.deleteFailed", error=str(e))
        ctx.exit(1)

    cache_sync(ctx, work_dir)
~~~~~
~~~~~python
    except (OSError, PermissionError) as e:
        logger.error(f"删除旧数据库文件 '{db_path}' 失败", exc_info=True)
        bus.error("cache.rebuild.error.deleteFailed", error=str(e))
        ctx.exit(1)

    cache_sync(ctx, work_dir)


@cache_app.command("prune-refs")
def cache_prune_refs(
    ctx: typer.Context,
    force: Annotated[bool, typer.Option("--force", "-f", help="强制执行，跳过确认提示。")] = False,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
):
    """
    清理冗余的 Quipu head 引用，仅保留叶子节点引用。
    """
    setup_logging()
    bus.info("cache.prune.info.starting")

    with engine_context(work_dir) as engine:
        graph = engine.history_graph
        if not graph:
            bus.info("query.info.emptyHistory")
            ctx.exit(0)

        # 1. 识别所有非叶子节点的 commit hash
        non_leaf_commits = {node.commit_hash for node in graph.values() if node.children}
        bus.info("cache.prune.info.nonLeafFound", count=len(non_leaf_commits))

        # 2. 查找所有指向非叶子节点的本地 head 引用
        all_refs = engine.git_db.list_refs("refs/quipu/local/heads")
        refs_to_prune = []
        for ref_name, commit_hash in all_refs.items():
            if commit_hash in non_leaf_commits:
                refs_to_prune.append(ref_name)

        if not refs_to_prune:
            bus.success("cache.prune.success.noAction")
            ctx.exit(0)

        bus.warning("cache.prune.warning.aboutToDelete", count=len(refs_to_prune))
        # 打印部分待删除的 ref 作为示例
        for ref_to_show in refs_to_prune[:10]:
            bus.data(f"  - {ref_to_show}")
        if len(refs_to_prune) > 10:
            bus.data(f"  ... and {len(refs_to_prune) - 10} more.")

        # 3. 请求用户确认
        if not force:
            prompt = bus.get("cache.prune.prompt.confirm")
            if not prompt_for_confirmation(prompt, default=False):
                bus.warning("common.prompt.cancel")
                raise typer.Abort()

        # 4. 执行删除
        deleted_count = 0
        with typer.progressbar(refs_to_prune, label="正在修剪引用") as progress:
            for ref_name in progress:
                try:
                    engine.git_db.delete_ref(ref_name)
                    deleted_count += 1
                except Exception as e:
                    logger.error(f"Failed to delete ref {ref_name}", exc_info=True)
                    bus.error("cache.prune.error.deleteFailed", ref=ref_name, error=str(e))

        bus.success("cache.prune.success.complete", count=deleted_count)
~~~~~

#### Acts 2: 添加新的消息文本

现在，我们需要为 `cli.json` 添加 `prune-refs` 命令所需的用户提示信息。

~~~~~act
patch_file
packages/quipu-common/src/pyquipu/common/locales/zh/cli.json
~~~~~
~~~~~python
  "cache.rebuild.info.deleting": "🗑️  旧数据库已删除。",
  "cache.rebuild.error.deleteFailed": "❌ 删除旧数据库失败: {error}",
  "navigation.info.navigating": "🚀 正在导航到节点: {short_hash}",
  "navigation.success.visit": "✅ 已成功切换到状态 {short_hash}。",
~~~~~
~~~~~python
  "cache.rebuild.info.deleting": "🗑️  旧数据库已删除。",
  "cache.rebuild.error.deleteFailed": "❌ 删除旧数据库失败: {error}",
  "cache.prune.info.starting": "🌿 正在分析 Quipu 历史图谱以查找冗余引用...",
  "cache.prune.info.nonLeafFound": "发现 {count} 个非叶子节点。",
  "cache.prune.success.noAction": "✅ 所有引用均指向叶子节点，无需修剪。",
  "cache.prune.warning.aboutToDelete": "⚠️  即将删除以下 {count} 个冗余引用:",
  "cache.prune.prompt.confirm": "此操作不可逆。是否继续？",
  "cache.prune.error.deleteFailed": "❌ 删除引用 {ref} 失败: {error}",
  "cache.prune.success.complete": "✅ 修剪完成，已成功删除 {count} 个冗余引用。",
  "navigation.info.navigating": "🚀 正在导航到节点: {short_hash}",
  "navigation.success.visit": "✅ 已成功切换到状态 {short_hash}。",
~~~~~

### 下一步
在你执行这个计划后，你将拥有一个新的命令 `quipu cache prune-refs`。运行它，就可以安全地清理掉所有现存的冗余引用了。

之后，我会提供修复 `GitObjectHistoryWriter` 逻辑的计划，以确保未来不会再产生冗余引用。
