import logging
from pathlib import Path
from typing import Any, Dict

import yaml
from pyquipu.common.messaging import bus

logger = logging.getLogger(__name__)

# 默认配置，为所有可能的设置提供一个基础
DEFAULTS = {
    "storage": {
        "type": "sqlite",  # 可选: "git_object", "sqlite"
    },
    "sync": {
        "remote_name": "origin",
        "persistent_ignores": [".idea", ".vscode", ".envs", "__pycache__", "node_modules", "o.md"],
        "user_id": None,
        "subscriptions": [],
    },
    "list_files": {"ignore_patterns": [".git", "__pycache__", ".idea", ".vscode", "node_modules", ".quipu"]},
}


class ConfigManager:
    def __init__(self, work_dir: Path):
        self.config_path = work_dir.resolve() / ".quipu" / "config.yml"
        self.user_config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
                if not isinstance(config_data, dict):
                    bus.warning("engine.config.warning.invalidFormat", path=self.config_path)
                    return {}
                return config_data
        except yaml.YAMLError as e:
            bus.error("engine.config.error.parseFailed", path=self.config_path, error=str(e))
            return {}
        except Exception as e:
            bus.error("engine.config.error.readFailed", error=str(e))
            return {}

    def get(self, key: str, fallback: Any = None) -> Any:
        # 尝试从用户配置中获取
        user_val = self._get_nested(self.user_config, key)
        if user_val is not None:
            return user_val

        # 尝试从默认配置中获取
        default_val = self._get_nested(DEFAULTS, key)
        if default_val is not None:
            return default_val

        # 返回最终的备用值
        return fallback

    def _get_nested(self, data: Dict, key: str) -> Any:
        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

    def set(self, key: str, value: Any):
        keys = key.split(".")
        d = self.user_config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        logger.debug(f"配置已更新: {key} = {value}")

    def save(self):
        try:
            self.config_path.parent.mkdir(exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.user_config, f, default_flow_style=False, allow_unicode=True)
            bus.success("engine.config.success.saved", path=self.config_path)
        except Exception as e:
            bus.error("engine.config.error.saveFailed", error=str(e))
            raise
