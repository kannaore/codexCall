You are reviewing a local coding change from Codex.
Return the final answer in Korean.
Wrap the full answer exactly between these markers:
BEGIN_CDX_REVIEW_20260311133035_01
END_CDX_REVIEW_20260311133035_01

# Codex Review Context

Repository: 호출기
Path: /home/mrcorp/Coding/Tools/호출기
Branch: main

## Requested Review
You are the secondary reviewer in a recursive Codex improvement loop.
Judge only the attached local code and its likely behavior.

Original user task:
호출기 핵심 소스 코드를 검토해서, 지금 시점에 남은 실제 개선점만 지적해.

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
- Ground every claim in the attached files only. Do not invent missing context.
- Keep every string concise and in Korean.
- must_fix, risks, and tests should each contain up to 5 items.
- follow_up_prompt should be empty when verdict is "pass".
- follow_up_prompt should be a compact instruction Codex can act on immediately when verdict is "revise".
- Do not wrap the JSON in markdown fences.

Extra review emphasis:
프롬프트 주입 정확성, ChatGPT 리뷰 회수 신뢰성, fanout 부분 성공 처리, 장시간 대기/타임아웃 경계, loop에서 review artifact를 소비하는 경계를 엄격히 봐라.

## Selected Files
- codex-gpt54-review
- codex-gpt54-loop
- chatgpt-cdp-smoke.js

## Git Status
```text
M chatgpt-cdp-smoke.js
 M codex-gpt54-review
 M tests/test_codex_gpt54_review.py
?? .oracle-reviews/codebase-improvement-review.json.candidates/candidate-01-01-regression.prompt.md
?? .oracle-reviews/codebase-improvement-review.json.candidates/candidate-02-02-edge-cases.prompt.md
?? .oracle-reviews/codebase-improvement-review.json.candidates/candidate-03-03-tests.prompt.md
?? .oracle-reviews/codebase-improvement-review.json.candidates/candidate-04-04-safety.prompt.md
?? .oracle-reviews/codebase-improvement-review.json.candidates/candidate-05-05-skeptic.prompt.md
?? .oracle-reviews/codebase-improvement-review.prompt.md
```

## Diff Stat
```text
chatgpt-cdp-smoke.js             | 62 ++++++++++++++++++++++++++++++++---
 codex-gpt54-review               | 42 ++++++++++++++++++++----
 tests/test_codex_gpt54_review.py | 70 ++++++++++++++++++++++++++++++++++++++++
 3 files changed, 163 insertions(+), 11 deletions(-)
```

## Attached Material

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


def reviewable_git_paths(repo_root: Path) -> list[str]:
    rel_paths: list[str] = []
    for path in gather_changed_files(repo_root, include_untracked=True):
        try:
            rel_paths.append(str(path.relative_to(repo_root)))
        except ValueError:
            continue
    return rel_paths


def build_review_status_text(repo_root: Path) -> str:
    rel_paths = reviewable_git_paths(repo_root)
    if not rel_paths:
        return ""
    return run_command(["git", "status", "--short", "--", *rel_paths], repo_root)


def build_review_diff_stat(repo_root: Path) -> str:
    rel_paths = reviewable_git_paths(repo_root)
    if not rel_paths:
        return ""
    return run_command(["git", "diff", "--stat", "HEAD", "--", *rel_paths], repo_root)


