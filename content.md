好的，我们开始为 `sync` 功能构建集成测试。

这个计划将创建一个新的测试文件，并搭建一个模拟双用户、单远程仓库的测试环境，以验证端到端的推送、拉取和数据所有权流程。

## test: 为 sync 工作流创建端到端集成测试

### 用户需求
为 `quipu sync` 功能编写一套完整的端到端集成测试，以验证其在多用户协作场景下的正确性、健壮性和数据一致性。

### 评论
这是 `sync` 功能开发的收尾步骤，也是最关键的一步。集成测试将模拟真实世界的使用场景，确保 Git 底层操作、配置读取、数据补水和所有权识别等多个模块能够正确协同工作。

### 目标
1.  创建一个新的测试文件 `tests/integration/test_sync.py`。
2.  在测试文件中搭建一个包含一个裸仓库 (作为远程) 和两个独立用户工作区的测试环境。
3.  验证用户A的 `push` 操作能否在远程正确创建其命名空间下的引用。
4.  验证用户B在订阅用户A后，其 `fetch` 操作能否正确拉取数据到本地的远程镜像命名空间。
5.  验证数据补水 (`Hydrator`) 过程能否为来自不同用户的节点正确记录 `owner_id`。
6.  验证 `--prune` 功能在本地删除引用并推送后，远程对应的引用也会被清理。

### 基本原理
我们将利用 `tests/helpers.py` 中的辅助函数来快速创建和配置 Git 仓库。测试的核心将是通过 `CliRunner` 或 `subprocess` 调用 `quipu sync` 命令，然后检查文件系统上的 `.git` 目录和 SQLite 数据库中的状态，以断言操作的正确性。每个用户工作区都将拥有独立的 `.quipu/config.yml` 文件来模拟不同的用户身份和订阅关系。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #concept/sync #scope/dx #ai/instruct #task/domain/testing #task/object/sync-workflow #task/action/integration-test #task/state/begin #task/status/active

---

### Script

#### Acts 1: 创建集成测试文件骨架

我们将创建 `tests/integration/test_sync.py` 文件，并为其填充好基础的类结构、`setup` 方法以及待实现的测试用例占位符。

~~~~~act
write_file
~~~~~
~~~~~path
tests/integration/test_sync.py
~~~~~
~~~~~python
import pytest
import subprocess
from pathlib import Path
from typer.testing import CliRunner

from quipu.cli.main import app
from quipu.common.identity import get_user_id_from_email
from tests.helpers import create_quipu_node, initialize_git_repo, run_command

runner = CliRunner()


class TestSyncWorkflow:
    """端到端测试 Quipu Sync 工作流。"""

    def setup_method(self):
        # 1. 创建裸仓库作为 "远程"
        self.remote_repo_path = Path("test_remote.git")
        run_command(["git", "init", "--bare", str(self.remote_repo_path)])
        self.remote_url = f"file://{self.remote_repo_path.resolve()}"

        # 2. 创建用户 A 的工作区
        self.user_a_path = Path("user_a_ws")
        self.user_a_email = "alice@example.com"
        self.user_a_id = get_user_id_from_email(self.user_a_email)
        initialize_git_repo(self.user_a_path)
        run_command(
            ["git", "remote", "add", "origin", self.remote_url],
            cwd=self.user_a_path,
        )
        run_command(["git", "config", "user.email", self.user_a_email], cwd=self.user_a_path)
        run_command(["git", "config", "user.name", "Alice"], cwd=self.user_a_path)

        # 3. 创建用户 B 的工作区
        self.user_b_path = Path("user_b_ws")
        self.user_b_email = "bob@example.com"
        self.user_b_id = get_user_id_from_email(self.user_b_email)
        initialize_git_repo(self.user_b_path)
        run_command(
            ["git", "remote", "add", "origin", self.remote_url],
            cwd=self.user_b_path,
        )
        run_command(["git", "config", "user.email", self.user_b_email], cwd=self.user_b_path)
        run_command(["git", "config", "user.name", "Bob"], cwd=self.user_b_path)

    def teardown_method(self):
        import shutil

        if self.remote_repo_path.exists():
            shutil.rmtree(self.remote_repo_path)
        if self.user_a_path.exists():
            shutil.rmtree(self.user_a_path)
        if self.user_b_path.exists():
            shutil.rmtree(self.user_b_path)

    def test_onboarding_and_initial_push(self):
        """测试首次 sync 时的用户引导和初次推送。"""
        # 在用户 A 的仓库中创建一个节点
        (self.user_a_path / "file.txt").write_text("hello from alice")
        result_run = runner.invoke(app, ["run", "-w", str(self.user_a_path)], "act: echo 'alice plan'")
        assert result_run.exit_code == 0

        # 运行 sync
        result_sync = runner.invoke(app, ["sync", "-w", str(self.user_a_path), "--remote", "origin"])
        assert result_sync.exit_code == 0
        assert f"生成并保存用户 ID: {self.user_a_id}" in result_sync.stderr
        assert "正在向 'origin' 推送" in result_sync.stderr

        # 验证远程仓库是否已创建对应的 ref
        res = run_command(
            ["git", "show-ref"],
            cwd=self.remote_repo_path,
            check=False,
        )
        assert f"refs/quipu/users/{self.user_a_id}/heads/" in res.stdout

    def test_subscribe_and_fetch(self):
        """测试用户 B 订阅并拉取用户 A 的历史。"""
        # 步骤 1: 用户 A 创建并推送历史 (复用上一个测试的逻辑)
        self.test_onboarding_and_initial_push()

        # 步骤 2: 用户 B 配置对 A 的订阅
        quipu_dir_b = self.user_b_path / ".quipu"
        quipu_dir_b.mkdir(exist_ok=True)
        config_b = quipu_dir_b / "config.yml"
        config_b.write_text(f"sync:\n  subscriptions:\n    - {self.user_a_id}\n")

        # 步骤 3: 用户 B 运行 sync
        result_sync_b = runner.invoke(app, ["sync", "-w", str(self.user_b_path), "--remote", "origin"])
        assert result_sync_b.exit_code == 0
        assert f"正在从 'origin' 拉取 2 个用户的历史" in result_sync_b.stderr

        # 步骤 4: 验证用户 B 的本地是否创建了远程镜像 ref
        res_b = run_command(
            ["git", "show-ref"],
            cwd=self.user_b_path,
            check=False,
        )
        assert f"refs/quipu/remotes/origin/{self.user_a_id}/heads/" in res_b.stdout
        
    def test_owner_id_hydration(self):
        """测试数据补水后，SQLite 中是否正确记录了 owner_id。"""
        pytest.skip("待实现: 需要在此处添加 SQLite 数据库检查逻辑。")

    def test_pruning_on_push(self):
        """测试推送时 --prune 是否能清理远程已删除的分支。"""
        pytest.skip("待实现: 需要模拟本地 ref 删除并验证远程 ref 是否同步删除。")

~~~~~

### 下一步建议
我们已经成功创建了测试文件的骨架。下一步是逐个实现标记为 `pytest.skip` 的测试用例，并补充更详细的断言逻辑，例如直接查询 SQLite 数据库来验证 `owner_id` 的正确性。
