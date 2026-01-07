import subprocess
from pathlib import Path

import pytest
from pyquipu.cli.main import app
from typer.testing import CliRunner

# A simple plan that creates one file
PLAN_A = """
```act
write_file a.txt
```
```content
File A content
```
"""

# A simple plan that creates a different file
PLAN_B = """
```act
write_file b.txt
```
```content
File B content
```
"""


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def git_workspace(tmp_path: Path) -> Path:
    """Creates a temporary directory and initializes it as a Git repository."""
    ws = tmp_path / "ws"
    ws.mkdir()
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=ws, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=ws, check=True)
    return ws


def git_rev_parse(ref: str, cwd: Path) -> str:
    """Helper to get the hash of a git ref."""
    result = subprocess.run(["git", "rev-parse", ref], cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


class TestStorageSelection:
    """Tests the automatic detection and selection of storage backends."""

    def test_defaults_to_git_object_storage_on_new_project(self, runner, git_workspace):
        """
        SCENARIO: A user starts a new project.
        EXPECTATION: The system should use the new Git Object storage by default.
        """
        # Action: Run a plan in the new workspace
        result = runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)

        assert result.exit_code == 0, result.stderr

        # Verification
        assert (git_workspace / "a.txt").exists()

        # 1. A new head ref should exist in the correct namespace
        get_heads_cmd = ["git", "for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads/"]
        heads = subprocess.check_output(get_heads_cmd, cwd=git_workspace, text=True).strip().splitlines()
        assert len(heads) >= 1, "A git ref for quipu history should have been created."

        # 2. Old directory should NOT exist
        legacy_history_dir = git_workspace / ".quipu" / "history"
        assert not legacy_history_dir.exists(), "Legacy file system history should not be used."

    def test_continues_using_git_object_storage(self, runner, git_workspace):
        """
        SCENARIO: A user runs quipu in a project already using the new format.
        EXPECTATION: The system should continue using the Git Object storage.
        """
        get_all_heads_cmd = ["git", "for-each-ref", "--format=%(objectname)", "refs/quipu/local/heads/"]

        # Setup: Run one command to establish the new format
        runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)
        heads_after_a = set(
            subprocess.check_output(get_all_heads_cmd, cwd=git_workspace, text=True).strip().splitlines()
        )
        assert len(heads_after_a) == 1
        commit_hash_a = heads_after_a.pop()

        # Action: Run a second command
        result = runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_B)
        assert result.exit_code == 0, result.stderr

        # Verification
        heads_after_b = set(
            subprocess.check_output(get_all_heads_cmd, cwd=git_workspace, text=True).strip().splitlines()
        )
        new_heads = heads_after_b - {commit_hash_a}

        # 1. A new head should be created
        assert len(new_heads) == 1, "A new history head was not created after the second run"
        commit_hash_b = new_heads.pop()

        # 2. The parent of the new commit should be the old one
        commit_data = subprocess.check_output(["git", "cat-file", "-p", commit_hash_b], cwd=git_workspace, text=True)
        parent_line = [line for line in commit_data.splitlines() if line.startswith("parent ")]
        assert len(parent_line) == 1, "New commit should have exactly one parent"
        parent_hash = parent_line[0].split(" ")[1]
        assert parent_hash == commit_hash_a, "The new commit should be parented to the previous one."

        # 3. No legacy files should be created
        assert not (git_workspace / ".quipu" / "history").exists()


class TestGitObjectWorkflow:
    """End-to-end tests for core commands using the Git Object backend."""

    def test_full_workflow_with_git_object_storage(self, runner, git_workspace):
        # 1. Run a plan to create state A
        res_run = runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)
        assert res_run.exit_code == 0
        assert (git_workspace / "a.txt").exists()

        # 2. Manually add a file and use `save` to create state B
        (git_workspace / "b.txt").write_text("manual change")
        res_save = runner.invoke(app, ["save", "add b.txt", "-w", str(git_workspace)])
        assert res_save.exit_code == 0
        assert "快照已保存" in res_save.stderr

        # 3. Use `log` to check history
        res_log = runner.invoke(app, ["log", "-w", str(git_workspace)])
        assert res_log.exit_code == 0
        assert "--- Quipu History Log ---" in res_log.stderr
        assert "add b.txt" in res_log.stdout  # Check data in stdout
        assert "Write: a.txt" in res_log.stdout  # Check data in stdout

        # 4. Use `find` and `checkout` to go back to state A
        res_find = runner.invoke(app, ["find", "--summary", "Write: a.txt", "-w", str(git_workspace)])
        assert res_find.exit_code == 0
        assert "--- 查找结果 ---" in res_find.stderr

        # Parse the output to get the full hash
        found_line = res_find.stdout.strip().splitlines()[-1]  # Get data from stdout
        parts = found_line.split()
        output_tree_a = parts[3]

        assert len(output_tree_a) == 40

        res_checkout = runner.invoke(app, ["checkout", output_tree_a[:8], "-f", "-w", str(git_workspace)])
        assert res_checkout.exit_code == 0, res_checkout.stderr

        # Verification of state A
        assert (git_workspace / "a.txt").exists()
        assert not (git_workspace / "b.txt").exists()


class TestFindCliCommand:
    @pytest.fixture
    def populated_workspace(self, git_workspace, runner):  # Correctly inject runner
        # Run plan A
        runner.invoke(app, ["run", "-y", "-w", str(git_workspace)], input=PLAN_A)
        # Run save
        (git_workspace / "change.txt").write_text("manual")
        runner.invoke(app, ["save", "Snapshot 1", "-w", str(git_workspace)])
        return git_workspace

    def test_find_cli_by_type(self, runner, populated_workspace):
        result = runner.invoke(app, ["find", "--type", "plan", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        assert "--- 查找结果 ---" in result.stderr
        assert "[PLAN]" in result.stdout
        assert "[CAPTURE]" not in result.stdout
        assert "Write: a.txt" in result.stdout

    def test_find_cli_by_summary(self, runner, populated_workspace):
        result = runner.invoke(app, ["find", "-s", "snapshot", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        assert "--- 查找结果 ---" in result.stderr
        assert "[CAPTURE]" in result.stdout
        assert "Snapshot 1" in result.stdout
        assert "[PLAN]" not in result.stdout

    def test_find_cli_no_results(self, runner, populated_workspace):
        result = runner.invoke(app, ["find", "-s", "non-existent", "-w", str(populated_workspace)])
        assert result.exit_code == 0
        assert "未找到符合条件" in result.stderr
