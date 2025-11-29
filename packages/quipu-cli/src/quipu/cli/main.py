import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show, export

# 初始化日志记录器，但不配置 handler
# handler 的配置（stderr 或 file）由具体命令在执行时决定
logging.getLogger(__name__)

# --- App Definition ---
app = typer.Typer(
    add_completion=False,
    name="quipu",
    help="Quipu: 一个基于 Git 的、用于文件系统状态溯源与文学化操作的工具。",
)

# --- Command Registration ---
# 注册子命令应用
app.add_typer(cache.cache_app)

# 注册顶级命令
axon.register(app)
workspace.register(app)
navigation.register(app)
query.register(app)
remote.register(app)
run.register(app)
ui.register(app)
show.register(app)
export.register(app)


# --- Entry Point ---
if __name__ == "__main__":
    app()
