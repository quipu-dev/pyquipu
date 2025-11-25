# test: 为持久化忽略规则同步逻辑添加单元测试

## 目标
为 `Engine` 类中新增的 `_sync_persistent_ignores` 方法编写一套完整的单元测试用例。这将确保该功能在各种场景下都能正确地创建、更新和维护 `.git/info/exclude` 文件，同时不会破坏用户已有的自定义规则。

## 基本原理
测试将在一个临时的、隔离的 Git 仓库中进行。我们将通过 `pytest` 的 fixture 来准备这个环境。测试用例将覆盖以下核心场景：
1.  **首次创建**: 当 `.git/info/exclude` 文件不存在时，能够根据配置正确创建文件和 Quipu 管理块。
2.  **内容追加**: 当文件已存在但没有 Quipu 管理块时，能够将 Quipu 规则追加到文件末尾，而不影响原有内容。
3.  **内容更新**: 当文件中已存在 Quipu 管理块时，能够用新配置更新该块，同时保持块外内容不变。
4.  **默认配置**: 当 `.quipu/config.yml` 中没有相关配置时，能够正确应用 `DEFAULTS` 中的默认忽略规则。

通过覆盖这些场景，我们可以确保该功能的健壮性和可靠性。

## 标签
#test #core #config

---

## Script

### Act 1: 在 `test_engine.py` 中添加新的测试用例

我们将向 `tests/test_engine.py` 文件追加一个新的测试类 `TestPersistentIgnores`，其中包含所有相关的测试用例。

~~~~~act
append_file tests/test_engine.py
~~~~~

~~~~~python

class TestPersistentIgnores:
    def test_sync_creates_file_if_not_exists(self, engine_setup):
        """测试：如果 exclude 文件不存在，应能根据默认配置创建它。"""
        engine, repo_path = engine_setup
        
        # 重新初始化 Engine 以触发 _sync... 逻辑
        # fixture 里的 engine 是在没有任何 quipu 配置的情况下初始化的
        # 这里我们确保 .quipu 目录存在，并再次初始化
        (repo_path / ".quipu").mkdir()
        
        # 触发器
        engine = Engine(repo_path)
        
        exclude_file = repo_path / ".git" / "info" / "exclude"
        assert exclude_file.exists()
        content = exclude_file.read_text("utf-8")
        
        assert "# --- Managed by Quipu ---" in content
        assert ".envs" in content  # 检查默认规则之一

    def test_sync_appends_to_existing_file(self, engine_setup):
        """测试：如果 exclude 文件已存在，应追加 Quipu 块而不是覆盖。"""
        engine, repo_path = engine_setup
        
        exclude_file = repo_path / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(exist_ok=True)
        user_content = "# My personal ignores\n*.log\n"
        exclude_file.write_text(user_content)
        
        # 触发器
        engine = Engine(repo_path)
        
        content = exclude_file.read_text("utf-8")
        assert user_content in content
        assert "# --- Managed by Quipu ---" in content
        assert "o.md" in content

    def test_sync_updates_existing_block(self, engine_setup):
        """测试：如果 Quipu 块已存在，应更新其内容。"""
        engine, repo_path = engine_setup
        
        exclude_file = repo_path / ".git" / "info" / "exclude"
        exclude_file.parent.mkdir(exist_ok=True)
        
        old_block = (
            "# --- Managed by Quipu ---\n"
            "old_rule/\n"
            "# --- End Managed by Quipu ---"
        )
        user_content = f"# My ignores\n{old_block}\n# More ignores"
        exclude_file.write_text(user_content)
        
        # 触发器
        engine = Engine(repo_path)
        
        content = exclude_file.read_text("utf-8")
        assert "old_rule/" not in content
        assert ".vscode" in content  # 检查默认规则之一
        assert "# My ignores" in content
        assert "# More ignores" in content

    def test_sync_uses_user_config(self, engine_setup):
        """测试：应优先使用 .quipu/config.yml 中的用户配置。"""
        import yaml
        engine, repo_path = engine_setup
        
        # 创建用户配置文件
        config_dir = repo_path / ".quipu"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"
        
        user_ignores = {
            "sync": {
                "persistent_ignores": ["custom_dir/", "*.tmp"]
            }
        }
        config_file.write_text(yaml.dump(user_ignores), "utf-8")
        
        # 触发器
        engine = Engine(repo_path)
        
        exclude_file = repo_path / ".git" / "info" / "exclude"
        content = exclude_file.read_text("utf-8")
        
        assert "custom_dir/" in content
        assert "*.tmp" in content
        assert ".envs" not in content # 默认值应被覆盖
~~~~~