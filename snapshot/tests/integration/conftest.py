import pytest

from .helpers import run_git_command


@pytest.fixture(scope="module")
def sync_test_environment(tmp_path_factory):
    """
    Sets up a full sync test environment:
    1. A bare remote repository.
    2. Two user workspaces cloned from the remote.
    """
    base_dir = tmp_path_factory.mktemp("sync_tests")
    remote_path = base_dir / "remote.git"
    user_a_path = base_dir / "user_a"
    user_b_path = base_dir / "user_b"

    # 1. Create bare remote
    run_git_command(base_dir, ["init", "--bare", str(remote_path)])

    # 2. Clone for User A
    run_git_command(base_dir, ["clone", str(remote_path), str(user_a_path)])
    run_git_command(user_a_path, ["config", "user.name", "User A"])
    run_git_command(user_a_path, ["config", "user.email", "user.a@example.com"])

    # 3. Clone for User B
    run_git_command(base_dir, ["clone", str(remote_path), str(user_b_path)])
    run_git_command(user_b_path, ["config", "user.name", "User B"])
    run_git_command(user_b_path, ["config", "user.email", "user.b@example.com"])

    # Add a dummy file to avoid issues with initial empty commits
    (user_a_path / "README.md").write_text("Initial commit")
    run_git_command(user_a_path, ["add", "README.md"])
    run_git_command(user_a_path, ["commit", "-m", "Initial commit"])
    run_git_command(user_a_path, ["push", "origin", "HEAD"])
    run_git_command(user_b_path, ["pull"])

    return remote_path, user_a_path, user_b_path
