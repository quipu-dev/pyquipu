import os
from pathlib import Path

from pyquipu.runtime.executor import Executor
from pyquipu.runtime.plugin_loader import load_plugins

from .utils import find_git_repository_root


class PluginManager:
    def load_from_sources(self, executor: Executor, work_dir: Path):
        plugin_sources = []

        # 优先级由低到高添加，后面的会覆盖前面的
        # 1. User Home (Lowest priority)
        home_acts = Path.home() / ".quipu" / "acts"
        plugin_sources.append(("🏠 Global", home_acts))

        # 2. Config / Env
        env_path = os.getenv("AXON_EXTRA_ACTS_DIR")
        if env_path:
            plugin_sources.append(("🔧 Env", Path(env_path)))

        # 3. Project Root (Highest priority)
        project_root_for_plugins = find_git_repository_root(work_dir)
        if project_root_for_plugins:
            proj_acts = project_root_for_plugins / ".quipu" / "acts"
            plugin_sources.append(("📦 Project", proj_acts))

        seen_paths = set()
        for label, path in plugin_sources:
            if not path.exists() or not path.is_dir():
                continue

            resolved_path = path.resolve()
            if resolved_path in seen_paths:
                continue

            load_plugins(executor, path)
            seen_paths.add(resolved_path)
