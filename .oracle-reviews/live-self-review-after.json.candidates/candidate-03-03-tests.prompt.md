You are reviewing a local coding change from Codex.
Return the final answer in Korean.
Wrap the full answer exactly between these markers:
BEGIN_CDX_REVIEW_20260311124853_03
END_CDX_REVIEW_20260311124853_03

# Codex Review Context

Repository: 호출기
Path: /home/mrcorp/Coding/Tools/호출기
Branch: main

## Requested Review
You are the secondary reviewer in a recursive Codex improvement loop.
Judge only the attached local changes and their likely behavior.

Original user task:
호출기의 실제 GPT-5.4 Pro 리뷰 워크플로우를 적용해 보고, 이번 수정 뒤에도 남은 문제만 지적해.

Return JSON only with this schema:
{
  "verdict": "pass" | "revise",
  "summary": "string",
  "must_fix": ["string"],
  "risks": ["string"],
  "tests": ["string"],
  "follow_up_prompt": "string"
}

Rules:
- Use verdict "pass" only when there are no material bugs, regressions, or missing tests left to address.
- Minor style nits alone should still be "pass".
- Ground every claim in the attached diff/files. Do not invent missing context.
- Keep every string concise and in Korean.
- must_fix, risks, and tests should each contain up to 5 items.
- follow_up_prompt should be empty when verdict is "pass".
- follow_up_prompt should be a compact instruction Codex can act on immediately when verdict is "revise".
- Do not wrap the JSON in markdown fences.

Extra review emphasis:
특히 fanout cleanup kill->wait, cleanup 예외 비마스킹, 단일 경로 temp 정리, 부분 완료 candidate 보존, 테스트 적정성을 엄격히 봐라.

## Selected Files
- codex-gpt54-review
- tests/test_codex_gpt54_review.py
- tests/test_codex_gpt54_loop.py

## Git Status
```text
M __pycache__/codex-gpt54-reviewcpython-312.pyc
 M codex-gpt54-review
 M tests/__pycache__/test_codex_gpt54_review.cpython-312.pyc
 M tests/test_codex_gpt54_review.py
?? .oracle-reviews/
```

## Diff Stat
```text
__pycache__/codex-gpt54-reviewcpython-312.pyc      | Bin 55710 -> 53632 bytes
 codex-gpt54-review                                 | 115 +++++-----
 .../test_codex_gpt54_review.cpython-312.pyc        | Bin 8165 -> 28559 bytes
 tests/test_codex_gpt54_review.py                   | 255 +++++++++++++++++++++
 4 files changed, 313 insertions(+), 57 deletions(-)
```

## Attached Material

### tmph_1vl1sa.oracle-context.md
```text
# Git Diff Review Payload

## Status
```text
M __pycache__/codex-gpt54-reviewcpython-312.pyc
 M codex-gpt54-review
 M tests/__pycache__/test_codex_gpt54_review.cpython-312.pyc
 M tests/test_codex_gpt54_review.py
?? .oracle-reviews/
```

## Staged Diff
```diff
(none)
```

## Unstaged Diff
```diff
diff --git a/__pycache__/codex-gpt54-reviewcpython-312.pyc b/__pycache__/codex-gpt54-reviewcpython-312.pyc
index 828ad4ec89ecb2b43caecfb6a03df67277189c52..828d98a8ffa47dc372bac9aae0e381196eb049fb 100644
GIT binary patch
delta 6977
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

delta 7896
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

[truncated]

```


### codex-gpt54-review
```text
#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, Sequence


DEFAULT_PROMPT = """Review the attached local changes as a senior peer reviewer.
Focus on:
- bugs and behavioral regressions
- edge cases and failure modes
- missing or weak tests
- simpler or safer implementation choices

Respond in Korean with short sections:
1. 핵심 피드백
2. 리스크
3. 테스트 보강
4. 바로 고칠 것
"""

