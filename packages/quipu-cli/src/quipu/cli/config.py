import os
from pathlib import Path

# 全局配置中心


def _find_project_root() -> Path:
    """
    向上递归查找项目根目录。
    依据：存在 'acts' 目录 或 顶层 'pyproject.toml'。
    """
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "packages").exists() and (parent / "pyproject.toml").exists():
            return parent
        if (parent / "pyproject.toml").exists():
            # 简单的检查，看是否是顶层配置
            try:
                content = (parent / "pyproject.toml").read_text()
                if 'name = "quipu-dev"' in content:
                    return parent
            except Exception:
                pass
    # Fallback: 如果找不到（比如已安装到 site-packages），则指向当前文件所在目录
    # 这种情况下，acts 可能需要以其他方式加载（待定）
    return Path(__file__).parent.resolve()


# 项目根目录（代码所在位置）
PROJECT_ROOT: Path = _find_project_root()

# 默认的工作区根目录，可以通过环境变量覆盖
# 在实际运行时，通常由 CLI 参数指定
DEFAULT_WORK_DIR: Path = Path(os.getenv("AI_FS_WORK_DIR", "."))

# 默认的指令入口文件
# 用户可以在此修改默认值，或通过环境变量 AXON_ENTRY_FILE 覆盖
DEFAULT_ENTRY_FILE: Path = Path(os.getenv("AXON_ENTRY_FILE", "o.md"))

# 日志级别
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