def build_diff_payload(repo_root: Path) -> str:
    rel_paths = reviewable_git_paths(repo_root)
    if rel_paths:
        status_text = run_command(["git", "status", "--short", "--", *rel_paths], repo_root)
        staged_diff = run_command(["git", "diff", "--cached", "--find-renames", "HEAD", "--", *rel_paths], repo_root)
        unstaged_diff = run_command(["git", "diff", "--find-renames", "--", *rel_paths], repo_root)
    else:
        status_text = ""
        staged_diff = ""
        unstaged_diff = ""
    return (
        "# Git Diff Review Payload\n\n"
        "## Status\n"
        "```text\n"
        f"{status_text or '(no reviewable changed files)'}\n"
        "```\n\n"
        "## Staged Diff\n"
        "```diff\n"
        f"{staged_diff or '(none)'}\n"
        "```\n\n"
        "## Unstaged D

[truncated]

```


### codex-gpt54-loop
```text
#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence


DEFAULT_OUTPUT_DIR = ".oracle-reviews"
DEFAULT_MAX_ROUNDS = 3
DEFAULT_REVIEW_MODEL = "ChatGPT 5.4 Pro"
DEFAULT_REVIEW_MODEL_STRATEGY = "select"
DEFAULT_REVIEW_DELIVERY = "cdp"
DEFAULT_REVIEW_MODE = "diff"
DEFAULT_REVIEW_TIMEOUT_MS = 900000
DEFAULT_REVIEW_FANOUT_COUNT = 5
DEFAULT_REVIEW_FANOUT_STRATEGY = "angled"


@dataclass
class ReviewDecision:
    verdict: str
    summary: str
    must_fix: list[str]
    risks: list[str]
    tests: list[str]
    follow_up_prompt: str
    raw: dict[str, Any]


def run_command(
    args: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        cwd=str(cwd) if cwd else None,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )


def detect_repo_root(start: Path) -> Path:
    result = run_command(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "Failed to detect git repository.")
    return Path(result.stdout.strip()).resolve()


def read_task(task_arg: str | None) -> str:
    if task_arg == "-":
        return sys.stdin.read().strip()
    if task_arg:
        return task_arg.strip()
    return ""


def ensure_text_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def extract_json_object(text: str) -> dict[str, Any]:
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


def parse_review_decision(text: str) -> ReviewDecision:
    payload = extract_json_object(text)
    verdict = str(payload.get("verdict", "")).strip().lower()
    if verdict not in {"pass", "revise"}:
        raise ValueError("Review verdict must be 'pass' or 'revise'.")
    return ReviewDecision(
        verdict=verdict,
        summary=str(payload.get("summary", "")).strip(),
        must_fix=ensure_text_list(payload.get("must_fix")),
        risks=ensure_text_list(payload.get("risks")),
        tests=ensure_text_list(payload.get("tests")),
        follow_up_prompt=str(payload.get("follow_up_prompt", "")).strip(),
        raw=payload,
    )


def parse_thread_id(jsonl_text: str) -> str:
    for line in jsonl_text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") == "thread.started":
            thread_id = payload.get("thread_id")
            if thread_id:
                return str(thread_id)
    raise ValueError("Codex session id was not found in JSON output.")


def has_repo_changes(repo_root: Path, *, session_dir: Path | None = None) -> bool:
    result = run_command(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed.")
    return any(
        is_reviewable_status_path(path, session_dir=session_dir)
        for _status, path in iter_status_entries(repo_root, result.stdout)
    )


def has_untracked_files(repo_root: Path, *, session_dir: Path | None = None) -> bool:
    result = run_command(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed.")
    for line in result.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        if is_reviewable_status_path(repo_root / text, session_dir=session_dir):
            return True
    return False


def iter_status_entries(repo_root: Path, status_text: str) -> list[tuple[str, Path]]:
    entries: list[tuple[str, Path]] = []
    for raw_line in status_text.splitlines():
        if not raw_line.strip():
            continue
        status = raw_line[:2]
        path_text = raw_line[3:].strip()
        if " -> " in path_text:
            path_text = path_text.split(" -> ", 1)[1].strip()
        entries.append((status, repo_root / path_text))
    return entries


def is_reviewable_status_path(path: Path, *, session_dir: Path | None) -> bool:
    if session_dir is not None:
        try:
            path.relative_to(session_dir)
            return False
        except ValueError:
            pass
    return DEFAULT_OUTPUT_DIR not in path.parts and "__pycache__" not in path.parts and path.suffix != ".pyc"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_review_prompt(task: str, note: str) -> str:
    sections = [
        "You are the secondary reviewer in a recursive Codex improvement loop.",
        "Judge only the attached local changes and their likely behavior.",
        "",
        "Original user task:",
        task.strip(),
        "",
        "Return JSON only with this schema:",
        "{",
        '  "verdict": "pass" | "revise",',
        '  "summary": "string",',
        '  "must_fix": ["string"],',
        '  "risks": ["string"],',
        '  "tests": ["string"],',
        '  "follow_up_prompt": "string"',
        "}",
        "",
        "Rules:",
        "- Use verdict 'pass' only when there are no material bugs, regressions, or missing tests left to address.",
        "- Minor style nits alone should still be 'pass'.",
        "- Ground every claim in the attached diff/files. Do not invent missing context.",
        "- Keep every string concise and in Korean.",
        "- `must_fix`, `risks`, and `tests` should each contain up to 5 items.",
        "- `follow_up_prompt` should be empty when verdict is 'pass'.",
        "- `follow_up_prompt` should be a compact instruction Codex can act on immediately when verdict is 'revise'.",
        "- Do not wrap the JSON in markdown fences.",
    ]
    if note.strip():
        sections.extend(["", "Extra review emphasis:", note.strip()])
    return "\n".join(sections)


def bullet_block(title: str, items: Sequence[str]) -> str:
    if not items:
        return ""
    return title + "\n" + "\n".join(f"- {item}" for item in items)


def review_candidate_manifest_path(review_path: Path) -> Path:
    return review_path.parent / f"{review_path.name}.candidates" / "manifest.json"


def load_review_candidate_manifest(review_path: Path) -> dict[str, Any] | None:
    manifest_path = review_candidate_manifest_path(review_path)
    if not manifest_path.exists():
        return None
    try:
        loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def build_follow_up_prompt(review: ReviewDecision, candidate_manifest: dict[str, Any] | None = None) -> str:
    parts = [
        "다음은 웹 ChatGPT의 코드 리뷰 결과다. 실제 코드와 대조해서 타당한 지적만 반영하고 수정해라.",
    ]
    aggregate = candidate_manifest.get("aggregate") if isinstance(candidate_manifest, dict) else None
    if isinstance(aggregate, dict):
        candidate_count = aggregate.get("valid_candidate_count")
        revise_count = aggregate.get("revise_count")
        selected_candidate = aggregate.get("selected_candidate")
        selected_label = str(aggregate.get("selected_label", "")).strip()
        selected_review_path = str(aggregate.get("selected_review_path", "")).strip()
        selected_prompt_path = str(aggregate.get("selected_prompt_path", "")).strip()
        summary_bits: list[str] = []
        if candidate_count not in {None, ""}:
            summary_bits.append(f"유효 리뷰 {candidate_count}개")
        if revise_count not in {None, ""}:
            summary_bits.append(f"revise {revise_count}개")
        if selected_candidate not in {None, ""}:
            if selected_label:
                summary_bits.append(f"선택 후보 {int(selected_candidate):02d} [{selected_label}]")
            else:
                summary_bits.append(f"선택 후보 {int(selected_candidate):02d}")
        if summary_bits:
            parts.append("병렬 리뷰 취합:\n- " + "\n- ".join(summary_bits))
        if selected_review_path:
            parts.append(f"선택된 저장 리뷰: {selected_review_path}")
        if selected_prompt_path:
            parts.append(f"선택 후보 프롬프트: {selected_prompt_path}")
    if review.summary:
        parts.append(f"요약: {review.summary}")
    must_fix_block = bullet_block("반드시 고칠 것:", review.must_fix)
    if must_fix_block:
        parts.append(must_fix_block)
    risk_block = bullet_block("추가 리스크:", review.risks)
    if risk_block:
        parts.append(risk_block)
    test_block = bullet_block("보강할 테스트:", review.tests)
    if test_block:
        parts.append(test_block)
    if review.follow_up_prompt:
        parts.append("리뷰어 후속 지시:\n" + review.follow_up_prompt)
    parts.append("수정 후에는 무엇을 바꿨고 어떤 테스트를 보강했는지 짧게 보고해라.")
    return "\n\n".join(parts)


def print_review_summary(round_index: int, review: ReviewDecision, review_path: Path) -> None:
    print(f"[round {round_index}] review verdict: {review.verdict}")
    if review.summary:
        print(f"  summary: {review.summary}")
    if review.must_fix:
        print("  must_fix:")
        for item in review.must_fix:
            print(f"    - {item}")
    if review.tests:
        print("  tests:")
        for item in review.tests:
            print(f"    - {item}")
    if review.risks:
        print("  risks:")
        for item in review.risks:
            print(f"    - {item}")
    print(f"  saved: {review_path}")


def confirm_manual_continue() -> bool:
    try:
        answer = input("Send this review back to Codex for another round? [Y/n]: ").strip().lower()
    except EOFError:
        return False
    return answer in {"", "y", "yes"}


def build_codex_command(
    *,
    repo_root: Path,
    thread_id: str | None,
    message_path: Path,
    args: argparse.Namespace,
) -> list[str]:
    resume_existing = bool(thread_id or args.codex_session_id or args.codex_resume_last)
    if resume_existing:
        command = ["codex", "exec", "resume", "--json", "-o", str(message_path)]
    else:
        command = ["codex", "exec", "--json", "-C", str(repo_root), "-o", str(message_path)]

    if args.codex_model:
        command.extend(["-m", args.codex_model])
    if args.codex_profile:
        command.extend(["-p", args.codex_profile])
    if args.codex_full_auto:
        command.append("--full-auto")
    if args.codex_bypass_approvals:
        command.append("--dangerously-bypass-approvals-and-sandbox")

    if resume_existing:
        if thread_id:
            command.extend([thread_id, "-"])
        elif args.codex_session_id:
            command.extend([args.codex_session_id, "-"])
        else:
            command.extend(["--last", "-"])
    else:
        command.append(

[truncated]

```


### chatgpt-cdp-smoke.js
```text
#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

function loadPlaywright() {
  try {
    return require("playwright");
  } catch (_error) {
    const localAppData = process.env.LOCALAPPDATA;
    if (!localAppData) {
      throw _error;
    }
    const runnerPath = path.join(localAppData, "CodexChatGPTRunner", "node_modules", "playwright");
    return require(runnerPath);
  }
}

async function main() {
  const [, , configPath] = process.argv;
  if (!configPath) {
    throw new Error("Usage: node chatgpt-cdp-smoke.js <config.json>");
  }

  const config = JSON.parse(fs.readFileSync(configPath, "utf8"));
  const {
    debugUrl,
    payloadPath,
    outputPath,
    beginMarker,
    endMarker,
    timeoutMs = 120000,
    connectTimeoutMs = 120000,
    projectUrl = "",
    modelLabel = "",
    modelStrategy = "ignore",
    preferNewPage = false,
    prepareOnly = false,
  } = config;

  if (!debugUrl) {
    throw new Error("Missing required config fields.");
  }
  if (!prepareOnly && (!payloadPath || !outputPath || !beginMarker || !endMarker)) {
    throw new Error("Missing required config fields.");
  }

  const payload = prepareOnly ? "" : fs.readFileSync(payloadPath, "utf8");
  const playwright = loadPlaywright();
  const browser = await playwright.chromium.connectOverCDP(debugUrl, { timeout: connectTimeoutMs });

  function normalizeModelLabel(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/chatgpt/g, "")
      .replace(/\s+/g, " ")
      .trim();
  }

  function modelTestIdForLabel(value) {
    const normalized = normalizeModelLabel(value);
    const entries = [
      [["5.3 instant", "instant 5.3", "gpt 5.3 instant"], "model-switcher-gpt-5-3-instant"],
      [["5.4 thinking", "thinking 5.4", "gpt 5.4 thinking"], "model-switcher-gpt-5-4-thinking"],
      [["5.4 pro", "pro 5.4", "gpt 5.4 pro"], "model-switcher-gpt-5-4-pro"],
    ];
    for (const [aliases, testId] of entries) {
      if (aliases.includes(normalized)) {
        return testId;
      }
    }
    return "";
  }

  async function readCurrentModelText(page) {
    const button = page.getByTestId("model-switcher-dropdown-button").first();
    await button.waitFor({ timeout: 20000 });
    const [text, aria] = await Promise.all([
      button.innerText().catch(() => ""),
      button.getAttribute("aria-label").catch(() => ""),
    ]);
    return `${text || ""} ${aria || ""}`.trim();
  }

  async function ensureModelSelection(page, desiredLabel, strategy) {
    if (!desiredLabel || strategy === "ignore") {
      return;
    }

    const currentText = await readCurrentModelText(page);
    const normalizedCurrent = normalizeModelLabel(currentText);
    const normalizedDesired = normalizeModelLabel(desiredLabel);
    if (normalizedCurrent.includes(normalizedDesired)) {
      return;
    }

    if (strategy === "current") {
      throw new Error(`Current ChatGPT model mismatch. Wanted "${desiredLabel}", but saw "${currentText}".`);
    }

    if (strategy !== "select") {
      throw new Error(`Unsupported model strategy: ${strategy}`);
    }

    const modelTestId = modelTestIdForLabel(desiredLabel);
    if (!modelTestId) {
      throw new Error(`Unsupported ChatGPT model label for automation: ${desiredLabel}`);
    }

    const button = page.getByTestId("model-switcher-dropdown-button").first();
    await button.click();
    const menuItem = page.getByTestId(modelTestId).first();
    await menuItem.waitFor({ timeout: 10000 });
    await menuItem.click();

    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      const afterText = await readCurrentModelText(page);
      if (normalizeModelLabel(afterText).includes(normalizedDesired)) {
        return;
      }
      await page.waitForTimeout(500);
    }

    const afterText = await readCurrentModelText(page);
    throw new Error(`Failed to switch ChatGPT model to "${desiredLabel}". Current button text: "${afterText}".`);
  }

  async function clearEditor(page, editor) {
    await editor.click();
    await page.keyboard.press("Control+A").catch(() => {});
    await page.keyboard.press("Backspace").catch(() => {});
    await editor.evaluate((node) => {
      node.textContent = "";
      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "deleteContentBackward", data: null }));
    }).catch(() => {});
  }

  function normalizePromptText(value) {
    return String(value || "").replace(/\s+/g, "");
  }

  async function readEditorText(editor) {
    const [innerText, textContent] = await Promise.all([
      editor.innerText().catch(() => ""),
      editor.evaluate((node) => node.textContent || "").catch(() => ""),
    ]);
    return { innerText, textContent };
  }

  function isPromptEquivalent(expected, actual) {
    return normalizePromptText(expected) === normalizePromptText(actual);
  }

  async function injectPromptViaDom(editor, payloadText) {
    await editor.evaluate((node, text) => {
      node.textContent = text;
      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
      node.dispatchEvent(new Event("change", { bubbles: true }));
    }, payloadText);
  }

  async function injectPromptViaInsertText(page, payloadText) {
    const chunks = [];
    const chunkSize = 4000;
    for (let index = 0; index < payloadText.length; index += chunkSize) {
      chunks.push(payloadText.slice(index, index + chunkSize));
    }
    for (const chunk of chunks) {
      await page.keyboard.insertText(chunk);
      await page.waitForTimeout(20);
    }
  }

  async function injectPromptViaClipboard(page, editor, payloadText) {
    await page.evaluate(async (text) => {
      await navigator.clipboard.writeText(text);
    }, payloadText);
    await editor.click();
    await page.keyboard.press("Control+V");
    await page.waitForTimeout(1000);
  }

  async function injectPrompt(page, editor, payloadText) {
    await clearEditor(page, editor);
    const strategies = [
      ["dom-set", async () => injectPromptViaDom(editor, payloadText)],
      ["clipboard", async () => injectPromptViaClipboard(page, editor, payloadText)],
      ["insert-text", async () => injectPromptViaInsertText(page, payloadText)],
    ];
    let lastError = "";
    for (const [label, action] of strategies) {
      await clearEditor(page, editor);
      try {
        await action();
        const { innerText, textContent } = await readEditorText(editor);
        if (isPromptEquivalent(payloadText, textContent) || isPromptEquivalent(payloadText, innerText)) {
          return;
        }
        lastError = `Prompt injection mismatch after ${label}. Expected ${payloadText.length} chars, saw innerText=${innerText.length}, textContent=${textContent.length}.`;
      } catch (error) {
        lastError = `Prompt injection failed via ${label}: ${String((error && error.message) || error)}`;
      }
    }
    throw new Error(lastError || `Prompt injection appears incomplete. Expected ${payloadText.length} chars.`);
  }

  async function submitPrompt(page, editor) {
    await page.keyboard.press("Enter").catch(() => {});
    await page.waitForTimeout(1200);

    const residualText = await editor.innerText().catch(() => "");
    if (!residualText.trim()) {
      return;
    }

    const candidates = [
      page.getByTestId("send-button").first(),
      page.locator('button[aria-label*="Send"]').first(),
      page.locator('button[aria-label*="전송"]').first(),
      page.locator('button[aria-label*="Submit"]').first(),
      page.locator('button svg').locator("..").first(),
    ];

    for (const candidate of candidates) {
      try {
        await candidate.waitFor({ timeout: 1500 });
        await candidate.click();
        await page.waitForTimeout(1200);
        const afterText = await editor.innerText().catch(() => "");
        if (!afterText.trim()) {
          return;
        }
      } catch (_error) {
        continue;
      }
    }

    const nearestButton = await page.evaluate(() => {
      const editorNode = document.querySelector("#prompt-textarea");
      if (!(editorNode instanceof HTMLElement)) {
        return null;
      }
      const editorRect = editorNode.getBoundingClientRect();
      const buttons = Array.from(document.querySelectorAll("button")).filter((button) => {
        if (!(button instanceof HTMLButtonElement) || button.disabled) {
          return false;
        }
        const style = window.getComputedStyle(button);
        if (style.visibility === "hidden" || style.display === "none") {
          return false;
        }
        const rect = button.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      });
      let bestButton = null;
      let bestScore = Number.POSITIVE_INFINITY;
      for (const button of buttons) {
        const rect = button.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const targetX = editorRect.right;
        const targetY = editorRect.bottom;
        const distance = (centerX - targetX) ** 2 + (centerY - targetY) ** 2;
        if (distance < bestScore) {
          bestScore = distance;
          bestButton = button;
        }
      }
      if (!bestButton) {
        return null;
      }
      bestButton.click();
      return {
        aria: bestButton.getAttribute("aria-label") || "",
        text: (bestButton.innerText || "").trim(),
        testid: bestButton.getAttribute("data-testid") || "",
      };
    }).catch(() => null);
    if (nearestButton) {
      await page.waitForTimeout(1200);
      const afterNearestClickText = await editor.innerText().catch(() => "");
      if (!afterNearestClickText.trim()) {
        return;
      }
    }

    throw new Error("Prompt submit did not clear the editor after Enter and send-button fallbacks.");
  }

  try {
    const context = browser.contexts()[0];
    if (!context) {
      throw new Error("No browser context found.");
    }

    const pages = context.pages();
    const pageSummaries = pages.map((page, index) => ({
      index,
      url: page.url(),
      title: page.isClosed() ? "(closed)" : undefined,
    }));

    let page = null;
    let sourcePage = null;
    if (projectUrl) {
      sourcePage = pages.find((candidate) => (candidate.url() || "").startsWith(projectUrl));
    }
    if (!sourcePage) {
      sourcePage = pages.find((candidate) => {
        const url = candidate.url() || "";
        return url.startsWith("https://chatgpt.com/") && !url.includes("auth/login");
      });
    }
    if (!sourcePage) {
      sourcePage = pages[0] || null;
    }

    if (preferNewPage) {
      page = await context.newPage();
    } else {
      page = sourcePage || (await context.newPage());
    }

    await page.bringToFront();
    const targetUrl = projectUrl || (preferNewPage && sourcePage ? sourcePage.url() : "");
    if (targetUrl && ((preferNewPage && (page.url() || "") !== targetUrl) || (projectUrl && !(page.url() || "").startsWith(projectUrl)))) {
      await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 120000 }).catch(() => {});
    }

    await page.waitForTimeout(1000);
    await ensureModelSelection(page, modelLabel, modelStrategy);

    const url = page.url();
    const body = await page.locator("body").innerText().catch(() => "");
    const lower = `${url}\n${body}`.toLowerCase();

    if (lower.includes("verify you are human") || lower.includes("just a moment") || lower.includes("cloudflare")) {
      throw new Error(`Human verification is blocking the current page: ${url}`);
    }
    if (lower.includes("log in") || lower.includes("sign up for free")) {
      throw new Error(`Login is required for the current page: ${url}`);
    }

    if (prepareOnly) {
      console.log(
        JSON.stringify({
          ok: true,
          prepared: true,
          url: page.url(),
          pages: pageSummaries,
          modelLabel,


[truncated]

```


## Review Request

You are the secondary reviewer in a recursive Codex improvement loop.
Judge only the attached local code and its likely behavior.

Original user task:
호출기 핵심 소스 코드를 검토해서, 지금 시점에 남은 실제 개선점만 지적해.

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
- Ground every claim in the attached files only. Do not invent missing context.
- Keep every string concise and in Korean.
- must_fix, risks, and tests should each contain up to 5 items.
- follow_up_prompt should be empty when verdict is "pass".
- follow_up_prompt should be a compact instruction Codex can act on immediately when verdict is "revise".
- Do not wrap the JSON in markdown fences.

Extra review emphasis:
프롬프트 주입 정확성, ChatGPT 리뷰 회수 신뢰성, fanout 부분 성공 처리, 장시간 대기/타임아웃 경계, loop에서 review artifact를 소비하는 경계를 엄격히 봐라.

Extra review lens for this run:
- 이번 답변은 핵심 버그와 동작 회귀 가능성을 가장 엄격하게 본다.