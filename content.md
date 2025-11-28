Of course. This is the perfect next step. We will now codify the logic from our successful manual test script into a fully automated `pytest` integration test. This will provide a permanent safety net, ensuring that future changes do not break the critical ownership attribution logic of the `sync` feature.

## test: add integration test for sync workflow and ownership verification

### 用户需求
你需要创建一个自动化的 `pytest` 集成测试，该测试应：
1.  完整地复现 `run_sync_test.sh` 脚本中的多用户协作流程。
2.  严格验证在用户 B `sync` 并订阅用户 A 之后，用户 B 本地 SQLite 缓存中的**每一个**历史节点都具有正确的 `owner_id`。

### 评论
将手动测试转化为自动化集成测试是软件开发中的一个关键实践。它将一次性的验证工作沉淀为可重复、可信赖的资产，极大地提升了项目的长期健壮性和开发者的信心。这个测试将成为 `sync` 功能正确性的最终守护者。

### 目标
1.  在 `tests/integration/` 目录下创建一个新的测试文件 `test_sync_workflow.py`。
2.  使用 `pytest` fixtures 来搭建一个包含裸仓库和两个独立用户工作区的隔离测试环境。
3.  在测试中，以编程方式模拟用户 A 创建历史、用户 B 克隆、`sync`、修改配置、再次 `sync` 的全过程。
4.  在测试的最后，从用户 B 的数据库中加载所有节点，并断言每一个节点的 `owner_id` 都与其原始作者的 ID 相匹配。

### 基本原理
我们将利用 `pytest` 的 `tmp_path` fixture 来创建临时的、隔离的文件系统环境。通过在测试代码中调用 `subprocess` 或封装好的 `QuipuProject` 辅助类，我们可以精确地控制 Git 和 `quipu` CLI 命令的执行，并检查其产生的副作用（如配置文件的修改和数据库内容的变更），从而实现对整个工作流的自动化验证。

### 标签
#intent/tooling #flow/ready #priority/high #comp/tests #concept/sync #scope/core #ai/instruct #task/domain/testing #task/object/sync-workflow #task/action/build #task/state/begin

---

### Script

#### Acts 1: 创建集成测试文件

我们将创建一个新的测试文件，其中包含完整的端到端 `sync` 工作流测试。

~~~~~act
write_file
tests/integration/test_sync_workflow.py
~~~~~
~~~~~python
import subprocess
from pathlib import Path
import yaml

import pytest
from tests.helpers import QuipuProject, get_user_id_from_email


@pytest.fixture(scope="module")
def bare_remote(tmp_path_factory) -> Path:
    """创建一个裸仓库作为中央服务器。"""
    remote_path = tmp_path_factory.mktemp("remote") / "repo.git"
    subprocess.run(["git", "init", "--bare", str(remote_path)], check=True, capture_output=True)
    return remote_path


@pytest.fixture(scope="module")
def user_a_data(bare_remote: Path, tmp_path_factory) -> tuple[QuipuProject, str, list[str]]:
    """
    初始化用户 A 的工作区，创建一些历史，并将所有内容推送到远程。
    返回: (QuipuProject 实例, 用户 A 的 ID, 用户 A 创建的 commit hashes)
    """
    # GIVEN: 用户 A 的工作区
    workspace_path = tmp_path_factory.mktemp("user_a")
    project = QuipuProject(workspace_path)
    project.git_init()
    project.git_remote_add("origin", str(bare_remote))
    project.git_config_set("user.name", "User A")
    project.git_config_set("user.email", "user.a@example.com")
    user_a_id = get_user_id_from_email("user.a@example.com")

    # GIVEN: 用户 A 创建了一些历史
    project.fs_write("file1.txt", "content1")
    node1 = project.capture("Initial commit")
    project.fs_write("file2.txt", "content2")
    node2 = project.capture("Second commit")
    commit_hashes = [node1.commit_hash, node2.commit_hash]

    # WHEN: 用户 A 将所有 Git 对象和 Quipu 引用推送到远程
    project.git_push_all()
    result = project.run_cli(["sync"])
    assert result.exit_code == 0, f"User A sync failed: {result.message}"

    return project, user_a_id, commit_hashes


