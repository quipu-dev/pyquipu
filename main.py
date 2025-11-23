import typer
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional, Dict

from logger_config import setup_logging
from core.controller import run_axon
from config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
from core.plugin_loader import load_plugins
from core.executor import Executor
from core.engine import Engine
from core.history import load_history_graph
from core.models import AxonNode
import inspect
import subprocess
from core.config_manager import ConfigManager

# 注意：不要在模块级别直接调用 setup_logging()，
# 否则会导致 CliRunner 测试中的 I/O 流过早绑定/关闭问题。
logger = logging.getLogger(__name__)

app = typer.Typer(add_completion=False, name="axon")

# --- 导航命令辅助函数 ---
def _find_current_node(engine: Engine, graph: Dict[str, AxonNode]) -> Optional[AxonNode]:
    """在图中查找与当前工作区状态匹配的节点"""
    current_hash = engine.git_db.get_tree_hash()
    node = graph.get(current_hash)
    if not node:
        typer.secho("⚠️  当前工作区状态未在历史中找到，或存在未保存的变更。", fg=typer.colors.YELLOW, err=True)
        typer.secho("💡  请先运行 'axon save' 创建一个快照，再进行导航。", fg=typer.colors.YELLOW, err=True)
    return node

def _execute_checkout(ctx: typer.Context, target_node: AxonNode, work_dir: Path):
    """通过子进程调用 checkout 命令以复用逻辑"""
    typer.secho(f"🚀 正在导航到节点: {target_node.short_hash} ({target_node.timestamp})", err=True)
    result = subprocess.run(
        [sys.executable, __file__, "checkout", target_node.output_tree, "--work-dir", str(work_dir), "--force"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        typer.secho("❌ 导航操作失败:", fg=typer.colors.RED, err=True)
        typer.secho(result.stderr, err=True)
        ctx.exit(1)
    else:
        typer.secho(result.stderr, err=True)

# --- 核心命令 ---

@app.command()
def ui(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    以交互式 TUI 模式显示 Axon 历史图谱。
    """
    try:
        from ui.tui import AxonUiApp
    except ImportError:
        typer.secho("❌ TUI 依赖 'textual' 未安装。", fg=typer.colors.RED, err=True)
        typer.secho("💡 请运行: pip install 'textual>=0.58.0'", err=True)
        ctx.exit(1)
        
    setup_logging()
    # 关键变更: 为了 UI, 我们需要加载所有节点, 而不仅仅是唯一状态节点
    from core.history import load_all_history_nodes
    
    engine = Engine(work_dir)
    all_nodes = load_all_history_nodes(engine.history_dir)
    
    if not all_nodes:
        typer.secho("📜 历史记录为空，无需启动 UI。", fg=typer.colors.YELLOW, err=True)
        ctx.exit(0)
        
    # 获取当前工作区状态哈希，用于在 UI 中自动定位
    current_hash = engine.git_db.get_tree_hash()
    
    app_instance = AxonUiApp(all_nodes, current_hash=current_hash)
    selected_hash = app_instance.run()

    if selected_hash:
        typer.secho(f"\n> TUI 请求检出到: {selected_hash[:7]}", err=True)
        _execute_checkout(ctx, graph[selected_hash], work_dir)


@app.command()
def save(
    ctx: typer.Context,
    message: Annotated[Optional[str], typer.Argument(help="本次快照的简短描述。")] = None,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    捕获当前工作区的状态，创建一个“微提交”快照。
    """
    setup_logging()
    engine = Engine(work_dir)
    status = engine.align()
    if status == "CLEAN":
        typer.secho("✅ 工作区状态未发生变化，无需创建快照。", fg=typer.colors.GREEN, err=True)
        ctx.exit(0)
    current_hash = engine.git_db.get_tree_hash()
    try:
        node = engine.capture_drift(current_hash, message=message)
        msg_suffix = f' ({message})' if message else ''
        typer.secho(f"📸 快照已保存: {node.short_hash}{msg_suffix}", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        typer.secho(f"❌ 创建快照失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)

@app.command()
def sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
    remote: Annotated[Optional[str], typer.Option("--remote", "-r", help="Git 远程仓库的名称 (覆盖配置文件)。")] = None,
):
    """
    与远程仓库同步 Axon 历史图谱。
    """
    setup_logging()
    work_dir = work_dir.resolve()
    config = ConfigManager(work_dir)
    if remote is None:
        remote = config.get("sync.remote_name", "origin")
    refspec = "refs/axon/history:refs/axon/history"
    def run_git_command(args: list[str]):
        try:
            result = subprocess.run(["git"] + args, cwd=work_dir, capture_output=True, text=True, check=True)
            if result.stdout: typer.echo(result.stdout, err=True)
            if result.stderr: typer.echo(result.stderr, err=True)
        except subprocess.CalledProcessError as e:
            typer.secho(f"❌ Git 命令执行失败: git {' '.join(args)}", fg=typer.colors.RED, err=True)
            typer.secho(e.stderr, fg=typer.colors.YELLOW, err=True)
            ctx.exit(1)
        except FileNotFoundError:
            typer.secho("❌ 错误: 未找到 'git' 命令。", fg=typer.colors.RED, err=True)
            ctx.exit(1)
    typer.secho(f"⬇️  正在从 '{remote}' 拉取 Axon 历史...", fg=typer.colors.BLUE, err=True)
    run_git_command(["fetch", remote, refspec])
    typer.secho(f"⬆️  正在向 '{remote}' 推送 Axon 历史...", fg=typer.colors.BLUE, err=True)
    run_git_command(["push", remote, refspec])
    typer.secho("\n✅ Axon 历史同步完成。", fg=typer.colors.GREEN, err=True)
    config_get_res = subprocess.run(["git", "config", "--get", f"remote.{remote}.fetch"], cwd=work_dir, capture_output=True, text=True)
    if refspec not in config_get_res.stdout:
        typer.secho("\n💡 提示: 为了让 `git pull` 自动同步 Axon 历史，请执行以下命令:", fg=typer.colors.YELLOW, err=True)
        typer.echo(f'  git config --add remote.{remote}.fetch "{refspec}"')

@app.command()
def discard(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="强制执行，跳过确认提示。")
    ] = False,
):
    """
    丢弃工作区所有未记录的变更，恢复到上一个干净状态。
    """
    setup_logging()
    engine = Engine(work_dir)
    history_dir = work_dir.resolve() / ".axon" / "history"
    graph = load_history_graph(history_dir)
    if not graph:
        typer.secho("❌ 错误: 找不到任何历史记录，无法确定要恢复到哪个状态。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    latest_node = max(graph.values(), key=lambda n: n.timestamp)
    target_tree_hash = latest_node.output_tree
    current_hash = engine.git_db.get_tree_hash()
    if current_hash == target_tree_hash:
        typer.secho(f"✅ 工作区已经是干净状态 ({latest_node.short_hash})，无需操作。", fg=typer.colors.GREEN, err=True)
        ctx.exit(0)
    if not force:
        typer.confirm(f"🚨 即将丢弃工作区所有未记录的变更，并恢复到状态 {latest_node.short_hash}。\n此操作不可逆。是否继续？", abort=True)
    try:
        engine.git_db.checkout_tree(target_tree_hash)
        typer.secho(f"✅ 工作区已成功恢复到节点 {latest_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        typer.secho(f"❌ 恢复状态失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)

@app.command()
def checkout(
    ctx: typer.Context,
    hash_prefix: Annotated[str, typer.Argument(help="目标状态节点的哈希前缀。")],
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
    force: Annotated[
        bool,
        typer.Option("--force", "-f", help="强制执行，跳过确认提示。")
    ] = False,
):
    """
    将工作区恢复到指定的历史节点状态。
    """
    setup_logging()
    history_dir = work_dir.resolve() / ".axon" / "history"
    graph = load_history_graph(history_dir)
    matches = [node for sha, node in graph.items() if sha.startswith(hash_prefix)]
    if not matches:
        typer.secho(f"❌ 错误: 未找到哈希前缀为 '{hash_prefix}' 的历史节点。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    if len(matches) > 1:
        typer.secho(f"❌ 错误: 哈希前缀 '{hash_prefix}' 不唯一，匹配到 {len(matches)} 个节点。", fg=typer.colors.RED, err=True)
        ctx.exit(1)
    target_node = matches[0]
    target_tree_hash = target_node.output_tree
    engine = Engine(work_dir)
    status = engine.align()
    current_hash = engine.git_db.get_tree_hash()
    if current_hash == target_tree_hash:
        typer.secho(f"✅ 工作区已处于目标状态 ({target_node.short_hash})，无需操作。", fg=typer.colors.GREEN, err=True)
        ctx.exit(0)
    if status in ["DIRTY", "ORPHAN"]:
        typer.secho("⚠️  检测到当前工作区存在未记录的变更，将自动创建捕获节点...", fg=typer.colors.YELLOW, err=True)
        engine.capture_drift(current_hash)
        typer.secho("✅ 变更已捕获。", fg=typer.colors.GREEN, err=True)
    if not force:
        typer.confirm(f"🚨 即将重置工作区到状态 {target_node.short_hash} ({target_node.timestamp})。\n此操作会覆盖未提交的更改。是否继续？", abort=True)
    try:
        engine.git_db.checkout_tree(target_tree_hash)
        typer.secho(f"✅ 已成功将工作区恢复到节点 {target_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        typer.secho(f"❌ 恢复状态失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)

# --- 导航命令 ---
@app.command()
def undo(
    ctx: typer.Context,
    count: Annotated[int, typer.Option("--count", "-n", help="向上移动的步数。")] = 1,
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", "-w", help="工作区根目录。")
    ] = DEFAULT_WORK_DIR,
):
    """
    向上移动到当前状态的父节点 (类似 Ctrl+Z)。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
    current_node = _find_current_node(engine, graph)
    if not current_node: ctx.exit(1)
    target_node = current_node
    for i in range(count):
        if not target_node.parent:
            msg = f"已到达历史根节点 (移动了 {i} 步)。" if i > 0 else "已在历史根节点。"
            typer.secho(f"✅ {msg}", fg=typer.colors.GREEN, err=True)
            if target_node == current_node: ctx.exit(0)
            break
        target_node = target_node.parent
    _execute_checkout(ctx, target_node, work_dir)

@app.command()
def redo(
    ctx: typer.Context,
    count: Annotated[int, typer.Option("--count", "-n", help="向下移动的步数。")] = 1,
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", "-w", help="工作区根目录。")
    ] = DEFAULT_WORK_DIR,
):
    """
    向下移动到子节点 (类似 Ctrl+Y)。默认选择最新的子节点。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
    current_node = _find_current_node(engine, graph)
    if not current_node: ctx.exit(1)
    target_node = current_node
    for i in range(count):
        if not target_node.children:
            msg = f"已到达分支末端 (移动了 {i} 步)。" if i > 0 else "已在分支末端。"
            typer.secho(f"✅ {msg}", fg=typer.colors.GREEN, err=True)
            if target_node == current_node: ctx.exit(0)
            break
        target_node = target_node.children[-1]
        if len(current_node.children) > 1:
            typer.secho(f"💡 当前节点有多个分支，已自动选择最新分支 -> {target_node.short_hash}", fg=typer.colors.YELLOW, err=True)
    _execute_checkout(ctx, target_node, work_dir)

@app.command()
def prev(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", "-w", help="工作区根目录。")
    ] = DEFAULT_WORK_DIR,
):
    """
    在同一父节点的兄弟分支间，切换到上一个 (更旧的) 节点。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
    current_node = _find_current_node(engine, graph)
    if not current_node: ctx.exit(1)
    siblings = current_node.siblings
    if len(siblings) <= 1:
        typer.secho("✅ 当前节点没有兄弟分支。", fg=typer.colors.GREEN, err=True)
        ctx.exit(0)
    try:
        idx = siblings.index(current_node)
        if idx == 0:
            typer.secho("✅ 已在最旧的兄弟分支。", fg=typer.colors.GREEN, err=True)
            ctx.exit(0)
        target_node = siblings[idx - 1]
        _execute_checkout(ctx, target_node, work_dir)
    except ValueError: pass

@app.command()
def next(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option("--work-dir", "-w", help="工作区根目录。")
    ] = DEFAULT_WORK_DIR,
):
    """
    在同一父节点的兄弟分支间，切换到下一个 (更新的) 节点。
    """
    setup_logging()
    engine = Engine(work_dir)
    graph = load_history_graph(engine.history_dir)
    current_node = _find_current_node(engine, graph)
    if not current_node: ctx.exit(1)
    siblings = current_node.siblings
    if len(siblings) <= 1:
        typer.secho("✅ 当前节点没有兄弟分支。", fg=typer.colors.GREEN, err=True)
        ctx.exit(0)
    try:
        idx = siblings.index(current_node)
        if idx == len(siblings) - 1:
            typer.secho("✅ 已在最新的兄弟分支。", fg=typer.colors.GREEN, err=True)
            ctx.exit(0)
        target_node = siblings[idx + 1]
        _execute_checkout(ctx, target_node, work_dir)
    except ValueError: pass

@app.command()
def log(
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w",
            help="操作执行的根目录（工作区）",
            file_okay=False,
            dir_okay=True,
            resolve_path=True
        )
    ] = DEFAULT_WORK_DIR,
):
    """
    显示 Axon 历史图谱日志。
    """
    setup_logging()
    history_dir = work_dir.resolve() / ".axon" / "history"
    if not history_dir.exists():
        typer.secho(f"❌ 在 '{work_dir}' 中未找到 Axon 历史记录 (.axon/history)。", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    graph = load_history_graph(history_dir)
    if not graph:
        typer.secho("📜 历史记录为空。", fg=typer.colors.YELLOW, err=True)
        raise typer.Exit(0)
    nodes = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)
    typer.secho("--- Axon History Log ---", bold=True, err=True)
    for node in nodes:
        ts = node.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        color = typer.colors.CYAN if node.node_type == "plan" else typer.colors.MAGENTA
        tag = f"[{node.node_type.upper()}]"
        summary = ""
        content_lines = node.content.strip().split('\n')
        if node.node_type == 'plan':
            in_act_block = False
            for line in content_lines:
                if line.strip().startswith(('~~~act', '```act')): in_act_block = True; continue
                if in_act_block and line.strip(): summary = line.strip(); break
            if not summary: summary = "Plan executed"
        elif node.node_type == 'capture':
            in_diff_block = False; diff_summary_lines = []
            for line in content_lines:
                if "变更文件摘要" in line: in_diff_block = True; continue
                if in_diff_block and line.strip().startswith('```'): break
                if in_diff_block and line.strip(): diff_summary_lines.append(line.strip())
            if diff_summary_lines:
                files_changed = [l.split('|')[0].strip() for l in diff_summary_lines]
                summary = f"Changes captured in: {', '.join(files_changed)}"
            else: summary = "Workspace changes captured"
        summary = (summary[:75] + '...') if len(summary) > 75 else summary
        typer.secho(f"{ts} {tag:<9} {node.short_hash}", fg=color, nl=False, err=True)
        typer.echo(f" - {summary}", err=True)

@app.command(name="run")
def run_command(
    ctx: typer.Context,
    file: Annotated[
        Optional[Path], 
        typer.Argument(help=f"包含 Markdown 指令的文件路径。", resolve_path=True)
    ] = None,
    work_dir: Annotated[
        Path, 
        typer.Option("--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True)
    ] = DEFAULT_WORK_DIR,
    parser_name: Annotated[str, typer.Option("--parser", "-p", help=f"选择解析器语法。默认为 'auto'。")] = "auto",
    yolo: Annotated[bool, typer.Option("--yolo", "-y", help="跳过所有确认步骤，直接执行 (You Only Look Once)。")] = False,
    list_acts: Annotated[bool, typer.Option("--list-acts", "-l", help="列出所有可用的操作指令及其说明。")] = False
):
    """
    Axon: 执行 Markdown 文件中的操作指令。
    """
    setup_logging()
    if list_acts:
        executor = Executor(root_dir=Path("."), yolo=True)
        load_plugins(executor, PROJECT_ROOT / "acts")
        typer.secho("\n📋 可用的 Axon 指令列表:\n", fg=typer.colors.GREEN, bold=True, err=True)
        acts = executor.get_registered_acts()
        for name in sorted(acts.keys()):
            doc = acts[name]
            clean_doc = inspect.cleandoc(doc) if doc else "暂无说明"
            indented_doc = "\n".join(f"   {line}" for line in clean_doc.splitlines())
            typer.secho(f"🔹 {name}", fg=typer.colors.CYAN, bold=True, err=True)
            typer.echo(f"{indented_doc}\n", err=True)
        ctx.exit(0)
    content = ""; source_desc = ""
    if file:
        if not file.exists(): typer.secho(f"❌ 错误: 找不到指令文件: {file}", fg=typer.colors.RED, err=True); ctx.exit(1)
        if not file.is_file(): typer.secho(f"❌ 错误: 路径不是文件: {file}", fg=typer.colors.RED, err=True); ctx.exit(1)
        content = file.read_text(encoding="utf-8"); source_desc = f"文件 ({file.name})"
    elif not sys.stdin.isatty():
        try:
            stdin_content = sys.stdin.read()
            if stdin_content: content = stdin_content; source_desc = "STDIN (管道流)"
        except Exception: pass
    if not content and DEFAULT_ENTRY_FILE.exists():
        content = DEFAULT_ENTRY_FILE.read_text(encoding="utf-8"); source_desc = f"默认文件 ({DEFAULT_ENTRY_FILE.name})"
    if file and not file.exists() and file.name in ["log", "checkout", "sync", "init", "ui"]:
        typer.secho(f"❌ 错误: 找不到指令文件: {file}", fg=typer.colors.RED, err=True)
        typer.secho(f"💡 提示: 你是不是想执行 'axon {file.name}' 命令？", fg=typer.colors.YELLOW, err=True)
        ctx.exit(1)
    if not content.strip():
        if not file:
            typer.secho(f"⚠️  提示: 未提供输入，且当前目录下未找到默认文件 '{DEFAULT_ENTRY_FILE.name}'。", fg=typer.colors.YELLOW, err=True)
            typer.echo("\n用法示例:", err=True); typer.echo("  axon run my_plan.md", err=True); typer.echo("  echo '...' | axon run", err=True)
            ctx.exit(0)
    logger.info(f"已加载指令源: {source_desc}"); logger.info(f"工作区根目录: {work_dir}")
    if yolo: logger.warning("⚠️  YOLO 模式已开启：将自动确认所有修改。")
    result = run_axon(content=content, work_dir=work_dir, parser_name=parser_name, yolo=yolo)
    if result.message:
        color = typer.colors.GREEN if result.success else typer.colors.RED
        typer.secho(f"\n{result.message}", fg=color, err=True)
    if result.data: typer.echo(result.data)
    ctx.exit(result.exit_code)

if __name__ == "__main__":
    app()