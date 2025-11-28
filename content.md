好的，我完全理解并赞同你的分析。为系统增加一个查看节点完整元数据的“OBD-II 接口”是至关重要的，它补全了数据可见性的闭环，并极大地增强了系统的调试能力和透明度。

你提出的 `quipu show <HASH>` 命令方案非常清晰且符合单一职责原则，是实现此功能的最佳路径。

我将生成一个计划，严格按照你设计的实现路径来添加这个功能。

## [WIP] feat: 实现 `quipu show` 命令以查看节点元数据

### 用户需求
系统当前缺少一个直接查看节点完整 `metadata.json` 遥测数据的方法，这造成了“数据可见性缺口”，限制了调试和问题追溯能力。需要实现一个类似 `git show` 的命令，用于展示指定历史节点的详细信息，特别是完整的元数据。

### 评论
这是一个关键的功能补全，它将 Quipu 精心记录的遥测数据暴露给用户，为兼容性问题排查、AI 行为分析和系统审计提供了必要的工具。引入职责单一的 `quipu show` 命令是比扩展现有 `log` 或 `find` 命令更清晰、更健壮的设计。

### 目标
1.  在 `HistoryReader` 接口中添加 `get_node_metadata_raw` 方法。
2.  在 `SQLiteHistoryReader` 和 `GitObjectHistoryReader` 中实现该接口。
3.  创建一个新的 `quipu show <HASH>` CLI 命令，能够接受 `commit_hash` 或 `output_tree` 的哈希前缀。
4.  该命令能够默认显示摘要、元数据和内容，并提供 `--meta` 和 `--content` 标志来分别只显示特定部分。
5.  使用 `rich` 库对输出的 JSON 元数据进行格式化和语法高亮。

### 基本原理
通过在数据访问层 (`HistoryReader`) 添加一个获取原始元数据的方法，我们可以高效地从存储后端（特别是 SQLite）直接提取未经解析的 JSON 字符串。CLI 层的新 `show` 命令将利用此方法，接收用户提供的哈希前缀，在历史图谱中进行匹配以找到唯一的节点，然后获取并格式化其详细信息。这遵循了分层设计的原则，将数据获取逻辑与表现逻辑解耦。

### 标签
#intent/build #flow/ready #priority/high #comp/cli #comp/engine #comp/interfaces #concept/history #concept/ui #scope/api #scope/ux #scope/dx #ai/instruct #task/domain/cli #task/object/show-command #task/action/implementation #task/state/begin #task/status/active

---

### Script

#### Acts 1: 在接口层定义原始元数据访问方法

我们首先更新 `quipu-interfaces` 中的 `HistoryReader` 抽象类，添加新方法的定义。

~~~~~act
patch_file
packages/quipu-interfaces/src/quipu/core/storage.py
~~~~~
~~~~~python
    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        """
        获取指定节点的完整内容 (Lazy Loading)。
        如果节点内容已加载，直接返回；否则从存储后端读取。
        """
        pass
~~~~~
~~~~~python
    @abstractmethod
    def get_node_content(self, node: QuipuNode) -> str:
        """
        获取指定节点的完整内容 (Lazy Loading)。
        如果节点内容已加载，直接返回；否则从存储后端读取。
        """
        pass

    @abstractmethod
    def get_node_metadata_raw(self, commit_hash: str) -> Optional[str]:
        """获取指定节点未经解析的原始 metadata JSON 字符串。"""
        pass
~~~~~

#### Acts 2: 在存储后端实现接口

现在，我们在 `SQLite` 和 `GitObject` 两个后端中实现 `get_node_metadata_raw` 方法。

首先是高效的 `SQLite` 后端：

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/sqlite_storage.py
~~~~~
~~~~~python
        except sqlite3.Error as e:
            logger.error(f"Failed to get private data for {node_commit_hash[:7]}: {e}")
            return None
~~~~~
~~~~~python
        except sqlite3.Error as e:
            logger.error(f"Failed to get private data for {node_commit_hash[:7]}: {e}")
            return None

    def get_node_metadata_raw(self, commit_hash: str) -> Optional[str]:
        """从 SQLite 高效获取原始 meta_json 字符串。"""
        conn = self.db_manager._get_conn()
        try:
            cursor = conn.execute("SELECT meta_json FROM nodes WHERE commit_hash = ?", (commit_hash,))
            row = cursor.fetchone()
            return row[0] if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get raw metadata for {commit_hash[:7]}: {e}")
            return None
~~~~~

然后是作为备用的 `GitObject` 后端：

