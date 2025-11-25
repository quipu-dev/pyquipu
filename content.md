# feat: 提交可插拔摘要功能的更改

## 用户需求
用户希望将实现“可插拔摘要生成逻辑”及其相关测试修复的代码提交到版本控制系统。

## 目标
执行 `git add` 和 `git commit`。

## 标签
#git #commit

---

## Script

### Acts 1: 提交代码

将所有修改添加到暂存区并提交。

~~~~~act
git_add .
~~~~~

~~~~~act
git_commit
~~~~~

~~~~~content
feat: implement pluggable summarizer for semantic history logs

- interfaces: define Summarizer type in ActContext
- runtime: update Executor to support summarizer registration and execution
- acts: add semantic summarizers for write_file, replace, append_file, and git_commit
- engine: update HistoryWriter to accept external summary overrides
- cli: integrate summarization logic into the main controller flow
- tests: fix unit and integration tests to align with new Executor API and summary format
~~~~~
