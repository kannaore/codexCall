from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def load_loop_module():
    script_path = Path(__file__).resolve().parents[1] / "codex-gpt54-loop"
    loader = SourceFileLoader("codex_gpt54_loop", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loop = load_loop_module()


class ParseReviewDecisionTests(unittest.TestCase):
    def test_accepts_fenced_json_and_normalizes_fields(self):
        decision = loop.parse_review_decision(
            """```json
            {
              "verdict": "REVISE",
              "summary": "핵심 버그가 남아 있음",
              "must_fix": ["예외 처리 누락", "  "],
              "risks": "회귀 가능성 있음",
              "tests": null,
              "follow_up_prompt": "예외 경로를 보강해라"
            }
            ```"""
        )

        self.assertEqual(decision.verdict, "revise")
        self.assertEqual(decision.summary, "핵심 버그가 남아 있음")
        self.assertEqual(decision.must_fix, ["예외 처리 누락"])
        self.assertEqual(decision.risks, ["회귀 가능성 있음"])
        self.assertEqual(decision.tests, [])
        self.assertEqual(decision.follow_up_prompt, "예외 경로를 보강해라")

    def test_rejects_invalid_verdict(self):
        with self.assertRaises(ValueError):
            loop.parse_review_decision('{"verdict":"maybe"}')


class PromptFormattingTests(unittest.TestCase):
    def test_build_follow_up_prompt_skips_empty_sections(self):
        review = loop.ReviewDecision(
            verdict="revise",
            summary="인증 흐름이 불안정함",
            must_fix=["토큰 만료 처리 보강"],
            risks=[],
            tests=["만료 토큰 회귀 테스트 추가"],
            follow_up_prompt="401 재시도 분기를 정리해라",
            raw={},
        )

        prompt = loop.build_follow_up_prompt(review)

        self.assertIn("요약: 인증 흐름이 불안정함", prompt)
        self.assertIn("반드시 고칠 것:", prompt)
        self.assertIn("보강할 테스트:", prompt)
        self.assertIn("리뷰어 후속 지시:", prompt)
        self.assertNotIn("추가 리스크:", prompt)

    def test_build_follow_up_prompt_includes_selected_review_artifacts(self):
        review = loop.ReviewDecision(
            verdict="revise",
            summary="예외 처리 누락",
            must_fix=["timeout 예외 처리 추가"],
            risks=[],
            tests=[],
            follow_up_prompt="timeout 실패 분기를 구현해라",
            raw={},
        )
        candidate_manifest = {
            "aggregate": {
                "selected_candidate": 2,
                "selected_label": "02-edge-cases",
                "valid_candidate_count": 5,
                "revise_count": 4,
                "selected_review_path": "/tmp/review-02.txt",
                "selected_prompt_path": "/tmp/review-02.prompt.md",
            }
        }

        prompt = loop.build_follow_up_prompt(review, candidate_manifest)

        self.assertIn("병렬 리뷰 취합:", prompt)
        self.assertIn("유효 리뷰 5개", prompt)
        self.assertIn("revise 4개", prompt)
        self.assertIn("선택 후보 02 [02-edge-cases]", prompt)
        self.assertIn("선택된 저장 리뷰: /tmp/review-02.txt", prompt)
        self.assertIn("선택 후보 프롬프트: /tmp/review-02.prompt.md", prompt)

    def test_build_review_prompt_embeds_task_and_note(self):
        prompt = loop.build_review_prompt("로그인 버그 수정", "세션 만료 케이스를 특히 봐라")

        self.assertIn("Original user task:", prompt)
        self.assertIn("로그인 버그 수정", prompt)
        self.assertIn("Extra review emphasis:", prompt)
        self.assertIn("세션 만료 케이스를 특히 봐라", prompt)
        self.assertIn('"verdict": "pass" | "revise"', prompt)


class CommandBuildingTests(unittest.TestCase):
    def make_args(self, **overrides):
        payload = {
            "codex_model": None,
            "codex_profile": None,
            "codex_full_auto": False,
            "codex_bypass_approvals": False,
            "codex_session_id": None,
            "codex_resume_last": False,
        }
        payload.update(overrides)
        return SimpleNamespace(**payload)

    def test_build_codex_command_uses_existing_session_id(self):
        repo_root = Path("/tmp/repo")
        message_path = Path("/tmp/message.md")

        command = loop.build_codex_command(
            repo_root=repo_root,
            thread_id=None,
            message_path=message_path,
            args=self.make_args(codex_session_id="session-123"),
        )

        self.assertEqual(command[:4], ["codex", "exec", "resume", "--json"])
        self.assertEqual(command[-2:], ["session-123", "-"])

    def test_build_codex_command_uses_last_session_when_requested(self):
        repo_root = Path("/tmp/repo")
        message_path = Path("/tmp/message.md")

        command = loop.build_codex_command(
            repo_root=repo_root,
            thread_id=None,
            message_path=message_path,
            args=self.make_args(codex_resume_last=True),
        )

        self.assertEqual(command[:4], ["codex", "exec", "resume", "--json"])
        self.assertEqual(command[-2:], ["--last", "-"])


class GitFilteringTests(unittest.TestCase):
    def test_has_repo_changes_ignores_loop_artifacts_and_pycaches(self):
        with patch.object(
            loop,
            "run_command",
            return_value=SimpleNamespace(
                returncode=0,
                stdout="?? .oracle-reviews/live-automation/manifest.json\n?? __pycache__/test_app.cpython-312.pyc\n",
                stderr="",
            ),
        ):
            changed = loop.has_repo_changes(Path("/tmp/repo"), session_dir=Path("/tmp/repo/.oracle-reviews/resume-smoke"))

        self.assertFalse(changed)

    def test_has_repo_changes_detects_real_source_file_changes(self):
        with patch.object(
            loop,
            "run_command",
            return_value=SimpleNamespace(returncode=0, stdout=" M app.py\n", stderr=""),
        ):
            changed = loop.has_repo_changes(Path("/tmp/repo"), session_dir=Path("/tmp/repo/.oracle-reviews/resume-smoke"))

        self.assertTrue(changed)


class MainLoopTests(unittest.TestCase):
    def test_run_review_round_forwards_fanout_options(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            session_dir = repo_root / "session"
            session_dir.mkdir(parents=True, exist_ok=True)
            review_path = session_dir / "round-01.review.json"
            review_path.write_text(
                json.dumps(
                    {
                        "verdict": "pass",
                        "summary": "문제 없음",
                        "must_fix": [],
                        "risks": [],
                        "tests": [],
                        "follow_up_prompt": "",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            args = SimpleNamespace(
                review_mode="diff",
                include_untracked=False,
                review_delivery="cdp",
                review_model="ChatGPT 5.4 Pro",
                review_model_strategy="select",
                review_timeout_ms=123456,
                review_fanout_count=5,
                review_fanout_strategy="angled",
                cdp_debug_url="http://127.0.0.1:9999",
                no_project_url=False,
                project_url="https://chatgpt.com/g/project",
                review_files=["docs/spec.md"],
                review_note="",
            )

            with patch.object(loop, "has_untracked_files", return_value=False), patch.object(
                loop,
                "run_command",
                return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
            ) as run_command:
                review, _review_path = loop.run_review_round(
                    repo_root=repo_root,
                    round_index=1,
                    task="로그인 버그 수정",
                    session_dir=session_dir,
                    args=args,
                )

            self.assertEqual(review.verdict, "pass")
            command = run_command.call_args.args[0]
            self.assertIn("--fanout-count", command)
            self.assertIn("5", command)
            self.assertIn("--fanout-strategy", command)
            self.assertIn("angled", command)

    def test_main_stops_after_pass_review_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            session_dir = repo_root / "session"
            review = loop.ReviewDecision(
                verdict="pass",
                summary="문제 없음",
                must_fix=[],
                risks=[],
                tests=["회귀 테스트 확인"],
                follow_up_prompt="",
                raw={},
            )

            with patch.object(loop, "detect_repo_root", return_value=repo_root), patch.object(
                loop, "run_codex_round", return_value="thread-1"
            ) as run_codex_round, patch.object(loop, "has_repo_changes", return_value=True), patch.object(
                loop, "run_review_round", return_value=(review, session_dir / "round-01.review.json")
            ) as run_review_round:
                exit_code = loop.main(
                    ["--repo", str(repo_root), "--session-dir", str(session_dir), "로그인 버그 수정"]
                )

            self.assertEqual(exit_code, 0)
            run_codex_round.assert_called_once()
            run_review_round.assert_called_once()

            manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "passed")
            self.assertEqual(manifest["thread_id"], "thread-1")
            self.assertEqual(len(manifest["rounds"]), 1)
            self.assertEqual(manifest["rounds"][0]["status"], "pass")
            self.assertEqual(manifest["rounds"][0]["review_summary"], "문제 없음")

    def test_main_feeds_follow_up_prompt_into_second_round_after_revise(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            session_dir = repo_root / "session"
            review_path = session_dir / "round-01.review.json"
            candidate_dir = session_dir / "round-01.review.json.candidates"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            (candidate_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "aggregate": {
                            "selected_candidate": 2,
                            "selected_label": "02-edge-cases",
                            "valid_candidate_count": 5,
                            "revise_count": 5,
                            "selected_review_path": str(candidate_dir / "candidate-02-02-edge-cases.txt"),
                            "selected_prompt_path": str(candidate_dir / "candidate-02-02-edge-cases.prompt.md"),
                        },
                        "candidates": [],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            review = loop.ReviewDecision(
                verdict="revise",
                summary="예외 경로 누락",
                must_fix=["timeout 예외 처리 추가"],
                risks=["재시도 폭주 가능성"],
                tests=["timeout 회귀 테스트"],
                follow_up_prompt="timeout 실패 분기를 구현해라",
                raw={},
            )
            prompts: list[str] = []

            def fake_run_codex_round(*, prompt, **_kwargs):
                prompts.append(prompt)
                return f"thread-{len(prompts)}"

            with patch.object(loop, "detect_repo_root", return_value=repo_root), patch.object(
                loop, "run_codex_round", side_effect=fake_run_codex_round
            ), patch.object(loop, "has_repo_changes", return_value=True), patch.object(
                loop, "run_review_round", return_value=(review, review_path)
            ):
                exit_code = loop.main(
                    [
                        "--repo",
                        str(repo_root),
                        "--session-dir",
                        str(session_dir),
                        "--max-rounds",
                        "2",
                        "파일 업로드 race condition 수정",
                    ]
                )

            self.assertEqual(exit_code, 3)
            self.assertEqual(len(prompts), 2)
            self.assertEqual(prompts[0], "파일 업로드 race condition 수정")
            self.assertIn("병렬 리뷰 취합:", prompts[1])
            self.assertIn("선택 후보 02 [02-edge-cases]", prompts[1])
            self.assertIn("반드시 고칠 것:", prompts[1])
            self.assertIn("timeout 예외 처리 추가", prompts[1])
            self.assertIn("리뷰어 후속 지시:", prompts[1])

            manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "max-rounds")
            self.assertEqual(len(manifest["rounds"]), 2)
            self.assertEqual(manifest["rounds"][0]["status"], "revise")
            self.assertEqual(manifest["rounds"][1]["status"], "revise")
            self.assertEqual(manifest["rounds"][0]["review_selected_candidate"], 2)
            self.assertTrue(manifest["rounds"][0]["review_selected_review_path"].endswith("candidate-02-02-edge-cases.txt"))
            self.assertTrue((session_dir / "round-01.followup.md").exists())

    def test_main_skips_review_when_codex_makes_no_changes(self):
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir)
            session_dir = repo_root / "session"

            with patch.object(loop, "detect_repo_root", return_value=repo_root), patch.object(
                loop, "run_codex_round", return_value="thread-1"
            ), patch.object(loop, "has_repo_changes", return_value=False), patch.object(
                loop, "run_review_round"
            ) as run_review_round:
                exit_code = loop.main(
                    ["--repo", str(repo_root), "--session-dir", str(session_dir), "문서만 갱신"]
                )

            self.assertEqual(exit_code, 0)
            run_review_round.assert_not_called()

            manifest = json.loads((session_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "stopped-no-changes")
            self.assertEqual(manifest["rounds"][0]["status"], "no_changes")

    def test_main_rejects_conflicting_session_resume_options(self):
        exit_code = loop.main(
            [
                "--codex-session-id",
                "session-123",
                "--codex-resume-last",
                "현재 세션에 후속 작업 주입",
            ]
        )

        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
