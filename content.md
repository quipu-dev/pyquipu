## [WIP] fix(build): 修正 bootstrap 脚本中错误的 wheel 构建命令

### 错误分析
`bootstrap.py init` 命令在为 `stable` 环境构建 `wheel` 包时失败，返回 `subprocess.CalledProcessError`，错误码为 2。经分析，这是由于在上次重构中，用于构建的命令被错误地从 `uv build --out-dir <dir>` 修改为了 `uv pip wheel --wheel-dir <dir>`。`uv build` 是专门用于执行 PEP 517 构建的正确命令，而 `uv pip wheel` 在此场景下未能成功创建构建环境，导致失败。使用 `-e` 模式的 `dev` 命令因不执行严格构建而掩盖了此问题。

### 用户需求
修复 `bootstrap.py` 脚本，使其 `init` 和 `promote` 命令能够成功为 `stable` 环境构建并安装软件包。

### 评论
这是一个典型的由不恰当的工具调用引起的回归错误。将命令修正回 `uv build` 不仅能解决当前的构建失败问题，也遵循了 `uv` 工具的最佳实践，确保了构建过程的健壮性和可预见性。

### 目标
1.  在 `bootstrap.py` 的 `install_packages` 函数中，定位错误的 `uv pip wheel` 命令。
2.  将其替换为正确的 `uv build --out-dir <dir>` 命令。

### 基本原理
恢复使用 `uv` 推荐的、专门用于从源码构建分发包的 `uv build` 命令。该命令会正确地读取 `pyproject.toml` 中的 `[build-system]` 表，设置一个临时的、隔离的构建环境，下载如 `setuptools` 等构建依赖，并执行构建后端，从而生成一个健壮的 `.whl` 文件。

### 标签
#intent/fix #flow/ready #priority/critical #comp/build #scope/dx #ai/instruct #task/domain/tooling #task/object/bootstrap-script #task/action/bug-fix #task/state/continue

---

### Script

#### Acts 1: 修正 `bootstrap.py` 中的构建命令

我们将使用 `patch_file` 精确地将错误的命令替换回正确的版本。

~~~~~act
patch_file
bootstrap.py
~~~~~
~~~~~python
                subprocess.run(
                    ["uv", "pip", "wheel", str(pkg_src), "--wheel-dir", str(tmp_path)],
                    check=True,
                    capture_output=True,
                )
~~~~~
~~~~~python
                subprocess.run(
                    ["uv", "build", str(pkg_src), "--out-dir", str(tmp_path)],
                    check=True,
                    capture_output=True,
                )
~~~~~

### 下一步建议
现在你可以重新运行 `python bootstrap.py init` 命令。构建过程现在应该可以成功完成了。
