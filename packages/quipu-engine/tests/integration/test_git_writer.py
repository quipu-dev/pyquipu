import json
import subprocess
from unittest.mock import MagicMock

import pytest
from pyquipu.engine.git_db import GitDB
from pyquipu.engine.git_object_storage import GitObjectHistoryWriter


@pytest.fixture
def git_writer_setup(tmp_path):
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()
    subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@quipu.dev"], cwd=repo_path, check=True)
    subprocess.run(["git", "config", "user.name", "Quipu Test"], cwd=repo_path, check=True)

    git_db = GitDB(repo_path)
    writer = GitObjectHistoryWriter(git_db)

    return writer, git_db, repo_path


class TestGitObjectHistoryWriterUnit:
    @pytest.mark.parametrize(
        "node_type, content, kwargs, mock_changes, expected_summary",
        [
            # Plan a
            ("plan", "# feat: Implement feature\nDetails here.", {}, [], "feat: Implement feature"),
            ("plan", "Just a simple plan content line.", {}, [], "Just a simple plan content line."),
            # Capture with no changes
            ("capture", "", {"message": "Initial capture"}, [], "Initial capture Capture: No changes detected"),
            # Capture with changes (<= 3 files)
            ("capture", "", {}, [("M", "f1.py"), ("A", "f2.js")], "Capture: M f1.py, A f2.js"),
            # Capture with changes (> 3 files, should truncate)
            (
                "capture",
                "",
                {"message": "Big change"},
                [("M", "f1.py"), ("A", "f2.js"), ("D", "f3.css"), ("A", "f4.html")],
                "Big change Capture: M f1.py, A f2.js, D f3.css ... and 1 more files",
            ),
        ],
    )
    def test_generate_summary(self, node_type, content, kwargs, mock_changes, expected_summary):
        mock_git_db = MagicMock(spec=GitDB)
        mock_git_db.get_diff_name_status.return_value = mock_changes

        writer = GitObjectHistoryWriter(mock_git_db)
        summary = writer._generate_summary(node_type, content, "hash_a", "hash_b", **kwargs)

        assert summary == expected_summary


class TestGitObjectHistoryWriterIntegration:
    def test_create_node_end_to_end(self, git_writer_setup):
        writer, git_db, repo_path = git_writer_setup

        # 1. 准备工作区状态
        (repo_path / "main.py").write_text("print('hello')", "utf-8")
        output_tree = git_db.get_tree_hash()

        # 2. 调用 create_node
        plan_content = "# feat: Initial implementation\nThis is the first version."
        node = writer.create_node(
            node_type="plan",
            input_tree="4b825dc642cb6eb9a060e54bf8d69288fbee4904",  # Empty tree
            output_tree=output_tree,
            content=plan_content,
        )

        # 3. 验证 Git 状态
        commit_hash = node.commit_hash
        assert len(commit_hash) == 40

        # 3.1 检查引用是否更新为新的 head 格式
        ref_path = repo_path / ".git" / "refs" / "quipu" / "local" / "heads" / commit_hash
        assert ref_path.is_file(), "A new head ref file was not created."
        assert ref_path.read_text().strip() == commit_hash, "The head ref does not point to the correct commit."

        # 3.2 检查 Commit 内容
        commit_data = subprocess.check_output(["git", "cat-file", "-p", commit_hash], cwd=repo_path, text=True)
        assert "tree " in commit_data
        assert "feat: Initial implementation" in commit_data
        assert f"X-Quipu-Output-Tree: {output_tree}" in commit_data

        # 3.3 检查 Tree 内容
        tree_hash = commit_data.splitlines()[0].split(" ")[1]
        tree_data = subprocess.check_output(["git", "ls-tree", tree_hash], cwd=repo_path, text=True)
        assert "metadata.json" in tree_data
        assert "content.md" in tree_data

        # 3.4 检查 Blob 内容
        meta_blob_hash = [line.split()[2] for line in tree_data.splitlines() if "metadata.json" in line][0]
        meta_content_str = subprocess.check_output(
            ["git", "cat-file", "blob", meta_blob_hash], cwd=repo_path, text=True
        )
        meta_data = json.loads(meta_content_str)

        assert meta_data["meta_version"] == "1.0"
        assert meta_data["type"] == "plan"
        assert meta_data["summary"] == "feat: Initial implementation"
        assert meta_data["generator"]["id"] == "manual"
