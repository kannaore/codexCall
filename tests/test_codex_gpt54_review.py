from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path


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


class ReviewAggregationTests(unittest.TestCase):
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

        aggregated_text, metadata = review.aggregate_structured_candidates(candidates)
        payload = json.loads(aggregated_text)

        self.assertEqual(payload["verdict"], "revise")
        self.assertEqual(payload["must_fix"], ["timeout 예외 처리 추가"])
        self.assertEqual(payload["tests"], ["timeout 회귀 테스트", "성공 경로 테스트"])
        self.assertEqual(payload["follow_up_prompt"], "timeout 실패 분기를 구현해라")
        self.assertEqual(metadata["mode"], "structured-consensus")
        self.assertEqual(metadata["selected_candidate"], 1)

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

        aggregated_text, metadata = review.aggregate_review_candidates(candidates)

        self.assertEqual(aggregated_text, "핵심 피드백\n리스크\n테스트 보강\n바로 고칠 것")
        self.assertEqual(metadata["selected_candidate"], 2)
        self.assertEqual(metadata["mode"], "best-text")


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


if __name__ == "__main__":
    unittest.main()
