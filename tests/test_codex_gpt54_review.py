from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load_review_module():
    script_path = Path(__file__).resolve().parents[1] / "codex-gpt54-review"
    loader = SourceFileLoader("codex_gpt54_review", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


review = load_review_module()


class ReviewVariantTests(unittest.TestCase):
    def test_build_review_variants_defaults_to_five_angled_prompts(self):
        variants = review.build_review_variants("버그와 테스트를 검토해라", 5, "angled")

        self.assertEqual(len(variants), 5)
        self.assertEqual(variants[0][0], "01-regression")
        self.assertEqual(variants[-1][0], "05-skeptic")
        self.assertTrue(all("Extra review lens for this run:" in prompt for _label, prompt in variants))

    def test_build_review_variants_supports_identical_strategy(self):
        variants = review.build_review_variants("동일 프롬프트", 3, "identical")

        self.assertEqual(
            variants,
            [
                ("candidate-01", "동일 프롬프트"),
                ("candidate-02", "동일 프롬프트"),
                ("candidate-03", "동일 프롬프트"),
            ],
        )


class TimeoutPolicyTests(unittest.TestCase):
    def test_effective_timeout_ms_raises_54_pro_minimum_to_sixty_minutes(self):
        self.assertEqual(review.effective_timeout_ms("ChatGPT 5.4 Pro", 900000), 3600000)

    def test_effective_timeout_ms_keeps_faster_models_requested_timeout(self):
        self.assertEqual(review.effective_timeout_ms("ChatGPT 5.3 Instant", 900000), 900000)


class DiffPayloadTests(unittest.TestCase):
    def test_build_diff_payload_limits_git_commands_to_reviewable_files(self):
        repo_root = Path("/tmp/repo")
        seen_commands: list[list[str]] = []
        rel_paths = ["codex-gpt54-review", "tests/test_codex_gpt54_review.py"]

        def fake_run_command(args, cwd):
            seen_commands.append(list(args))
            command_key = tuple(args[:3])
            if command_key == ("git", "status", "--short"):
                return " M codex-gpt54-review\n M tests/test_codex_gpt54_review.py"
            return "(none)"

        with patch.object(review.repo_context_mod, "run_command", side_effect=fake_run_command):
            payload = review.build_diff_payload(repo_root, rel_paths)

        self.assertIn("codex-gpt54-review", payload)
        self.assertIn("tests/test_codex_gpt54_review.py", payload)
        self.assertEqual(
            seen_commands,
            [
                ["git", "status", "--short", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
                ["git", "diff", "--cached", "--find-renames", "HEAD", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
                ["git", "diff", "--find-renames", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
            ],
        )

    def test_build_diff_payload_reports_when_no_reviewable_files_changed(self):
        with patch.object(review.repo_context_mod, "run_command") as run_command:
            payload = review.build_diff_payload(Path("/tmp/repo"), [])

        self.assertIn("(no reviewable changed files)", payload)
        run_command.assert_not_called()

    def test_build_review_status_and_diff_stat_use_reviewable_paths_only(self):
        repo_root = Path("/tmp/repo")
        seen_commands: list[list[str]] = []
        rel_paths = ["codex-gpt54-review", "tests/test_codex_gpt54_review.py"]

        def fake_run_command(args, cwd):
            seen_commands.append(list(args))
            return "ok"

        with patch.object(review.repo_context_mod, "run_command", side_effect=fake_run_command):
            status_text = review.build_review_status_text(repo_root, rel_paths)
            diff_stat = review.build_review_diff_stat(repo_root, rel_paths)

        self.assertEqual(status_text, "ok")
        self.assertEqual(diff_stat, "ok")
        self.assertEqual(
            seen_commands,
            [
                ["git", "status", "--short", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
                ["git", "diff", "--stat", "HEAD", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
            ],
        )

    def test_collect_review_git_paths_keeps_deletes_and_filters_internal_artifacts(self):
        repo_root = Path("/tmp/repo")
        with patch.object(
            review.repo_context_mod,
            "gather_changed_git_paths",
            return_value=["app.py", "old.py", ".oracle-reviews/manifest.json", "__pycache__/x.pyc"],
        ):
            rel_paths = review.collect_review_git_paths(
                repo_root,
                selected_files=[repo_root / "tests" / "test_app.py"],
                include_changed_files=True,
                include_untracked=True,
            )

        self.assertEqual(rel_paths, ["app.py", "old.py", "tests/test_app.py"])

    def test_gather_repo_snapshot_paths_uses_tracked_and_untracked_files(self):
        repo_root = Path("/tmp/repo")

        def fake_run_command(args, cwd):
            if args == ["git", "ls-files"]:
                return "app.py\nREADME.md\n.oracle-reviews/manifest.json\n.oracle-bridge-token"
            if args == ["git", "ls-files", "--others", "--exclude-standard"]:
                return "notes.md\n__pycache__/junk.pyc"
            raise AssertionError(args)

        with patch.object(review.repo_context_mod, "run_command", side_effect=fake_run_command):
            rel_paths = review.gather_repo_snapshot_paths(repo_root, include_untracked=True)

        self.assertEqual(rel_paths, ["app.py", "README.md", "notes.md"])

    def test_sensitive_snapshot_paths_are_excluded(self):
        self.assertTrue(review.is_sensitive_snapshot_relpath(".oracle-bridge-token"))
        self.assertTrue(review.is_sensitive_snapshot_relpath(".env.local"))
        self.assertTrue(review.is_sensitive_snapshot_relpath("secrets/dev.pem"))
        self.assertFalse(review.is_sensitive_snapshot_relpath("src/app.py"))


class ReviewAggregationTests(unittest.TestCase):
    def test_consensus_threshold_requires_strict_majority_for_even_counts(self):
        self.assertEqual(review.consensus_threshold(4), 3)

    def make_candidate(self, index: int, label: str, payload: dict[str, object]) -> object:
        return review.ReviewCandidate(
            index=index,
            label=label,
            prompt_text=f"prompt-{index}",
            review_text=json.dumps(payload, ensure_ascii=False),
            output_path=Path(f"/tmp/review-{index}.json"),
            returncode=0,
            stdout_text="",
            stderr_text="",
            metadata={},
        )

    def test_aggregate_structured_candidates_merges_revise_feedback(self):
        candidates = [
            self.make_candidate(
                1,
                "01-regression",
                {
                    "verdict": "revise",
                    "summary": "예외 처리 누락",
                    "must_fix": ["timeout 예외 처리 추가"],
                    "risks": ["재시도 폭주 가능성"],
                    "tests": ["timeout 회귀 테스트"],
                    "follow_up_prompt": "timeout 실패 분기를 구현해라",
                },
            ),
            self.make_candidate(
                2,
                "02-tests",
                {
                    "verdict": "revise",
                    "summary": "테스트가 부족함",
                    "must_fix": ["timeout 예외 처리 추가"],
                    "risks": [],
                    "tests": ["timeout 회귀 테스트", "성공 경로 테스트"],
                    "follow_up_prompt": "",
                },
            ),
            self.make_candidate(
                3,
                "03-skeptic",
                {
                    "verdict": "pass",
                    "summary": "치명적 문제는 안 보임",
                    "must_fix": [],
                    "risks": [],
                    "tests": [],
                    "follow_up_prompt": "",
                },
            ),
        ]

        aggregated_text, metadata = review.aggregate_structured_candidates(candidates, expected_count=3)
        payload = json.loads(aggregated_text)

        self.assertEqual(payload["verdict"], "revise")
        self.assertEqual(payload["must_fix"], ["timeout 예외 처리 추가"])
        self.assertEqual(payload["tests"], ["timeout 회귀 테스트", "성공 경로 테스트"])
        self.assertEqual(payload["follow_up_prompt"], "timeout 실패 분기를 구현해라")
        self.assertEqual(metadata["mode"], "structured-consensus")
        self.assertEqual(metadata["selected_candidate"], 1)
        self.assertEqual(metadata["required_valid_candidate_count"], 2)

    def test_aggregate_review_candidates_falls_back_to_best_plaintext(self):
        candidates = [
            review.ReviewCandidate(
                index=1,
                label="plain-1",
                prompt_text="p1",
                review_text="짧은 리뷰",
                output_path=Path("/tmp/plain-1.txt"),
                returncode=0,
                stdout_text="",
                stderr_text="",
                metadata={},
            ),
            review.ReviewCandidate(
                index=2,
                label="plain-2",
                prompt_text="p2",
                review_text="핵심 피드백\n리스크\n테스트 보강\n바로 고칠 것",
                output_path=Path("/tmp/plain-2.txt"),
                returncode=0,
                stdout_text="",
                stderr_text="",
                metadata={},
            ),
        ]

        aggregated_text, metadata = review.aggregate_review_candidates(candidates, expected_count=2)

        self.assertEqual(aggregated_text, "핵심 피드백\n리스크\n테스트 보강\n바로 고칠 것")
        self.assertEqual(metadata["selected_candidate"], 2)
        self.assertEqual(metadata["mode"], "best-text")

    def test_aggregate_structured_candidates_requires_consensus_not_single_outlier(self):
        candidates = [
            self.make_candidate(
                1,
                "01-regression",
                {
                    "verdict": "revise",
                    "summary": "예외 처리 누락",
                    "must_fix": ["timeout 예외 처리 추가"],
                    "risks": [],
                    "tests": [],
                    "follow_up_prompt": "timeout 실패 분기를 구현해라",
                },
            ),
            self.make_candidate(
                2,
                "02-skeptic",
                {
                    "verdict": "pass",
                    "summary": "치명적 문제는 안 보임",
                    "must_fix": [],
                    "risks": [],
                    "tests": ["성공 경로 테스트"],
                    "follow_up_prompt": "",
                },
            ),
            self.make_candidate(
                3,
                "03-tests",
                {
                    "verdict": "pass",
                    "summary": "치명적 문제는 안 보임",
                    "must_fix": [],
                    "risks": [],
                    "tests": ["회귀 테스트 확인"],
                    "follow_up_prompt": "",
                },
            ),
        ]

        aggregated_text, metadata = review.aggregate_structured_candidates(candidates, expected_count=3)
        payload = json.loads(aggregated_text)

        self.assertEqual(payload["verdict"], "pass")
        self.assertEqual(payload["must_fix"], [])
        self.assertEqual(metadata["pass_count"], 2)
        self.assertEqual(metadata["revise_count"], 1)

    def test_aggregate_structured_candidates_rejects_insufficient_valid_reviews(self):
        candidates = [
            self.make_candidate(
                1,
                "01-regression",
                {
                    "verdict": "pass",
                    "summary": "ok",
                    "must_fix": [],
                    "risks": [],
                    "tests": [],
                    "follow_up_prompt": "",
                },
            )
        ]

        with self.assertRaisesRegex(ValueError, "at least 2 are required"):
            review.aggregate_structured_candidates(candidates, expected_count=3)

    def test_aggregate_review_candidates_does_not_fallback_to_plaintext_when_json_consensus_fails(self):
        candidates = [
            self.make_candidate(
                1,
                "01-regression",
                {
                    "verdict": "pass",
                    "summary": "ok",
                    "must_fix": [],
                    "risks": [],
                    "tests": [],
                    "follow_up_prompt": "",
                },
            )
        ]

        with self.assertRaisesRegex(ValueError, "at least 2 are required"):
            review.aggregate_review_candidates(candidates, expected_count=3)


class ReviewArtifactResetTests(unittest.TestCase):
    def test_reset_review_artifacts_clears_stale_outputs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            write_output = base / "review.json"
            prompt_artifact = base / "review.prompt.md"
            candidate_dir = base / "review.json.candidates"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            write_output.write_text("old-review", encoding="utf-8")
            prompt_artifact.write_text("old-prompt", encoding="utf-8")
            (candidate_dir / "manifest.json").write_text("old-manifest", encoding="utf-8")

            review.reset_review_artifacts(write_output, prompt_artifact, candidate_dir)

            self.assertFalse(write_output.exists())
            self.assertFalse(prompt_artifact.exists())
            self.assertFalse(candidate_dir.exists())


class SnapshotArchiveTests(unittest.TestCase):
    def test_resolve_attachment_format_prefers_text_for_small_inline_payloads(self):
        with tempfile.TemporaryDirectory() as tempdir:
            small_file = Path(tempdir) / "small.py"
            small_file.write_text("print('ok')\n", encoding="utf-8")

            attachment_format = review.resolve_attachment_format(
                "auto",
                delivery="cdp",
                inline_attachments=[small_file],
            )

        self.assertEqual(attachment_format, "text")

    def test_resolve_attachment_format_prefers_repo_zip_for_large_inline_payloads(self):
        with tempfile.TemporaryDirectory() as tempdir:
            big_files = []
            for index in range(4):
                big_file = Path(tempdir) / f"big-{index}.py"
                big_file.write_text("x" * 1000, encoding="utf-8")
                big_files.append(big_file)

            attachment_format = review.resolve_attachment_format(
                "auto",
                delivery="cdp",
                inline_attachments=big_files,
            )

        self.assertEqual(attachment_format, "repo-zip")

    def test_create_repo_snapshot_archive_includes_manifest_context_diff_and_repo_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            (repo_root / "app.py").write_text("print('ok')\n", encoding="utf-8")
            (repo_root / "pkg").mkdir()
            (repo_root / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")

            with patch.object(review.bundles_mod, "gather_changed_git_paths", return_value=["app.py", ".oracle-bridge-token"]):
                archive_path = review.create_repo_snapshot_archive(
                    repo_root=repo_root,
                    branch="main",
                    prompt_text="리뷰해라",
                    context_text="# Context\n",
                    selected_files=[],
                    review_git_paths=["app.py", "deleted.py"],
                    repo_snapshot_paths=["app.py", "pkg/mod.py"],
                    status_text=" M app.py\n D deleted.py",
                    diff_stat=" app.py | 1 +",
                    diff_payload="# Diff\n",
                )
            try:
                import zipfile

                with zipfile.ZipFile(archive_path) as archive:
                    names = set(archive.namelist())
                    self.assertIn("README.md", names)
                    self.assertIn("manifest.json", names)
                    self.assertIn("context/review-context.md", names)
                    self.assertIn("context/git-diff.md", names)
                    self.assertIn("repo/app.py", names)
                    self.assertIn("repo/pkg/mod.py", names)
                    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
                    self.assertEqual(manifest["deleted_paths"], ["deleted.py"])
                    self.assertEqual(manifest["repo_snapshot_paths"], ["app.py", "pkg/mod.py"])
                    self.assertIn("excluded_sensitive_paths", manifest)
            finally:
                archive_path.unlink(missing_ok=True)


class CleanupHelperTests(unittest.TestCase):
    def test_safe_unlink_ignores_locked_files(self):
        class LockedPath:
            def __init__(self):
                self.calls: list[tuple[str, object]] = []

            def unlink(self, missing_ok: bool = False):
                self.calls.append(("unlink", missing_ok))
                raise PermissionError("locked")

        locked = LockedPath()

        review.safe_unlink(locked)  # type: ignore[arg-type]

        self.assertEqual(locked.calls, [("unlink", True)])

    def test_terminate_process_waits_after_kill(self):
        class FakeProcess:
            def __init__(self):
                self.wait_calls = 0
                self.calls: list[str] = []

            def poll(self):
                self.calls.append("poll")
                return None

            def terminate(self):
                self.calls.append("terminate")

            def wait(self, timeout: float):
                self.wait_calls += 1
                self.calls.append(f"wait:{timeout}")
                if self.wait_calls == 1:
                    raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
                return 0

            def kill(self):
                self.calls.append("kill")

        process = FakeProcess()

        review.terminate_process(process)  # type: ignore[arg-type]

        self.assertEqual(process.calls, ["poll", "terminate", "wait:5", "kill", "wait:5"])


class CDPReviewRunnerTests(unittest.TestCase):
    def test_recover_existing_windows_cdp_candidates_reads_prompt_markers_and_uses_recovery_mode(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            candidate_dir = base / "review.json.candidates"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            prompt_path = candidate_dir / "candidate-01-01-regression.prompt.md"
            prompt_path.write_text(
                "BEGIN_CDX_REVIEW_ABC_01\nEND_CDX_REVIEW_ABC_01\n",
                encoding="utf-8",
            )

            def fake_run_windows_cdp_chatgpt(**kwargs):
                output_path = kwargs["output_path"]
                assert output_path is not None
                output_path.write_text("{\"verdict\":\"pass\"}", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout=b'{"recovered":true}', stderr=b"")

            with patch.object(review, "run_windows_cdp_chatgpt", side_effect=fake_run_windows_cdp_chatgpt) as runner:
                candidates = review.recover_existing_windows_cdp_candidates(
                    candidate_dir=candidate_dir,
                    project_url="https://chatgpt.com/g/project",
                    model_label="ChatGPT 5.4 Pro",
                    timeout_ms=3600000,
                    debug_url="http://127.0.0.1:9870",
                    marker_suffix="recover",
                )

            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].index, 1)
            self.assertEqual(candidates[0].label, "01-regression")
            self.assertEqual(candidates[0].review_text, '{"verdict":"pass"}')
            self.assertTrue(runner.call_args.kwargs["recover_existing_only"])

    def test_inspect_windows_cdp_reviews_uses_inspection_mode(self):
        with patch.object(
            review,
            "run_windows_cdp_chatgpt",
            return_value=SimpleNamespace(returncode=0, stdout=b'{"pendingReviews":[]}', stderr=b""),
        ) as run_windows_cdp_chatgpt:
            payload = review.inspect_windows_cdp_reviews(
                project_url="https://chatgpt.com/g/project",
                debug_url="http://127.0.0.1:9870",
                marker_suffix="inspect",
            )

        self.assertEqual(payload, {"pendingReviews": []})
        kwargs = run_windows_cdp_chatgpt.call_args.kwargs
        self.assertTrue(kwargs["inspect_existing_reviews_only"])
        self.assertFalse(kwargs["prepare_only"])
        self.assertFalse(kwargs["prefer_new_page"])
        self.assertEqual(kwargs["model_strategy"], "ignore")

    def test_ensure_no_pending_windows_cdp_reviews_raises_when_existing_tabs_are_incomplete(self):
        with patch.object(
            review,
            "inspect_windows_cdp_reviews",
            return_value={
                "pendingReviews": [
                    {"state": "pending", "url": "https://chatgpt.com/g/project/c/1"},
                    {"state": "incomplete", "url": "https://chatgpt.com/g/project/c/2"},
                ]
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "still pending or incomplete"):
                review.ensure_no_pending_windows_cdp_reviews(
                    project_url="https://chatgpt.com/g/project",
                    debug_url="http://127.0.0.1:9870",
                    marker_suffix="inspect",
                )

    def test_run_windows_cdp_chatgpt_cleans_driver_and_config_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            payload_path = base / "payload.txt"
            payload_path.write_text("prompt", encoding="utf-8")
            output_path = base / "output.md"
            attachment_path = base / "repo.zip"
            attachment_path.write_text("zip", encoding="utf-8")
            created_paths: list[Path] = []

            def fake_write_windows_temp_file(name: str, content: str) -> Path:
                path = base / name
                path.write_text(content, encoding="utf-8")
                created_paths.append(path)
                return path

            def fake_run(args, check, capture_output):
                config_path = Path(args[2])
                config = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(config["debugUrl"], "http://127.0.0.1:9870")
                self.assertEqual(config["payloadPath"], str(payload_path))
                self.assertEqual(config["outputPath"], str(output_path))
                self.assertEqual(config["attachmentPaths"], [str(attachment_path)])
                return SimpleNamespace(returncode=0, stdout=b'{"ok":true}', stderr=b"")

            with patch.object(review, "detect_windows_cdp_debug_url", return_value="http://127.0.0.1:9870"), patch.object(
                review, "write_windows_temp_file", side_effect=fake_write_windows_temp_file
            ), patch.object(review, "to_windows_path", side_effect=lambda path: str(path)), patch.object(
                review.subprocess, "run", side_effect=fake_run
            ):
                completed = review.run_windows_cdp_chatgpt(
                    payload_path=payload_path,
                    output_path=output_path,
                    attachment_paths=[attachment_path],
                    project_url="https://chatgpt.com/g/project",
                    model_label="ChatGPT 5.4 Pro",
                    model_strategy="select",
                    timeout_ms=123456,
                    begin_marker="BEGIN",
                    end_marker="END",
                    debug_url=None,
                    marker_suffix="unit",
                )

            self.assertEqual(completed.returncode, 0)
            self.assertTrue(payload_path.exists())
            self.assertFalse((base / "chatgpt-cdp-driver-unit.js").exists())
            self.assertFalse((base / "codex-chatgpt-cdp-unit.json").exists())
            self.assertEqual(len(created_paths), 2)

    def test_run_windows_cdp_chatgpt_fanout_preserves_partial_results_and_cleans_temp_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            created_temp_paths: list[Path] = []
            created_output_paths: list[Path] = []

            def fake_write_windows_temp_file(name: str, content: str) -> Path:
                path = base / name
                path.write_text(content, encoding="utf-8")
                created_temp_paths.append(path)
                return path

            def fake_windows_temp_path(name: str) -> Path:
                path = base / name
                created_output_paths.append(path)
                return path

            class FakeProcess:
                def __init__(self, config_path: Path):
                    self.config_path = config_path
                    self.calls: list[str] = []
                    config = json.loads(config_path.read_text(encoding="utf-8"))
                    output_path = Path(config["outputPath"])
                    if output_path.name.endswith("01.md"):
                        output_path.write_text(
                            json.dumps(
                                {
                                    "verdict": "pass",
                                    "summary": "ok",
                                    "must_fix": [],
                                    "risks": [],
                                    "tests": [],
                                    "follow_up_prompt": "",
                                },
                                ensure_ascii=False,
                            ),
                            encoding="utf-8",
                        )
                        self.returncode = 0
                    else:
                        self.returncode = 1

                def communicate(self):
                    self.calls.append("communicate")
                    return (b"", b"")

                def poll(self):
                    self.calls.append("poll")
                    return self.returncode

                def terminate(self):
                    self.calls.append("terminate")

                def wait(self, timeout: float):
                    self.calls.append(f"wait:{timeout}")
                    return self.returncode

                def kill(self):
                    self.calls.append("kill")

            processes: list[FakeProcess] = []

            def fake_popen(args, stdout, stderr):
                process = FakeProcess(Path(args[2]))
                processes.append(process)
                return process

            with patch.object(review, "detect_windows_cdp_debug_url", return_value="http://127.0.0.1:9870"), patch.object(
                review, "write_windows_temp_file", side_effect=fake_write_windows_temp_file
            ), patch.object(review, "windows_temp_path", side_effect=fake_windows_temp_path), patch.object(
                review, "to_windows_path", side_effect=lambda path: str(path)
            ), patch.object(review.subprocess, "Popen", side_effect=fake_popen):
                candidates = review.run_windows_cdp_chatgpt_fanout(
                    review_jobs=[
                        (1, "01-regression", "prompt-1"),
                        (2, "02-tests", "prompt-2"),
                    ],
                    attachment_paths=[base / "snapshot.zip"],
                    project_url="https://chatgpt.com/g/project",
                    model_label="ChatGPT 5.4 Pro",
                    model_strategy="ignore",
                    timeout_ms=123456,
                    debug_url=None,
                    marker_suffix="fanout",
                )

            self.assertEqual([candidate.returncode for candidate in candidates], [0, 1])
            self.assertIn('"verdict": "pass"', candidates[0].review_text)
            self.assertEqual(candidates[1].review_text, "")
            self.assertTrue(all(not path.exists() for path in created_temp_paths))
            self.assertTrue(all(not path.exists() for path in created_output_paths))
            self.assertFalse((base / "chatgpt-cdp-driver-fanout.js").exists())
            self.assertEqual([process.calls for process in processes], [["communicate", "poll"], ["communicate", "poll"]])

    def test_run_windows_cdp_chatgpt_fanout_preserves_original_error_when_cleanup_runs(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)

            def fake_write_windows_temp_file(name: str, content: str) -> Path:
                path = base / name
                path.write_text(content, encoding="utf-8")
                return path

            def fake_windows_temp_path(name: str) -> Path:
                return base / name

            class HangingProcess:
                def __init__(self, _config_path: Path):
                    self.calls: list[str] = []
                    self.wait_calls = 0

                def communicate(self):
                    self.calls.append("communicate")
                    raise RuntimeError("boom")

                def poll(self):
                    self.calls.append("poll")
                    return None

                def terminate(self):
                    self.calls.append("terminate")

                def wait(self, timeout: float):
                    self.wait_calls += 1
                    self.calls.append(f"wait:{timeout}")
                    if self.wait_calls == 1:
                        raise subprocess.TimeoutExpired(cmd="fake", timeout=timeout)
                    return 0

                def kill(self):
                    self.calls.append("kill")

            process = HangingProcess(base / "unused.json")

            def fake_popen(args, stdout, stderr):
                _ = stdout, stderr
                return process

            with patch.object(review, "detect_windows_cdp_debug_url", return_value="http://127.0.0.1:9870"), patch.object(
                review, "write_windows_temp_file", side_effect=fake_write_windows_temp_file
            ), patch.object(review, "windows_temp_path", side_effect=fake_windows_temp_path), patch.object(
                review, "to_windows_path", side_effect=lambda path: str(path)
            ), patch.object(review.subprocess, "Popen", side_effect=fake_popen):
                with self.assertRaisesRegex(RuntimeError, "boom"):
                    review.run_windows_cdp_chatgpt_fanout(
                        review_jobs=[(1, "01-regression", "prompt-1")],
                        attachment_paths=[base / "snapshot.zip"],
                        project_url="https://chatgpt.com/g/project",
                        model_label="ChatGPT 5.4 Pro",
                        model_strategy="ignore",
                        timeout_ms=123456,
                        debug_url=None,
                        marker_suffix="fanout-exc",
                    )

            self.assertEqual(
                process.calls,
                ["communicate", "poll", "terminate", "wait:5", "kill", "wait:5"],
            )


if __name__ == "__main__":
    unittest.main()