@pytest.fixture
def user_b_project(bare_remote: Path, tmp_path: Path) -> QuipuProject:
    """初始化用户 B 的工作区，通过克隆远程仓库。"""
    # GIVEN: 用户 B 通过克隆加入项目
    user_b_ws = tmp_path / "user_b"
    subprocess.run(["git", "clone", str(bare_remote), str(user_b_ws)], check=True, capture_output=True)
    project = QuipuProject(user_b_ws)
    project.git_config_set("user.name", "User B")
    project.git_config_set("user.email", "user.b@example.com")
    return project


def test_sync_and_subscribe_workflow(user_a_data: tuple[QuipuProject, str, list[str]], user_b_project: QuipuProject):
    """
    完整的端到端测试：
    1. 用户 B 首次 sync，生成配置。
    2. 用户 B 订阅用户 A。
    3. 用户 B 再次 sync，拉取历史。
    4. 验证用户 B 数据库中的所有权归属是否完全正确。
    """
    _user_a_project, user_a_id, user_a_commit_hashes = user_a_data
    user_b_id = get_user_id_from_email("user.b@example.com")

    # --- 1. 用户 B 首次 sync (Onboarding) ---
    # WHEN: 用户 B 首次运行 sync
    result_sync1 = user_b_project.run_cli(["sync"])
    assert result_sync1.exit_code == 0, f"User B first sync failed: {result_sync1.message}"

    # THEN: 配置文件应已自动生成
    config_path = user_b_project.root_dir / ".quipu" / "config.yml"
    assert config_path.exists()
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    assert config["sync"]["user_id"] == user_b_id

    # --- 2. 用户 B 订阅用户 A ---
    # WHEN: 用户 B 手动修改配置以订阅用户 A
    config["sync"]["subscriptions"] = [user_a_id]
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # --- 3. 用户 B 再次 sync (Fetch) ---
    # WHEN: 用户 B 再次运行 sync，这次应该会拉取用户 A 的历史
    result_sync2 = user_b_project.run_cli(["sync"])
    assert result_sync2.exit_code == 0, f"User B second sync failed: {result_sync2.message}"

    # --- 4. 最终验证：所有权归属 ---
    # THEN: 用户 B 数据库中的每个节点都应有正确的 owner_id
    all_nodes_in_b = user_b_project.engine.reader.load_all_nodes()

    # 确保我们真的从用户 A 那里获取了节点
    assert len(all_nodes_in_b) >= len(user_a_commit_hashes)

    found_nodes = 0
    for node in all_nodes_in_b:
        # 这是一个核心断言：
        # 如果这个节点是用户 A 创建的，它的所有者必须是 user_a_id
        if node.commit_hash in user_a_commit_hashes:
            assert node.owner_id == user_a_id, (
                f"Node {node.commit_hash[:7]} should be owned by {user_a_id}, " f"but is owned by {node.owner_id}"
            )
            found_nodes += 1
        # 在这个测试中，用户 B 没有创建任何节点，所以我们不检查 user_b_id

    # 确保我们验证了所有预期从用户 A 同步过来的节点
    assert found_nodes == len(user_a_commit_hashes)

    print(f"\n✅ Verification successful: All {found_nodes} nodes from User A have the correct owner_id.")
~~~~~

### 下一步建议
1.  **运行测试**: 在你的项目根目录下，执行 `pytest tests/integration/test_sync_workflow.py`。
2.  **确认结果**: 测试应该会顺利通过，并在终端打印出成功的验证消息。
3.  **清理 (可选)**: 成功后，你可以安全地删除 `~/tmp/run_sync_test.sh` 脚本，因为它现在已经被这个更可靠的自动化测试所取代。
4.  **提交测试代码**: 将新的 `test_sync_workflow.py` 文件提交到版本控制中，为 `sync` 功能的开发画上一个完美的句号。
