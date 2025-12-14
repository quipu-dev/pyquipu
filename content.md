你说得对，非常到位。简单替换确实治标不治本，会让测试在不同环境（比如 CI 或其他开发者本地）下表现不一。

治本的方法是让测试代码不依赖于任何特定的默认分支名。我们可以通过 `git push origin HEAD` 来实现这一点。`HEAD` 是一个指向当前所在分支的引用，这样无论默认分支是 `master` 还是 `main`，它都能正确地将当前分支推送到远程。

我将修改 `tests/integration/conftest.py`，采用这个更健壮的方案。

~~~~~act
patch_file
tests/integration/conftest.py
~~~~~
~~~~~python
    # Add a dummy file to avoid issues with initial empty commits
    (user_a_path / "README.md").write_text("Initial commit")
    run_git_command(user_a_path, ["add", "README.md"])
    run_git_command(user_a_path, ["commit", "-m", "Initial commit"])
    run_git_command(user_a_path, ["push", "origin", "master"])
    run_git_command(user_b_path, ["pull"])

    return remote_path, user_a_path, user_b_path
~~~~~
~~~~~python
    # Add a dummy file to avoid issues with initial empty commits
    (user_a_path / "README.md").write_text("Initial commit")
    run_git_command(user_a_path, ["add", "README.md"])
    run_git_command(user_a_path, ["commit", "-m", "Initial commit"])
    run_git_command(user_a_path, ["push", "origin", "HEAD"])
    run_git_command(user_b_path, ["pull"])

    return remote_path, user_a_path, user_b_path
~~~~~