DEFAULT_PROJECT_URL = "https://chatgpt.com/g/g-p-69afcec40f908191b65f5b13357d45cf-codexjeonyong/project"
DEFAULT_OUTPUT_DIR = ".oracle-reviews"
DEFAULT_DELIVERY = "cdp"
DEFAULT_MODEL = "ChatGPT 5.4 Pro"
DEFAULT_MODEL_STRATEGY = "select"
DEFAULT_FANOUT_COUNT = 5
DEFAULT_FANOUT_STRATEGY = "angled"
WINDOWS_TEMP_DIR = Path("/mnt/c/Users/Administrator/AppData/Local/Temp")
WINDOWS_RUNNER_DIR = Path("/mnt/c/Users/Administrator/AppData/Local/CodexChatGPTRunner")
WINDOWS_NODE = "/mnt/c/Program Files/nodejs/node.exe"
MAX_FILE_CHARS = 12000
MAX_BUNDLE_CHARS = 100000

REVIEW_ANGLE_PRESETS: list[tuple[str, str]] = [
    ("regression", "이번 답변은 핵심 버그와 동작 회귀 가능성을 가장 엄격하게 본다."),
    ("edge-cases", "이번 답변은 경계값, 예외 경로, 실패 모드를 우선 검토한다."),
    ("tests", "이번 답변은 빠진 테스트, 재현성, 회귀 방지 측면을 우선 검토한다."),
    ("safety", "이번 답변은 더 단순하고 안전한 구현, 불필요한 복잡도, 유지보수 리스크를 우선 검토한다."),
    ("skeptic", "이번 답변은 과도한 지적을 줄이고 실제 근거가 충분한 문제만 남기도록 검토한다."),
]


@dataclass
class ReviewCandidate:
    index: int
    label: str
    prompt_text: str
    review_text: str
    output_path: Path
    returncode: int
    stdout_text: str
    stderr_text: str
    metadata: dict[str, object]


