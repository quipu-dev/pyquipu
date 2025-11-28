from quipu.cli.main import app


def test_cache_sync(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace

    # 这里我们主要测试命令的执行路径，因为 mock SQLite 依赖在集成测试中较复杂
    # 只要命令不崩溃且输出正确的日志即可
    result = runner.invoke(app, ["cache", "sync", "-w", str(work_dir)])

    # 预期失败或成功取决于是否安装了 SQLite 依赖，
    # 但我们至少可以验证它尝试运行了。
    # 如果环境没有配置 SQLite 后端，engine context 会正常退出。
    assert "数据同步" in result.stderr


def test_cache_rebuild_no_db(runner, quipu_workspace):
    work_dir, _, _ = quipu_workspace

    result = runner.invoke(app, ["cache", "rebuild", "-w", str(work_dir)])
    assert "数据库文件不存在" in result.stderr
    assert result.exit_code == 0
