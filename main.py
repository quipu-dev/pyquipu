import typer
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

from logger_config import setup_logging
from core.controller import run_axon
from config import DEFAULT_WORK_DIR, DEFAULT_ENTRY_FILE, PROJECT_ROOT
from core.plugin_loader import load_plugins
from core.executor import Executor
from core.engine import Engine
from core.history import load_history_graph
import inspect
import subprocess

# 注意：不要在模块级别直接调用 setup_logging()，
# 否则会导致 CliRunner 测试中的 I/O 流过早绑定/关闭问题。
logger = logging.getLogger(__name__)

# 将主应用改名为 app，并将旧的 cli 命令重命名为 'run'
app = typer.Typer(add_completion=False, name="axon")

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
    remote: Annotated[str, typer.Option(help="Git 远程仓库的名称")] = "origin",
):
    """
    与远程仓库同步 Axon 历史图谱。

    此命令会推送本地的 Axon 历史记录，并拉取远程的更新。
    """
    setup_logging()
    work_dir = work_dir.resolve()
    
    # Git 仓库检查已移至 Engine/GitDB 初始化中，会自动触发
    # if not (work_dir / ".git").is_dir():
    #     typer.secho(f"❌ 错误: '{work_dir}' 不是一个 Git 仓库。", fg=typer.colors.RED, err=True)
    #     ctx.exit(1)

    refspec = "refs/axon/history:refs/axon/history"
    
    def run_git_command(args: list[str]):
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=work_dir,
                capture_output=True,
                text=True,
                check=True,
            )
            if result.stdout:
                typer.echo(result.stdout, err=True)
            if result.stderr:
                typer.echo(result.stderr, err=True)
        except subprocess.CalledProcessError as e:
            typer.secho(f"❌ Git 命令执行失败: git {' '.join(args)}", fg=typer.colors.RED, err=True)
            typer.secho(e.stderr, fg=typer.colors.YELLOW, err=True)
            ctx.exit(1)
        except FileNotFoundError:
            typer.secho("❌ 错误: 未找到 'git' 命令。", fg=typer.colors.RED, err=True)
            ctx.exit(1)


    # 1. Fetch from remote
    typer.secho(f"⬇️  正在从 '{remote}' 拉取 Axon 历史...", fg=typer.colors.BLUE, err=True)
    run_git_command(["fetch", remote, refspec])

    # 2. Push to remote
    typer.secho(f"⬆️  正在向 '{remote}' 推送 Axon 历史...", fg=typer.colors.BLUE, err=True)
    run_git_command(["push", remote, refspec])
    
    typer.secho("\n✅ Axon 历史同步完成。", fg=typer.colors.GREEN, err=True)
    
    # Check for fetch config and provide guidance if missing
    config_get_res = subprocess.run(
        ["git", "config", "--get", f"remote.{remote}.fetch"],
        cwd=work_dir, capture_output=True, text=True
    )
    if refspec not in config_get_res.stdout:
        typer.secho("\n💡 提示: 为了让 `git pull` 自动同步 Axon 历史，请执行以下命令:", fg=typer.colors.YELLOW, err=True)
        typer.echo(f'  git config --add remote.{remote}.fetch "{refspec}"')


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
        typer.Option(
            "--force", "-f",
            help="强制执行，跳过确认提示。"
        )
    ] = False,
):
    """
    将工作区恢复到指定的历史节点状态。
    """
    setup_logging()
    
    # 1. 查找节点
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
    
    # 2. 安全捕获当前状态
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

    # 3. 确认
    if not force:
        confirm = typer.confirm(
            f"🚨 即将重置工作区到状态 {target_node.short_hash} ({target_node.timestamp})。\n"
            f"此操作会覆盖未提交的更改。是否继续？",
            abort=True
        )

    # 4. 执行
    try:
        engine.git_db.checkout_tree(target_tree_hash)
        typer.secho(f"✅ 已成功将工作区恢复到节点 {target_node.short_hash}。", fg=typer.colors.GREEN, err=True)
    except Exception as e:
        typer.secho(f"❌ 恢复状态失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)


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
        
    # 按时间戳降序排序
    nodes = sorted(graph.values(), key=lambda n: n.timestamp, reverse=True)
    
    typer.secho("--- Axon History Log ---", bold=True, err=True)
    for node in nodes:
        ts = node.timestamp.strftime('%Y-%m-%d %H:%M:%S')
        
        # 颜色和标签
        color = typer.colors.CYAN if node.node_type == "plan" else typer.colors.MAGENTA
        tag = f"[{node.node_type.upper()}]"
        
        # 摘要
        first_line = node.content.strip().split('\n')[0]
        # 尝试从 plan 中提取 act 名称作为摘要
        if node.node_type == 'plan' and 'act' in first_line:
            summary = first_line
        else:
             summary = (first_line[:70] + '...') if len(first_line) > 70 else first_line


        typer.secho(f"{ts} {tag:<9} {node.short_hash}", fg=color, nl=False, err=True)
        typer.echo(f" - {summary}", err=True)


@app.command(name="run")
def run_command(
    ctx: typer.Context,
    file: Annotated[
        Optional[Path], 
        typer.Argument(
            help=f"包含 Markdown 指令的文件路径。",
            resolve_path=True
        )
    ] = None,
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
    parser_name: Annotated[
        str,
        typer.Option(
            "--parser", "-p",
            help=f"选择解析器语法。默认为 'auto'。",
        )
    ] = "auto",
    yolo: Annotated[
        bool,
        typer.Option(
            "--yolo", "-y",
            help="跳过所有确认步骤，直接执行 (You Only Look Once)。",
        )
    ] = False,
    list_acts: Annotated[
        bool,
        typer.Option(
            "--list-acts", "-l",
            help="列出所有可用的操作指令及其说明。",
        )
    ] = False
):
    """
    Axon: 执行 Markdown 文件中的操作指令。
    支持从文件参数、管道 (STDIN) 或默认文件中读取指令。
    """
    # 延迟初始化日志，确保流处理正确
    setup_logging()
    
    # --- 1. 特殊指令处理 ---
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

    # --- 2. 输入源处理 (Input Normalization) ---
    content = ""
    source_desc = ""

    # A. 显式文件参数
    if file:
        if not file.exists():
            typer.secho(f"❌ 错误: 找不到指令文件: {file}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
        if not file.is_file():
            typer.secho(f"❌ 错误: 路径不是文件: {file}", fg=typer.colors.RED, err=True)
            ctx.exit(1)
        content = file.read_text(encoding="utf-8")
        source_desc = f"文件 ({file.name})"

    # B. 尝试读取 STDIN (管道)
    # 只要不是 TTY，就尝试读取。这解决了 isatty 在测试环境中的歧义。
    elif not sys.stdin.isatty():
        try:
            # 读取所有内容，如果为空字符串说明没有数据
            stdin_content = sys.stdin.read()
            if stdin_content:
                content = stdin_content
                source_desc = "STDIN (管道流)"
        except Exception:
            pass # 读取失败则忽略

    # C. 回退到默认文件
    if not content and DEFAULT_ENTRY_FILE.exists():
        content = DEFAULT_ENTRY_FILE.read_text(encoding="utf-8")
        source_desc = f"默认文件 ({DEFAULT_ENTRY_FILE.name})"

    # D. 最终检查
    if not content.strip():
        typer.secho(f"⚠️  提示: 未提供输入，且当前目录下未找到默认文件 '{DEFAULT_ENTRY_FILE.name}'。", fg=typer.colors.YELLOW, err=True)
        typer.echo("\n用法示例:", err=True)
        typer.echo("  axon run my_plan.md       # 指定文件", err=True)
        typer.echo("  echo '...' | axon run     # 管道输入", err=True)
        typer.echo("\n更多选项请使用 --help", err=True)
        ctx.exit(0) # 这是一个正常的空运行退出，不应报错

    logger.info(f"已加载指令源: {source_desc}")
    logger.info(f"工作区根目录: {work_dir}")
    
    if yolo:
        logger.warning("⚠️  YOLO 模式已开启：将自动确认所有修改。")

    # --- 3. 调用核心控制器 (Core Execution) ---
    result = run_axon(
        content=content,
        work_dir=work_dir,
        parser_name=parser_name,
        yolo=yolo
    )

    # --- 4. 处理结果 (Output Mapping) ---
    if result.message:
        # 将摘要信息输出到 stderr
        color = typer.colors.GREEN if result.success else typer.colors.RED
        typer.secho(f"\n{result.message}", fg=color, err=True)

    # 如果有数据需要输出到 stdout (例如 read_file 的内容)，在这里处理
    # 目前 Controller 还没有数据返回机制，暂时保留接口
    if result.data:
        typer.echo(result.data)

    # 使用 ctx.exit 而不是 raise typer.Exit，对测试框架更友好
    ctx.exit(result.exit_code)

if __name__ == "__main__":
    app()