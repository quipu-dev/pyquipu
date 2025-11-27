好的，我分析了测试失败的原因。这些失败都指向了一个共同的根源：`quipu sync` 命令中的一个逻辑缺陷，导致它在处理远程仓库名称时行为不当，即使在测试中显式提供了 `--remote` 参数，`git push` 命令依然失败。根本原因在于，当未提供 `--remote` 选项时，传递给 `git` 底层命令的 `remote` 参数为 `None`，这导致了命令执行失败，并连锁引发了后续所有测试的断言失败。

我将修复这个问题。

## fix: 修复 `sync` 命令中远程名称解析的逻辑缺陷

### 错误分析
`quipu sync` 命令的实现直接将其 `remote` 参数（当未通过 CLI 传递时，其值为 `None`）传递给了底层的 `git_db` 方法。这导致 `git push None ...` 这样的无效命令被执行，从而使整个 `sync` 操作失败，并返回非零退出码。集成测试捕捉到了这个失败，表现为 `assert result.exit_code == 0` 失败。

### 用户需求
`quipu sync` 命令应该能够智能地确定要使用的远程仓库名称。其解析顺序应该是：
1.  优先使用通过 `--remote` CLI 选项传递的值。
2.  如果未提供 CLI 选项，则从 `.quipu/config.yml` 中读取 `sync.remote_name` 的值。
3.  如果配置文件中也没有，则回退到 `origin` 作为默认值。

### 评论
这是一个关键的可用性修复。用户不应该每次都必须输入 `--remote origin`。通过实现一个健全的回退逻辑，我们能提供更流畅的用户体验，并修复导致所有集成测试失败的根本性缺陷。

### 目标
修改 `quipu.cli.main.sync` 函数，以正确实现上述的远程名称解析逻辑，确保所有 `push` 和 `fetch` 操作都使用一个有效的远程名称。

### 基本原理
在 `sync` 函数的开头，引入一个新的局部变量 `final_remote`。通过检查 CLI 参数、配置文件和默认值来为其赋值，然后在后续的所有 `git_db` 调用中使用这个经过解析的、保证有效的变量。

### 标签
#intent/fix #flow/ready #priority/critical #comp/cli #concept/sync #scope/core #ai/instruct #task/domain/testing #task/object/sync-workflow #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修复 `sync` 命令

我将使用 `patch_file` 整体替换 `sync` 命令的实现，以引入正确的远程名称解析逻辑。

