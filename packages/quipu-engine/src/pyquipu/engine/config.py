import yaml
from pathlib import Path
import logging
from typing import Any, Dict
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
    """
    负责加载和管理 .quipu/config.yml 文件。
    """

    def __init__(self, work_dir: Path):
        self.config_path = work_dir.resolve() / ".quipu" / "config.yml"
        self.user_config: Dict[str, Any] = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """加载并解析 YAML 配置文件，如果文件不存在或无效则返回空字典。"""
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
        """
        获取一个配置值，支持点状符号进行嵌套访问 (e.g., 'sync.remote_name')。

        查找顺序:
        1. 用户配置 (`config.yml`)
        2. 内置默认值 (`DEFAULTS`)
        3. 提供的 `fallback` 值
        """
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
        """使用点状符号安全地访问嵌套字典。"""
        keys = key.split(".")
        current = data
        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None
        return current

    def set(self, key: str, value: Any):
        """
        设置一个配置值，支持点状符号进行嵌套访问。
        如果中间路径的字典不存在，会自动创建。
        """
        keys = key.split(".")
        d = self.user_config
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        logger.debug(f"配置已更新: {key} = {value}")

    def save(self):
        """将当前的 user_config 写回到 .quipu/config.yml 文件。"""
        try:
            self.config_path.parent.mkdir(exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.user_config, f, default_flow_style=False, allow_unicode=True)
            bus.success("engine.config.success.saved", path=self.config_path)
        except Exception as e:
            bus.error("engine.config.error.saveFailed", error=str(e))
            raise
