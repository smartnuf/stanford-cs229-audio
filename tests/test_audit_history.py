from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import audit_history  # noqa: E402


class HistoryAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="cs229-history-test-")
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        self.env = os.environ.copy()
        self.env.update({
            "GIT_AUTHOR_NAME": "History fixture",
            "GIT_COMMITTER_NAME": "History fixture",
            "GIT_AUTHOR_EMAIL": "fixture@cs229-preservation.invalid",
            "GIT_COMMITTER_EMAIL": "fixture@cs229-preservation.invalid",
        })
        self.git("init", "--quiet")

    def git(self, *args: str, data: bytes | None = None,
            env: dict[str, str] | None = None) -> bytes:
        return subprocess.run(
            ["git", *args], cwd=self.repo, input=data, env=env or self.env,
            check=True, capture_output=True,
        ).stdout

    def commit(self, files: dict[str, bytes], parents: tuple[str, ...] = (),
               disallowed: str | None = None) -> str:
        entries = []
        for name, data in sorted(files.items()):
            blob = self.git("hash-object", "-w", "--stdin", data=data).decode().strip()
            entries.append(f"100644 blob {blob}\t{name}\n")
        tree = self.git("mktree", data="".join(entries).encode()).decode().strip()
        args = ["commit-tree", tree]
        for parent in parents:
            args.extend(["-p", parent])
        env = self.env.copy()
        if disallowed:
            env[f"GIT_{disallowed}_EMAIL"] = "fixture@disallowed.invalid"
        return self.git(*args, data=b"Synthetic regression fixture\n", env=env).decode().strip()

    def audit(self, *args: str) -> tuple[int, str]:
        output = io.StringIO()
        with patch.object(audit_history, "ROOT", self.repo), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            status = audit_history.main(list(args))
        return status, output.getvalue()

    def test_real_candidate_passes_without_switching_synthetic_merge_checkout(self) -> None:
        base = self.commit({"base.txt": b"base"})
        head = self.commit({"base.txt": b"base", "candidate.txt": b"candidate"}, (base,))
        merge = self.commit({"integration.txt": b"merged tree"}, (base, head), "COMMITTER")
        self.git("update-ref", "refs/heads/integration", merge)
        self.git("symbolic-ref", "HEAD", "refs/heads/integration")
        self.git("read-tree", "--reset", "-u", "HEAD")
        before = self.git("rev-parse", "HEAD")
        self.assertEqual(self.audit("--revision", head)[0], 0)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual((self.repo / "integration.txt").read_bytes(), b"merged tree")
        self.assertEqual(self.audit("--revision", "HEAD")[0], 1)
        self.assertEqual(self.audit()[0], 1)  # Legacy all-ref audit remains strict.

    def test_bad_author_or_committer_in_ancestor_still_fails(self) -> None:
        for role in ("AUTHOR", "COMMITTER"):
            with self.subTest(role=role):
                bad = self.commit({"past.txt": b"past"}, disallowed=role)
                clean_tip = self.commit({"now.txt": b"now"}, (bad,))
                status, output = self.audit("--revision", clean_tip)
                self.assertEqual(status, 1)
                self.assertIn("unapproved public author/committer", output)
                self.assertNotIn("fixture@disallowed.invalid", output)

    def test_historical_blobs_remain_audited_after_deletion(self) -> None:
        fake_secret = ("gh" + "p_" + "A" * 36).encode()
        cases = [
            ("lecture.M4A", b"not media", "forbidden blob type"),
            (".env", b"placeholder", "credential/config filename"),
            ("large.bin", b"x" * audit_history.MAX_TRACKED_BYTES, "oversized blob"),
            ("notes.txt", fake_secret, "credential signature"),
        ]
        for name, data, message in cases:
            with self.subTest(name=name):
                past = self.commit({name: data})
                tip = self.commit({"safe.txt": b"safe"}, (past,))
                status, output = self.audit("--revision", tip)
                self.assertEqual(status, 1)
                self.assertIn(message, output)
                self.assertNotIn(fake_secret.decode(), output)

    def test_invalid_revision_cannot_select_another_walk(self) -> None:
        good = self.commit({"safe.txt": b"safe"})
        self.git("update-ref", "refs/heads/main", good)
        for value in ("missing-ref", "--all", good + ".." + good):
            with self.subTest(value=value):
                status, output = self.audit("--revision=" + value)
                self.assertEqual(status, 1)
                self.assertIn("must resolve to an available commit", output)

    def test_shallow_history_fails_closed(self) -> None:
        tip = self.commit({"safe.txt": b"safe"})
        self.git("update-ref", "refs/heads/main", tip)
        (self.repo / ".git" / "shallow").write_bytes((tip + "\n").encode())
        for args in ((), ("--revision", tip)):
            self.assertEqual(self.audit(*args)[0], 1)

    def test_workflow_keeps_integration_checkout_and_scopes_only_history(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "validate.yml").read_text()
        checkout = workflow.split("- name: Check out exact revision", 1)[1].split("- name:", 1)[0]
        self.assertIn("fetch-depth: 0", checkout)
        self.assertNotRegex(checkout, r"(?m)^\s+ref:")
        self.assertIn("AUDIT_REVISION: ${{ github.event.pull_request.head.sha || github.sha }}", workflow)
        self.assertIn('python3 scripts/audit_history.py --revision "$AUDIT_REVISION"', workflow)
        self.assertLess(workflow.index("Run offline tests"), workflow.index("Audit genuine candidate history"))


if __name__ == "__main__":
    unittest.main()
