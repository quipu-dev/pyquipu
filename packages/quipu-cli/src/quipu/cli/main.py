import logging
import typer
from .commands import axon, cache, navigation, query, remote, run, ui, workspace, show, export
from .rendering import TyperRenderer
from quipu.common.messaging import bus

# --- Global Setup ---
# Inject the CLI-specific renderer into the common message bus instance.
# This must be done once at the application's entry point.
bus.set_renderer(TyperRenderer())

# Initialize logger, but handler configuration (stderr or file)
# is determined by specific commands at runtime.
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