~~~~~act
patch_file
packages/quipu-cli/src/quipu/cli/main.py
~~~~~
~~~~~python
@app.command()
def sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
    remote: Annotated[Optional[str], typer.Option("--remote", "-r", help="Git 远程仓库的名称 (覆盖配置文件)。")] = None,
):
    """
    与远程仓库同步 Quipu 历史图谱。
    """
    setup_logging()
    # Sync 必须在 git 项目根目录执行
    sync_dir = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(sync_dir)

    # --- 1.3: 首次使用的“引导 (Onboarding)”逻辑 ---
    user_id = config.get("sync.user_id")
    if not user_id:
        typer.secho("🤝 首次使用 sync 功能，正在自动配置用户身份...", fg=typer.colors.BLUE, err=True)
        try:
            result = subprocess.run(
                ["git", "config", "user.email"], cwd=sync_dir, capture_output=True, text=True, check=True
            )
            email = result.stdout.strip()
            if not email:
                raise ValueError("Git user.email is empty.")

            user_id = get_user_id_from_email(email)
            config.set("sync.user_id", user_id)
            config.save()
            typer.secho(f"✅ 已根据你的 Git 邮箱 '{email}' 生成并保存用户 ID: {user_id}", fg=typer.colors.GREEN, err=True)

        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            typer.secho("❌ 错误：无法获取你的 Git 用户邮箱。", fg=typer.colors.RED, err=True)
            typer.secho("💡 请先运行以下命令进行设置:", fg=typer.colors.YELLOW, err=True)
            typer.echo("  git config --global user.email \"you@example.com\"")
            ctx.exit(1)

    try:
        git_db = GitDB(sync_dir)

        # --- Push Flow ---
        typer.secho(f"⬆️  正在向 '{remote}' 推送你的本地历史...", fg=typer.colors.BLUE, err=True)
        git_db.push_quipu_refs(remote, user_id)

        # --- Fetch Flow ---
        subscriptions = config.get("sync.subscriptions", [])
        target_ids_to_fetch = set([user_id] + subscriptions)
        typer.secho(f"⬇️  正在从 '{remote}' 拉取 {len(target_ids_to_fetch)} 个用户的历史...", fg=typer.colors.BLUE, err=True)

        for target_id in sorted(list(target_ids_to_fetch)):
            git_db.fetch_quipu_refs(remote, target_id)

        typer.secho("\n✅ Quipu 引用同步完成。", fg=typer.colors.GREEN, err=True)
        typer.secho(
            "\n💡 提示: 运行 `quipu cache sync` 来更新本地数据库和 UI 视图。",
            fg=typer.colors.YELLOW,
            err=True,
        )

    except RuntimeError as e:
        # Catch errors from GitDB._run
        typer.secho(f"\n❌ 同步操作失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)
~~~~~
~~~~~python
@app.command()
def sync(
    ctx: typer.Context,
    work_dir: Annotated[
        Path,
        typer.Option(
            "--work-dir", "-w", help="操作执行的根目录（工作区）", file_okay=False, dir_okay=True, resolve_path=True
        ),
    ] = DEFAULT_WORK_DIR,
    remote_option: Annotated[Optional[str], typer.Option("--remote", "-r", help="Git 远程仓库的名称 (覆盖配置文件)。")] = None,
):
    """
    与远程仓库同步 Quipu 历史图谱。
    """
    setup_logging()
    # Sync 必须在 git 项目根目录执行
    sync_dir = find_git_repository_root(work_dir) or work_dir
    config = ConfigManager(sync_dir)

    # 修复：实现远程名称的正确解析逻辑
    remote = remote_option or config.get("sync.remote_name", "origin")

    # --- 1.3: 首次使用的“引导 (Onboarding)”逻辑 ---
    user_id = config.get("sync.user_id")
    if not user_id:
        typer.secho("🤝 首次使用 sync 功能，正在自动配置用户身份...", fg=typer.colors.BLUE, err=True)
        try:
            result = subprocess.run(
                ["git", "config", "user.email"], cwd=sync_dir, capture_output=True, text=True, check=True
            )
            email = result.stdout.strip()
            if not email:
                raise ValueError("Git user.email is empty.")

            user_id = get_user_id_from_email(email)
            config.set("sync.user_id", user_id)
            config.save()
            typer.secho(f"✅ 已根据你的 Git 邮箱 '{email}' 生成并保存用户 ID: {user_id}", fg=typer.colors.GREEN, err=True)

        except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
            typer.secho("❌ 错误：无法获取你的 Git 用户邮箱。", fg=typer.colors.RED, err=True)
            typer.secho("💡 请先运行以下命令进行设置:", fg=typer.colors.YELLOW, err=True)
            typer.echo("  git config --global user.email \"you@example.com\"")
            ctx.exit(1)

    try:
        git_db = GitDB(sync_dir)

        # --- Push Flow ---
        typer.secho(f"⬆️  正在向 '{remote}' 推送你的本地历史...", fg=typer.colors.BLUE, err=True)
        git_db.push_quipu_refs(remote, user_id)

        # --- Fetch Flow ---
        subscriptions = config.get("sync.subscriptions", [])
        target_ids_to_fetch = set([user_id] + subscriptions)
        typer.secho(f"⬇️  正在从 '{remote}' 拉取 {len(target_ids_to_fetch)} 个用户的历史...", fg=typer.colors.BLUE, err=True)

        for target_id in sorted(list(target_ids_to_fetch)):
            git_db.fetch_quipu_refs(remote, target_id)

        typer.secho("\n✅ Quipu 引用同步完成。", fg=typer.colors.GREEN, err=True)
        typer.secho(
            "\n💡 提示: 运行 `quipu cache sync` 来更新本地数据库和 UI 视图。",
            fg=typer.colors.YELLOW,
            err=True,
        )

    except RuntimeError as e:
        # Catch errors from GitDB._run
        typer.secho(f"\n❌ 同步操作失败: {e}", fg=typer.colors.RED, err=True)
        ctx.exit(1)
~~~~~

### 下一步建议
在应用此修复后，之前失败的集成测试应该能够全部通过。下一步，我们将继续 **任务 6.2**，更新用户文档，详细说明 `sync` 命令的用法和协作工作流。
