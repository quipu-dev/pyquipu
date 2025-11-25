# fix 完善 GitDB 测试

## 用户需求
完善 `tests/test_git_db.py` 中的 `test_cat_file_types` 测试用例，使其能够真正验证 Tree 对象的读取功能，而不是简单地 `pass`。

## 目标
更新测试代码，确保 Git 底层对象读取功能的正确性。

## 标签
#comp/tests #fix

---

## Script

### Acts 1: 完善 test_cat_file_types

~~~~~act
replace tests/test_git_db.py
~~~~~

~~~~~python
    def test_cat_file_types(self, git_repo, db):
        """测试 cat_file 处理不同类型对象的能力"""
        # Create a file
        content = b"content"
        blob_hash = db.hash_object(content)
        
        # Read as blob
        read_content = db.cat_file(blob_hash, "blob")
        assert read_content == content
        
        # Create a commit to test tree/commit cat
        subprocess.run(["git", "commit", "--allow-empty", "-m", "test"], cwd=git_repo, check=True)
        head_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo).decode().strip()
        
        # Read commit (pretty print)
        commit_content = db.cat_file(head_hash, "commit")
        assert b"tree " in commit_content
        assert b"author " in commit_content
        
        # Read tree
        tree_hash = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=git_repo).decode().strip()
        tree_content = db.cat_file(tree_hash, "tree")
        # tree content is text-like in pretty mode (ls-tree style output from cat-file -p?)
        # GitDB.cat_file uses -p for tree, which outputs parsed text format.
        # Let's verify it contains entries if any, or is empty-ish.
        # Since we allowed empty commit, it might be empty tree or have initial files from previous tests?
        # In this isolated test, git_repo fixture gives a clean repo? 
        # Wait, git_repo fixture in test_git_db.py does `git init`.
        # So it might be empty.
        pass
~~~~~

~~~~~python
    def test_cat_file_types(self, git_repo, db):
        """测试 cat_file 处理不同类型对象的能力"""
        # 1. Prepare data: create file, add, and commit
        (git_repo / "test_file").write_text("file content", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=git_repo, check=True)
        subprocess.run(["git", "commit", "-m", "test commit"], cwd=git_repo, check=True)
        
        # 2. Get hashes using git command for verification source
        head_hash = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=git_repo).decode().strip()
        tree_hash = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=git_repo).decode().strip()
        # Get blob hash via ls-tree
        ls_out = subprocess.check_output(["git", "ls-tree", "HEAD", "test_file"], cwd=git_repo).decode()
        blob_hash = ls_out.split()[2]

        # 3. Verify Blob reading
        read_blob = db.cat_file(blob_hash, "blob")
        assert read_blob == b"file content"
        
        # 4. Verify Commit reading
        read_commit = db.cat_file(head_hash, "commit")
        assert b"tree " in read_commit
        assert b"test commit" in read_commit
        
        # 5. Verify Tree reading
        read_tree = db.cat_file(tree_hash, "tree")
        # cat-file -p tree_hash output format: "100644 blob <hash>\ttest_file"
        assert b"test_file" in read_tree
        assert blob_hash.encode() in read_tree
~~~~~