~~~~~act
patch_file
packages/quipu-engine/src/quipu/core/git_object_storage.py
~~~~~
~~~~~python
        return descendants

    def get_node_content(self, node: QuipuNode) -> str:
        """
        从 Git Commit 中按需读取 content.md。
~~~~~
~~~~~python
        return descendants

    def get_node_metadata_raw(self, commit_hash: str) -> Optional[str]:
        """从 Git 对象中按需读取并返回 metadata.json 的内容。"""
        try:
            # 1. Get Tree Hash from Commit
            commit_bytes = self.git_db.cat_file(commit_hash, "commit")
            tree_line = commit_bytes.split(b"\n", 1)[0].decode("utf-8")
            if not tree_line.startswith("tree "):
                raise ValueError("Invalid commit object format")
            tree_hash = tree_line.split()[1]

            # 2. Get metadata.json Blob Hash from Tree
            tree_content_map = self.git_db.batch_cat_file([tree_hash])
            if tree_hash not in tree_content_map:
                return None
            tree_content = tree_content_map[tree_hash]
            entries = self._parse_tree_binary(tree_content)
            blob_hash = entries.get("metadata.json")

            if not blob_hash:
                return None  # No metadata found

            # 3. Read Blob content
            content_bytes = self.git_db.cat_file(blob_hash)
            return content_bytes.decode("utf-8", errors="ignore")

        except Exception as e:
            logger.error(f"Failed to lazy load raw metadata for commit {commit_hash[:7]}: {e}")
            return None

    def get_node_content(self, node: QuipuNode) -> str:
        """
        从 Git Commit 中按需读取 content.md。
~~~~~

#### Acts 3: 创建 `show` CLI 命令

我们在 `commands` 目录下创建一个新的 `show.py` 文件来实现 `quipu show` 命令。

~~~~~act
write_file
packages/quipu-cli/src/quipu/cli/commands/show.py
~~~~~
~~~~~python
import json
import logging
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.syntax import Syntax

from .helpers import engine_context
from ..config import DEFAULT_WORK_DIR

logger = logging.getLogger(__name__)


def register(app: typer.Typer):
    @app.command()
    def show(
        ctx: typer.Context,
        hash_prefix: Annotated[str, typer.Argument(help="目标状态节点的 commit_hash 或 output_tree 的哈希前缀。")],
        work_dir: Annotated[
            Path,
            typer.Option(
                "--work-dir",
                "-w",
                help="操作执行的根目录（工作区）",
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
            ),
        ] = DEFAULT_WORK_DIR,
        meta: Annotated[bool, typer.Option("--meta", help="仅显示完整的 metadata.json。")] = False,
        content: Annotated[bool, typer.Option("--content", help="仅显示完整的 content.md。")] = False,
    ):
        """
        显示指定历史节点的详细信息。
        """
        with engine_context(work_dir) as engine:
            graph = engine.history_graph

            matches = [
                node
                for node in graph.values()
                if node.commit_hash.startswith(hash_prefix) or node.output_tree.startswith(hash_prefix)
            ]

            if not matches:
                typer.secho(f"❌ 错误: 未找到哈希前缀为 '{hash_prefix}' 的历史节点。", fg=typer.colors.RED, err=True)
                ctx.exit(1)
            if len(matches) > 1:
                # 尝试通过 output_tree 精确匹配
                exact_matches = [node for node in matches if node.output_tree.startswith(hash_prefix)]
                if len(exact_matches) == 1:
                    matches = exact_matches
                else:
                    typer.secho(
                        f"❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {len(matches)} 个节点。",
                        fg=typer.colors.RED,
                        err=True,
                    )
                    ctx.exit(1)

            target_node = matches[0]

            # 确定要显示什么
            show_meta = meta or not (meta or content)
            show_content = content or not (meta or content)
            show_summary = not (meta or content)

            console = Console()

            if show_summary:
                ts = target_node.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                color = "cyan" if target_node.node_type == "plan" else "magenta"
                tag = f"[{target_node.node_type.upper()}]"
                typer.secho(f"[{color}]{ts} {tag:<9} {target_node.short_hash}[/{color}] - {target_node.summary}")
                typer.echo("-" * 20)

            if show_meta:
                meta_str = engine.reader.get_node_metadata_raw(target_node.commit_hash)
                if meta_str:
                    if show_summary:
                        typer.secho("\n📄 Metadata:", bold=True)
                    # 美化 JSON
                    parsed_json = json.loads(meta_str)
                    pretty_json = json.dumps(parsed_json, indent=2, ensure_ascii=False)
                    syntax = Syntax(pretty_json, "json", theme="default", line_numbers=True)
                    console.print(syntax)
                else:
                    typer.secho("🤷 未找到此节点的元数据。", fg=typer.colors.YELLOW)

            if show_content:
                node_content = engine.reader.get_node_content(target_node)
                if node_content:
                    if show_summary:
                        typer.secho("\n📜 Content:", bold=True)
                    # 打印 Markdown 内容
                    typer.echo(node_content)
                else:
                    typer.secho("🤷 此节点无内容。", fg=typer.colors.YELLOW)
~~~~~

#### Acts 4: 在主应用中注册新命令

最后，我们将 `show` 命令注册到 `quipu-cli` 的主应用中。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)
~~~~~
~~~~~python
import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)
~~~~~

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
remote.register(app)
run.register(app)
ui.register(app)
~~~~~
~~~~~python
remote.register(app)
run.register(app)
ui.register(app)
show.register(app)
~~~~~

### 下一步建议
- **完善 `show` 命令**：可以继续为 `quipu show` 添加 `--diff` 功能，调用 `git_db.get_diff_stat` 来显示该节点与其父节点之间的差异，这将使其功能更加完整。
- **编写测试用例**：为新的 `show` 命令在 `tests/cli/` 目录下添加测试用例，验证其哈希匹配逻辑、不同标志下的输出内容以及格式化是否正确。
