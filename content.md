# fix-test: 修复持久化忽略规则测试中的目录重复创建问题

## 问题分析

错误原因是 `FileExistsError`，这意味着在测试用例尝试创建 `.quipu` 目录时，该目录已经存在了。

`engine_setup` 这个 fixture 在创建 `Engine` 实例时，`Engine` 的 `__init__` 方法就已经确保了 `.quipu` 目录的存在。因此，在测试用例中再次调用 `(repo_path / ".quipu").mkdir()` 就会导致文件已存在的错误。

解决方案非常简单：在调用 `mkdir()` 时，添加 `exist_ok=True` 参数。这样，如果目录已经存在，`mkdir` 操作会静默成功，而不会抛出异常。

## 目标
修复 `TestPersistentIgnores` 测试类中由于重复创建 `.quipu` 目录而导致的 `FileExistsError`。

## 基本原理
`engine_setup` fixture 在初始化 `Engine` 时已经保证了 `.quipu` 目录的存在。测试用例中后续的 `mkdir()` 调用需要增加 `exist_ok=True` 参数，以兼容目录已存在的情况。

## 标签
#fix #test

---

## Script

### Act 1: 修复 `test_sync_creates_file_if_not_exists` 测试用例

为 `.quipu` 目录的 `mkdir` 调用添加 `exist_ok=True`。

~~~~~act
replace tests/test_engine.py
~~~~~

~~~~~python
        # fixture 里的 engine 是在没有任何 quipu 配置的情况下初始化的
        # 这里我们确保 .quipu 目录存在，并再次初始化
        (repo_path / ".quipu").mkdir()
~~~~~

~~~~~python
        # fixture 里的 engine 是在没有任何 quipu 配置的情况下初始化的
        # 这里我们确保 .quipu 目录存在，并再次初始化
        (repo_path / ".quipu").mkdir(exist_ok=True)
~~~~~

### Act 2: 修复 `test_sync_uses_user_config` 测试用例

为 `config_dir.mkdir()` 调用添加 `exist_ok=True`。

~~~~~act
replace tests/test_engine.py
~~~~~

~~~~~python
        # 创建用户配置文件
        config_dir = repo_path / ".quipu"
        config_dir.mkdir()
        config_file = config_dir / "config.yml"
~~~~~

~~~~~python
        # 创建用户配置文件
        config_dir = repo_path / ".quipu"
        config_dir.mkdir(exist_ok=True)
        config_file = config_dir / "config.yml"
~~~~~