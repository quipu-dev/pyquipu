from pathlib import Path

import pytest
import yaml
from pyquipu.engine.config import ConfigManager


# A pytest fixture to provide a clean work directory for each test
@pytest.fixture
def work_dir(tmp_path: Path) -> Path:
    """Creates a temporary directory to act as a project root."""
    return tmp_path


def test_config_get_defaults(work_dir: Path):
    """Test that default values are returned when no config file exists."""
    config = ConfigManager(work_dir)

    # Test accessing a nested default value
    assert config.get("storage.type") == "sqlite"
    # Test a non-existent key with a fallback
    assert config.get("nonexistent.key", "fallback") == "fallback"
    # Test a default that is None
    assert config.get("sync.user_id") is None


def test_config_load_from_file(work_dir: Path):
    """Test loading configuration from an existing config.yml file."""
    config_dir = work_dir / ".quipu"
    config_dir.mkdir()
    config_file = config_dir / "config.yml"

    # Create a dummy config file
    dummy_config = {"storage": {"type": "sqlite"}, "sync": {"user_id": "test-user-from-file"}}
    with open(config_file, "w") as f:
        yaml.dump(dummy_config, f)

    config = ConfigManager(work_dir)

    # User-defined value should override default
    assert config.get("storage.type") == "sqlite"
    # Value defined in file should be loaded
    assert config.get("sync.user_id") == "test-user-from-file"
    # Default value should still be accessible if not overridden
    assert config.get("sync.remote_name") == "origin"


def test_config_set_and_save(work_dir: Path):
    """Test setting a simple value and saving it to a new file."""
    config = ConfigManager(work_dir)

    # Pre-check: value should be default (None)
    assert config.get("sync.user_id") is None

    # Set a new value in memory
    config.set("sync.user_id", "test-user-new")
    assert config.get("sync.user_id") == "test-user-new"

    # Save the configuration to disk
    config.save()

    config_file = work_dir / ".quipu" / "config.yml"
    assert config_file.exists()

    # Verify the content of the saved file
    with open(config_file, "r") as f:
        saved_data = yaml.safe_load(f)

    assert saved_data == {"sync": {"user_id": "test-user-new"}}


def test_config_nested_set_and_save(work_dir: Path):
    """Test that setting a nested key creates the necessary dictionaries."""
    config = ConfigManager(work_dir)

    config.set("a.b.c", 123)
    config.save()

    # Verify by loading with a new instance
    new_config = ConfigManager(work_dir)
    assert new_config.get("a.b.c") == 123


def test_config_round_trip_consistency(work_dir: Path):
    """
    Test the full cycle: create, set, save, then create a new instance and load.
    """
    # --- Phase 1: Create and save ---
    config1 = ConfigManager(work_dir)
    config1.set("storage.type", "sqlite")
    config1.set("sync.user_id", "round-trip-user")
    config1.set("sync.subscriptions", ["user-a", "user-b"])
    config1.save()

    # --- Phase 2: Load in a new instance and verify ---
    config2 = ConfigManager(work_dir)
    assert config2.get("storage.type") == "sqlite"
    assert config2.get("sync.user_id") == "round-trip-user"
    assert config2.get("sync.subscriptions") == ["user-a", "user-b"]
    # Verify a default value is still accessible
    assert config2.get("sync.remote_name") == "origin"
