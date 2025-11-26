import importlib.util
import logging
import sys
from pathlib import Path
from .executor import Executor

logger = logging.getLogger(__name__)


def load_plugins(executor: Executor, plugin_dir: Path):
    """
    动态扫描、导入并注册所有插件模块。

    改进版：不再依赖 sys.path 和包名，而是直接通过文件路径加载模块。
    这允许加载任意位置的插件，哪怕文件夹名称相同（如都叫 'acts'）。
    """
    if not plugin_dir.exists():
        return

    logger.info(f"🔍 正在从 '{plugin_dir}' 加载插件...")

    # 确保是一个目录
    if not plugin_dir.is_dir():
        logger.warning(f"⚠️  路径 '{plugin_dir}' 不是目录，跳过。")
        return

    # 扫描目录下所有 .py 文件
    for file_path in plugin_dir.glob("*.py"):
        # 跳过私有模块和 __init__.py (除非你需要在 init 里做特殊注册，通常插件是独立的)
        if file_path.name.startswith("_"):
            continue

        # 构造唯一的模块名称，防止冲突
        # 格式: quipu_plugin.{parent_dir_hash}.{filename}
        # 这里简单使用全路径哈希或替换字符来保证唯一性
        safe_name = f"quipu_plugin_{file_path.stem}_{abs(hash(str(file_path)))}"

        try:
            # 使用 importlib.util 从文件路径直接加载
            spec = importlib.util.spec_from_file_location(safe_name, file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                # 必须在执行前加入 sys.modules，防止模块内部互相引用出错
                sys.modules[safe_name] = module
                spec.loader.exec_module(module)

                # 查找约定的 'register' 函数
                if hasattr(module, "register"):
                    register_func = getattr(module, "register")
                    register_func(executor)
                    logger.debug(f"✅ 成功加载插件: {file_path.name}")
                else:
                    # 静默跳过没有 register 的辅助文件
                    pass
            else:
                logger.warning(f"❌ 无法为 {file_path} 创建模块规范")

        except Exception as e:
            logger.error(f"❌ 加载插件 {file_path.name} 失败: {e}")