def run_command(args: Sequence[str], cwd: Path) -> str:
    result = subprocess.run(
        list(args),
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def split_non_empty(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def ensure_text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    for candidate in candidates:
        if not candidate:
            continue
        try:
            loaded = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(loaded, dict):
            return loaded

    raise ValueError("Review output was not valid JSON.")


def build_review_variants(base_prompt: str, count: int, strategy: str) -> list[tuple[str, str]]:
    prompt_text = base_prompt.strip()
    if count < 1:
        raise ValueError("fanout count must be at least 1")

    variants: list[tuple[str, str]] = []
    if strategy == "identical":
        for index in range(count):
            variants.append((f"candidate-{index + 1:02d}", prompt_text))
        return variants

    if strategy != "angled":
        raise ValueError(f"Unsupported fanout strategy: {strategy}")

    for index in range(count):
        label, lens = REVIEW_ANGLE_PRESETS[index % len(REVIEW_ANGLE_PRESETS)]
        prompt = (
            f"{prompt_text}\n\n"
            "Extra review lens for this run:\n"
            f"- {lens}"
        )
        variants.append((f"{index + 1:02d}-{label}", prompt))
    return variants


def rank_text_items(values: list[list[str]], *, limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    first_seen: dict[str, tuple[int, int]] = {}
    for candidate_index, items in enumerate(values):
        for item_index, item in enumerate(items):
            text = item.strip()
            if not text:
                continue
            counts[text] += 1
            first_seen.setdefault(text, (candidate_index, item_index))
    ranked = sorted(counts, key=lambda text: (-counts[text], first_seen[text][0], first_seen[text][1], text))
    return ranked[:limit]


def score_structured_payload(payload: dict[str, object]) -> tuple[int, int]:
    verdict = str(payload.get("verdict", "")).strip().lower()
    must_fix = ensure_text_list(payload.get("must_fix"))
    risks = ensure_text_list(payload.get("risks"))
    tests = ensure_text_list(payload.get("tests"))
    follow_up = str(payload.get("follow_up_prompt", "")).strip()
    summary = str(payload.get("summary", "")).strip()
    primary = 0
    if verdict == "revise":
        primary += 100
    primary += len(must_fix) * 20
    primary += len(tests) * 12
    primary += len(risks) * 8
    if follow_up:
        primary += 10
    return primary, len(summary)


def build_consensus_follow_up(must_fix: list[str], tests: list[str], anchor_prompt: str) -> str:
    if anchor_prompt.strip():
        return anchor_prompt.strip()
    parts: list[str] = []
    if must_fix:
        parts.append("다음 문제를 먼저 수정해라: " + "; ".join(must_fix[:3]))
    if tests:
        parts.append("그리고 테스트를 보강해라: " + "; ".join(tests[:2]))
    return " ".join(parts).strip()


def aggregate_structured_candidates(candidates: Sequence[ReviewCandidate]) -> tuple[str, dict[str, object]]:
    parsed: list[tuple[ReviewCandidate, dict[str, object]]] = []
    for candidate in candidates:
        try:
            payload = extract_json_object(candidate.review_text)
        except ValueError:
            continue
        verdict = str(payload.get("verdict", "")).strip().lower()
        if verdict not in {"pass", "revise"}:
            continue
        parsed.append((candidate, payload))

    if not parsed:
        raise ValueError("No valid structured review response was found.")

    revise = [(candidate, payload) for candidate, payload in parsed if str(payload.get("verdict", "")).strip().lower() == "revise"]
    anchor_source = revise if revise else parsed
    anchor_candidate, anchor_payload = max(anchor_source, key=lambda item: score_structured_payload(item[1]))

    must_fix = rank_text_items([ensure_text_list(payload.get("must_fix")) for _candidate, payload in parsed])
    risks = rank_text_items([ensure_text_list(payload.get("risks")) for _candidate, payload in parsed])
    tests = rank_text_items([ensure_text_list(payload.get("tests")) for _candidate, payload in parsed])
    follow_up_prompt = ""
    verdict = "pass" if not revise else "revise"
    if verdict == "revise":
        follow_up_prompt = build_consensus_follow_up(
            must_fix,
            tests,
            str(anchor_payload.get("follow_up_prompt", "")).strip(),
        )

    summary = str(anchor_payload.get("summary", "")).strip()
    if verdict == "revise" and not summary:
        summary = "여러 리뷰에서 수정 필요 항목이 확인되었다."
    if verdict == "pass" and not summary:
        summary = "여러 리뷰에서 치명적 문제는 발견되지 않았다."

    aggregated = {
        "verdict": verdict,
        "summary": summary,
        "must_fix": must_fix,
        "risks": risks,
        "tests": tests,
        "follow_up_prompt": follow_up_prompt,
    }
    metadata = {
        "mode": "structured-consensus",
        "selected_candidate": anchor_candidate.index,
        "selected_label": anchor_candidate.label,
        "valid_candidate_count": len(parsed),
        "revise_count": len(revise),
    }
    return json.dumps(aggregated, ensure_ascii=False, indent=2) + "\n", metadata


def score_plaintext_review(text: str) -> tuple[int, int]:
    body = text.strip()
    score = len(body)
    for keyword in ("핵심", "리스크", "테스트", "바로 고칠 것", "must_fix", "follow_up_prompt"):
        if keyword in body:
            score += 120
    score += min(len(split_non_empty(body)), 12) * 25
    return score, len(body)


def aggregate_plaintext_candidates(candidates: Sequence[ReviewCandidate]) -> tuple[str, dict[str, object]]:
    selected = max(candidates, key=lambda candidate: score_plaintext_review(candidate.review_text))
    metadata = {
        "mode": "best-text",
        "selected_candidate": selected.index,
        "selected_label": selected.label,
        "valid_candidate_count": len(candidates),
    }
    return selected.review_text, metadata


def aggregate_review_candidates(candidates: Sequence[ReviewCandidate]) -> tuple[str, dict[str, object]]:
    try:
        return aggregate_structured_candidates(candidates)
    except ValueError:
        return aggregate_plaintext_candidates(candidates)


def is_reviewable_path(path: Path) -> bool:
    return path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"


def dedupe_paths(paths: Iterable[Path]) -> list[Path]:
    seen: set[str] = set()
    selected: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        key = str(resolved)
        if key in seen or not resolved.exists() or not is_reviewable_path(resolved):
            continue
        seen.add(key)
        selected.append(resolved)
    return selected


def detect_repo_root(start: Path) -> Path:
    return Path(run_command(["git", "rev-parse", "--show-toplevel"], start))


def detect_branch(repo_root: Path) -> str:
    return run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)


def gather_changed_files(repo_root: Path, *, include_untracked: bool) -> list[Path]:
    staged = split_non_empty(run_command(["git", "diff", "--name-only", "--cached", "--diff-filter=ACMR"], repo_root))
    unstaged = split_non_empty(run_command(["git", "diff", "--name-only", "--diff-filter=ACMR"], repo_root))
    selected = [repo_root / path for path in [*staged, *unstaged]]
    if include_untracked:
        untracked = split_non_empty(run_command(["git", "ls-files", "--others", "--exclude-standard"], repo_root))
        selected.extend(repo_root / path for path in untracked)
    return dedupe_paths(selected)


def build_diff_payload(repo_root: Path) -> str:
    status_text = run_command(["git", "status", "--short"], repo_root)
    staged_diff = run_command(["git", "diff", "--cached", "--find-renames", "--binary", "HEAD"], repo_root)
    unstaged_diff = run_command(["git", "diff", "--find-renames", "--binary"], repo_root)
    return (
        "# Git Diff Review Payload\n\n"
        "## Status\n"
        "```text\n"
        f"{status_text or '(clean working tree)'}\n"
        "```\n\n"
        "## Staged Diff\n"
        "```diff\n"
        f"{staged_diff or '(none)'}\n"
        "```\n\n"
        "## Unstaged Diff\n"
        "```diff\n"
        f"{unstaged_diff or '(none)'}\n"
        "```\n"
    )


def build_context_markdown(
    *,
    repo_root: Path,
    branch: str,
    prompt_text: str,
    selected_files: Sequence[Path],
    status_text: str,
    diff_stat: str,
) -> str:
    rel_files = []
    for path in selected_files:
        try:
            rel_files.append(str(path.relative_to(repo_root)))
        except ValueError:
            rel_files.append(str(path))
    files_block = "\n".join(f"- {path}" for path in rel_files) or "- (none)"
    return f"""# Codex Review Context

Repository: {repo_root.name}
Path: {repo_root}
Branch: {branch}

## Requested Review
{prompt_text.strip()}

## Selected Files
{files_block}

## Git Status
```text
{status_text or "(clean working tree)"}
```

## Diff Stat
```text
{diff_stat or "(no diff stat available)"}
```
"""


def create_temp_context(content: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encodi

[truncated]

```


### test_codex_gpt54_review.py
```text
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
    def test_run_windows_cdp_chatgpt_cleans_driver_and_config_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            payload_path = base / "payload.txt"
            payload_path.write_text("prompt", encoding="utf-8")
            output_path = base / "output.md"
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
                return SimpleNamespace(returncode=0, stdout=b'{"ok":true}', stderr=b"")

            with patch.object(review, "detect_windows_cdp_debug_url", return_value="http://127.0.0.1:9870"), patch.object(
                review, "write_windows_temp_file", side_effect=fake_write_windows_temp_file
            ), patch.object(review, "to_windows_path", side_effect=lambda path: str(path)), patch.object(
                review.subprocess, "run", side_effect=fake_run
            ):
                completed = review.run_windows_cdp_chatgpt(
                    payload_path=payload_path,
                    output_path=output_path,
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

                def wait(se

[truncated]

```


### test_codex_gpt54_loop.py
```text
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
   

[truncated]

```


## Review Request

You are the secondary reviewer in a recursive Codex improvement loop.
Judge only the attached local changes and their likely behavior.

Original user task:
호출기의 실제 GPT-5.4 Pro 리뷰 워크플로우를 적용해 보고, 이번 수정 뒤에도 남은 문제만 지적해.

Return JSON only with this schema:
{
  "verdict": "pass" | "revise",
  "summary": "string",
  "must_fix": ["string"],
  "risks": ["string"],
  "tests": ["string"],
  "follow_up_prompt": "string"
}

Rules:
- Use verdict "pass" only when there are no material bugs, regressions, or missing tests left to address.
- Minor style nits alone should still be "pass".
- Ground every claim in the attached diff/files. Do not invent missing context.
- Keep every string concise and in Korean.
- must_fix, risks, and tests should each contain up to 5 items.
- follow_up_prompt should be empty when verdict is "pass".
- follow_up_prompt should be a compact instruction Codex can act on immediately when verdict is "revise".
- Do not wrap the JSON in markdown fences.

Extra review emphasis:
특히 fanout cleanup kill->wait, cleanup 예외 비마스킹, 단일 경로 temp 정리, 부분 완료 candidate 보존, 테스트 적정성을 엄격히 봐라.

Extra review lens for this run:
- 이번 답변은 빠진 테스트, 재현성, 회귀 방지 측면을 우선 검토한다.