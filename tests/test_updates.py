import subprocess
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from reconcave.cli import apply_update, check_for_updates


class TestCheckForUpdates(unittest.TestCase):
    def test_not_a_git_checkout(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = check_for_updates(Path("/fake/path"))
        self.assertFalse(result["available"])
        self.assertIn("not a git checkout", result["reason"])

    @patch("reconcave.cli.subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_git_not_installed(self, mock_exists, mock_run):
        mock_run.side_effect = FileNotFoundError()
        result = check_for_updates(Path("/fake/path"))
        self.assertFalse(result["available"])
        self.assertIn("git is not installed", result["reason"])

    @patch("reconcave.cli._run_git")
    @patch("reconcave.cli.subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_up_to_date(self, mock_exists, mock_subprocess_run, mock_run_git):
        # subprocess.run is only used for the `git --version` probe here
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        def fake_git(args, cwd, timeout=20.0):
            if args == ["fetch", "--quiet"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if args == ["rev-parse", "HEAD"]:
                return MagicMock(returncode=0, stdout="abc123\n", stderr="")
            if args == ["rev-parse", "@{u}"]:
                return MagicMock(returncode=0, stdout="abc123\n", stderr="")
            raise AssertionError(f"unexpected git call: {args}")

        mock_run_git.side_effect = fake_git
        result = check_for_updates(Path("/fake/path"))
        self.assertTrue(result["available"])
        self.assertTrue(result["up_to_date"])

    @patch("reconcave.cli._run_git")
    @patch("reconcave.cli.subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_behind_reports_commit_count_and_log(self, mock_exists, mock_subprocess_run, mock_run_git):
        mock_subprocess_run.return_value = MagicMock(returncode=0)

        def fake_git(args, cwd, timeout=20.0):
            if args == ["fetch", "--quiet"]:
                return MagicMock(returncode=0, stdout="", stderr="")
            if args == ["rev-parse", "HEAD"]:
                return MagicMock(returncode=0, stdout="aaa111\n", stderr="")
            if args == ["rev-parse", "@{u}"]:
                return MagicMock(returncode=0, stdout="bbb222\n", stderr="")
            if args == ["rev-list", "--count", "aaa111..bbb222"]:
                return MagicMock(returncode=0, stdout="3\n", stderr="")
            if args == ["log", "--oneline", "aaa111..bbb222"]:
                return MagicMock(returncode=0, stdout="bbb222 fix banner\nccc333 add feature\n", stderr="")
            raise AssertionError(f"unexpected git call: {args}")

        mock_run_git.side_effect = fake_git
        result = check_for_updates(Path("/fake/path"))
        self.assertTrue(result["available"])
        self.assertFalse(result["up_to_date"])
        self.assertEqual(result["behind_by"], 3)
        self.assertEqual(len(result["commits"]), 2)

    @patch("reconcave.cli._run_git")
    @patch("reconcave.cli.subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_fetch_failure_reported_gracefully(self, mock_exists, mock_subprocess_run, mock_run_git):
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_run_git.return_value = MagicMock(returncode=1, stdout="", stderr="could not resolve host")
        result = check_for_updates(Path("/fake/path"))
        self.assertFalse(result["available"])
        self.assertIn("git fetch failed", result["reason"])

    @patch("reconcave.cli._run_git")
    @patch("reconcave.cli.subprocess.run")
    @patch("pathlib.Path.exists", return_value=True)
    def test_timeout_reported_gracefully_not_raised(self, mock_exists, mock_subprocess_run, mock_run_git):
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        mock_run_git.side_effect = subprocess.TimeoutExpired(cmd="git fetch", timeout=20)
        result = check_for_updates(Path("/fake/path"))
        self.assertFalse(result["available"])
        self.assertIn("timed out", result["reason"])


class TestApplyUpdate(unittest.TestCase):
    @patch("reconcave.cli.subprocess.run")
    @patch("reconcave.cli._run_git")
    def test_successful_update(self, mock_run_git, mock_subprocess_run):
        mock_run_git.return_value = MagicMock(returncode=0, stdout="Already up to date.\n", stderr="")
        mock_subprocess_run.return_value = MagicMock(returncode=0)
        self.assertTrue(apply_update(Path("/fake/path")))

    @patch("reconcave.cli._run_git")
    def test_pull_failure_does_not_attempt_reinstall(self, mock_run_git):
        mock_run_git.return_value = MagicMock(returncode=1, stdout="", stderr="merge conflict")
        with patch("reconcave.cli.subprocess.run") as mock_subprocess_run:
            result = apply_update(Path("/fake/path"))
            mock_subprocess_run.assert_not_called()
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
