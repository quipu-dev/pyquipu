from pathlib import Path

from pyquipu.application.utils import find_git_repository_root


class TestRootDiscovery:
    def test_find_git_repository_root(self, tmp_path: Path):
        # /project/.git
        # /project/src/subdir
        project = tmp_path / "project"
        project.mkdir()
        (project / ".git").mkdir()

        subdir = project / "src" / "subdir"
        subdir.mkdir(parents=True)

        # Case 1: From subdir
        assert find_git_repository_root(subdir) == project.resolve()

        # Case 2: From root
        assert find_git_repository_root(project) == project.resolve()

        # Case 3: Outside
        outside = tmp_path / "outside"
        outside.mkdir()
        assert find_git_repository_root(outside) is None
