#!/usr/bin/env python3
import shutil
import subprocess
import os
from pathlib import Path

ROOT_DIR = Path(__file__).parent
SANDBOX_DIR = ROOT_DIR / "sandbox"
DEV_QUIPU = ROOT_DIR / ".envs" / "dev" / "bin" / "quipu"


def setup_sandbox():
    if SANDBOX_DIR.exists():
        shutil.rmtree(SANDBOX_DIR)
    SANDBOX_DIR.mkdir()

    print(f"📦 初始化沙盒: {SANDBOX_DIR}")
    # 初始化 Git (Engine 需要)
    subprocess.run(["git", "init"], cwd=SANDBOX_DIR, check=True, capture_output=True)
    # 配置 Git 用户
    subprocess.run(["git", "config", "user.email", "sandbox@quipu.dev"], cwd=SANDBOX_DIR, check=True)
    subprocess.run(["git", "config", "user.name", "Sandbox Bot"], cwd=SANDBOX_DIR, check=True)


def run_test_plan():
    plan_content = """
~~~act
write_file
~~~
~~~path
hello.txt
~~~
~~~content
Hello from Sandbox
~~~
"""
    plan_path = SANDBOX_DIR / "test_plan.md"
    plan_path.write_text(plan_content, encoding="utf-8")

    print("▶️  在沙盒中执行 qd run ...")
    try:
        subprocess.run([str(DEV_QUIPU), "run", "test_plan.md", "--yolo"], cwd=SANDBOX_DIR, check=True)
        print("✅ 执行成功")
    except subprocess.CalledProcessError:
        print("❌ 执行失败")
        exit(1)


def verify_result():
    target = SANDBOX_DIR / "hello.txt"
    history = SANDBOX_DIR / ".quipu" / "history"

    if target.exists() and target.read_text() == "Hello from Sandbox":
        print("✅ 文件创建验证通过")
    else:
        print("❌ 文件创建验证失败")
        exit(1)

    if history.exists() and list(history.glob("*.md")):
        print("✅ 历史记录验证通过")
    else:
        print("❌ 历史记录验证失败")
        exit(1)


def main():
    if not DEV_QUIPU.exists():
        print("❌ 未找到 Dev 环境，请先运行 bootstrap.py")
        exit(1)

    setup_sandbox()
    run_test_plan()
    verify_result()
    print("\n🎉 沙盒验证全部通过！代码逻辑基本正常。")


if __name__ == "__main__":
    main()
