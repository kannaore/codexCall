You are reviewing a local coding change from Codex.
Return the final answer in Korean.
Wrap the full answer exactly between these markers:
BEGIN_CDX_REVIEW_20260311131721_03
END_CDX_REVIEW_20260311131721_03

# Codex Review Context

Repository: 호출기
Path: /home/mrcorp/Coding/Tools/호출기
Branch: main

## Requested Review
You are the secondary reviewer in a recursive Codex improvement loop.
Judge only the attached local code and its likely behavior.

Original user task:
호출기 코드베이스를 검토해서, 지금 시점에 실제로 개선 가치가 남아 있는 문제만 지적해.

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
- Ground every claim in the attached files or diff. Do not invent missing context.
- Keep every string concise and in Korean.
- must_fix, risks, and tests should each contain up to 5 items.
- follow_up_prompt should be empty when verdict is "pass".
- follow_up_prompt should be a compact instruction Codex can act on immediately when verdict is "revise".
- Do not wrap the JSON in markdown fences.

Extra review emphasis:
우선순위는 1) 실제 오동작 가능성 2) 워크플로우 신뢰성 3) 테스트 공백 4) 유지보수성이다.
특히 ChatGPT 프롬프트 주입 신뢰성, review artifact 생성/소비 연결, 장시간 5.4 Pro 응답 대기, fanout 부분 성공 처리, false positive 리뷰 결과를 엄격히 봐라.

## Selected Files
- codex-gpt54-review
- codex-gpt54-loop
- chatgpt-cdp-smoke.js
- tests/test_codex_gpt54_review.py
- tests/test_codex_gpt54_loop.py

## Git Status
```text
M chatgpt-cdp-smoke.js
 M codex-gpt54-review
 M tests/test_codex_gpt54_review.py
```

## Diff Stat
```text
chatgpt-cdp-smoke.js             | 62 ++++++++++++++++++++++++++++++++---
 codex-gpt54-review               | 42 ++++++++++++++++++++----
 tests/test_codex_gpt54_review.py | 70 ++++++++++++++++++++++++++++++++++++++++
 3 files changed, 163 insertions(+), 11 deletions(-)
```

## Attached Material

### tmppz1lex_0.oracle-context.md
```text
# Git Diff Review Payload

## Status
```text
M chatgpt-cdp-smoke.js
 M codex-gpt54-review
 M tests/test_codex_gpt54_review.py
```

## Staged Diff
```diff
(none)
```

## Unstaged Diff
```diff
diff --git a/chatgpt-cdp-smoke.js b/chatgpt-cdp-smoke.js
index f04a50a..eb6c6f9 100644
--- a/chatgpt-cdp-smoke.js
+++ b/chatgpt-cdp-smoke.js
@@ -137,8 +137,31 @@ async function main() {
     }).catch(() => {});
   }
 
-  async function injectPrompt(page, editor, payloadText) {
-    await clearEditor(page, editor);
+  function normalizePromptText(value) {
+    return String(value || "").replace(/\s+/g, "");
+  }
+
+  async function readEditorText(editor) {
+    const [innerText, textContent] = await Promise.all([
+      editor.innerText().catch(() => ""),
+      editor.evaluate((node) => node.textContent || "").catch(() => ""),
+    ]);
+    return { innerText, textContent };
+  }
+
+  function isPromptEquivalent(expected, actual) {
+    return normalizePromptText(expected) === normalizePromptText(actual);
+  }
+
+  async function injectPromptViaDom(editor, payloadText) {
+    await editor.evaluate((node, text) => {
+      node.textContent = text;
+      node.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
+      node.dispatchEvent(new Event("change", { bubbles: true }));
+    }, payloadText);
+  }
+
+  async function injectPromptViaInsertText(page, payloadText) {
     const chunks = [];
     const chunkSize = 4000;
     for (let index = 0; index < payloadText.length; index += chunkSize) {
@@ -148,10 +171,39 @@ async function main() {
       await page.keyboard.insertText(chunk);
       await page.waitForTimeout(20);
     }
-    const editorText = await editor.innerText().catch(() => "");
-    if (!editorText || editorText.length < Math.min(payloadText.length, 200)) {
-      throw new Error(`Prompt injection appears incomplete. Expected ${payloadText.length} chars, saw ${editorText.length}.`);
+  }
+
+  async function injectPromptViaClipboard(page, editor, payloadText) {
+    await page.evaluate(async (text) => {
+      await navigator.clipboard.writeText(text);
+    }, payloadText);
+    await editor.click();
+    await page.keyboard.press("Control+V");
+    await page.waitForTimeout(1000);
+  }
+
+  async function injectPrompt(page, editor, payloadText) {
+    await clearEditor(page, editor);
+    const strategies = [
+      ["dom-set", async () => injectPromptViaDom(editor, payloadText)],
+      ["clipboard", async () => injectPromptViaClipboard(page, editor, payloadText)],
+      ["insert-text", async () => injectPromptViaInsertText(page, payloadText)],
+    ];
+    let lastError = "";
+    for (const [label, action] of strategies) {
+      await clearEditor(page, editor);
+      try {
+        await action();
+        const { innerText, textContent } = await readEditorText(editor);
+        if (isPromptEquivalent(payloadText, textContent) || isPromptEquivalent(payloadText, innerText)) {
+          return;
+        }
+        lastError = `Prompt injection mismatch after ${label}. Expected ${payloadText.length} chars, saw innerText=${innerText.length}, textContent=${textContent.length}.`;
+      } catch (error) {
+        lastError = `Prompt injection failed via ${label}: ${String((error && error.message) || error)}`;
+      }
     }
+    throw new Error(lastError || `Prompt injection appears incomplete. Expected ${payloadText.length} chars.`);
   }
 
   async function submitPrompt(page, editor) {
diff --git a/codex-gpt54-review b/codex-gpt54-review
index e874059..6646d6a 100755
--- a/codex-gpt54-review
+++ b/codex-gpt54-review
@@ -304,15 +304,45 @@ def gather_changed_files(repo_root: Path, *, include_untracked: bool) -> list[Pa
     return dedupe_paths(selected)
 
 
+def reviewable_git_paths(repo_root: Path) -> list[str]:
+    rel_paths: list[str] = []
+    for path in gather_changed_files(repo_root, include_untracked=True):
+        try:
+            rel_paths.append(str(path.relative_to(repo_root)))
+        except ValueError:
+            continue
+    return rel_paths
+
+
+def build_review_status_text(repo_root: Path) -> str:
+    rel_paths = reviewable_git_paths(repo_root)
+    if not rel_paths:
+        return ""
+    return run_command(["git", "status", "--short", "--", *rel_paths], repo_root)
+
+
+def build_review_diff_stat(repo_root: Path) -> str:
+    rel_paths = reviewable_git_paths(repo_root)
+    if not rel_paths:
+        return ""
+    return run_command(["git", "diff", "--stat", "HEAD", "--", *rel_paths], repo_root)
+
+
 def build_diff_payload(repo_root: Path) -> str:
-    status_text = run_command(["git", "status", "--short"], repo_root)
-    staged_diff = run_command(["git", "diff", "--cached", "--find-renames", "--binary", "HEAD"], repo_root)
-    unstaged_diff = run_command(["git", "diff", "--find-renames", "--binary"], repo_root)
+    rel_paths = reviewable_git_paths(repo_root)
+    if rel_paths:
+        status_text = run_command(["git", "status", "--short", "--", *rel_paths], repo_root)
+        staged_diff = run_command(["git", "diff", "--cached", "--find-renames", "HEAD", "--", *rel_paths], repo_root)
+        unstaged_diff = run_command(["git", "diff", "--find-renames", "--", *rel_paths], repo_root)
+    else:
+        status_text = ""
+        staged_diff = ""
+        unstaged_diff = ""
     return (
         "# Git Diff Review Payload\n\n"
         "## Status\n"
         "```text\n"
-        f"{status_text or '(clean working tree)'}\n"
+        f"{status_text or '(no reviewable changed files)'}\n"
         "```\n\n"
         "## Staged Diff\n"
         "```diff\n"
@@ -989,8 +1019,8 @@ def main(argv: Sequence[str] | None = None) -> int:
         print("No attachments selected. Modify tracked files first or pass --file <path>.", file=sys.stderr)
         return 1
 
-    status_text = run_command(["git", "status", "--short"], repo_root)
-    diff_stat = run_command(["git", "diff", "--stat", "HEAD"], repo_root)
+    status_text = build_review_status_text(repo_root)
+    diff_stat = build_review_diff_stat(repo_root)
     context_file = create_temp_context(
         build_context_markdown(
             repo_root=repo_root,
diff --git a/tests/test_codex_gpt54_review.py b/tests/test_codex_gpt54_review.py
index 501800d..bd27763 100644
--- a/tests/test_codex_gpt54_review.py
+++ b/tests/test_codex_gpt54_review.py
@@ -48,6 +48,76 @@ class ReviewVariantTests(unittest.TestCase):
         )
 
 
+class DiffPayloadTests(unittest.TestCase):
+    def test_build_diff_payload_limits_git_commands_to_reviewable_files(self):
+        repo_root = Path("/tmp/repo")
+        seen_commands: list[list[str]] = []
+
+        def fake_run_command(args, cwd):
+            seen_commands.append(list(args))
+            command_key = tuple(args[:3])
+            if command_key == ("git", "status", "--short"):
+                return " M codex-gpt54-review\n M tests/test_codex_gpt54_review.py"
+            return "(none)"
+
+        with patch.object(
+            review,
+            "gather_changed_files",
+            return_value=[
+                repo_root / "codex-gpt54-review",
+                repo_root / "tests" / "test_codex_gpt54_review.py",
+            ],
+        ), patch.object(review, "run_command", side_effect=fake_run_command):
+            payload = review.build_diff_payload(repo_root)
+
+        self.assertIn("codex-gpt54-review", payload)
+        self.assertIn("tests/test_codex_gpt54_review.py", payload)
+        self.assertEqual(
+            seen_commands,
+            [
+                ["git", "status", "--short", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
+                ["git", "diff", "--cached", "--find-renames", "HEAD", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
+                ["git", "diff", "--find-renames", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
+            ],
+        )
+
+    def test_build_diff_payload_reports_when_no_reviewable_files_changed(self):
+        with patch.object(review, "gather_changed_files", return_value=[]), patch.object(review, "run_command") as run_command:
+            payload = review.build_diff_payload(Path("/tmp/repo"))
+
+        self.assertIn("(no reviewable changed files)", payload)
+        run_command.assert_not_called()
+
+    def test_build_review_status_and_diff_stat_use_reviewable_paths_only(self):
+        repo_root = Path("/tmp/repo")
+        seen_commands: list[list[str]] = []
+
+        def fake_run_command(args, cwd):
+            seen_commands.append(list(args))
+            return "ok"
+
+        with patch.object(
+            review,
+            "gather_changed_files",
+            return_value=[
+                repo_root / "codex-gpt54-review",
+                repo_root / "tests" / "test_codex_gpt54_review.py",
+            ],
+        ), patch.object(review, "run_command", side_effect=fake_run_command):
+            status_text = review.build_review_status_text(repo_root)
+            diff_stat = review.build_review_diff_stat(repo_root)
+
+        self.assertEqual(status_text, "ok")
+        self.assertEqual(diff_stat, "ok")
+        self.assertEqual(
+            seen_commands,
+            [
+                ["git", "status", "--short", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
+                ["git", "diff", "--stat", "HEAD", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
+            ],
+        )
+
+
 class ReviewAggregationTests(unittest.TestCase):
     def make_candidate(self, index: int, label: str, payload: dict[str, object]) -> object:
         return review.ReviewCandidate(
```

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


class DiffPayloadTests(unittest.TestCase):
    def test_build_diff_payload_limits_git_commands_to_reviewable_files(self):
        repo_root = Path("/tmp/repo")
        seen_commands: list[list[str]] = []

        def fake_run_command(args, cwd):
            seen_commands.append(list(args))
            command_key = tuple(args[:3])
            if command_key == ("git", "status", "--short"):
                return " M codex-gpt54-review\n M tests/test_codex_gpt54_review.py"
            return "(none)"

        with patch.object(
            review,
            "gather_changed_files",
            return_value=[
                repo_root / "codex-gpt54-review",
                repo_root / "tests" / "test_codex_gpt54_review.py",
            ],
        ), patch.object(review, "run_command", side_effect=fake_run_command):
            payload = review.build_diff_payload(repo_root)

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
        with patch.object(review, "gather_changed_files", return_value=[]), patch.object(review, "run_command") as run_command:
            payload = review.build_diff_payload(Path("/tmp/repo"))

        self.assertIn("(no reviewable changed files)", payload)
        run_command.assert_not_called()

    def test_build_review_status_and_diff_stat_use_reviewable_paths_only(self):
        repo_root = Path("/tmp/repo")
        seen_commands: list[list[str]] = []

        def fake_run_command(args, cwd):
            seen_commands.append(list(args))
            return "ok"

        with patch.object(
            review,
            "gather_changed_files",
            return_value=[
                repo_root / "codex-gpt54-review",
                repo_root / "tests" / "test_codex_gpt54_review.py",
            ],
        ), patch.object(review, "run_command", side_effect=fake_run_command):
            status_text = review.build_review_status_text(repo_root)
            diff_stat = review.build_review_diff_stat(repo_root)

        self.assertEqual(status_text, "ok")
        self.assertEqual(diff_stat, "ok")
        self.assertEqual(
            seen_commands,
            [
                ["git", "status", "--short", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
                ["git", "diff", "--stat", "HEAD", "--", "codex-gpt54-review", "tests/test_codex_gpt54_review.py"],
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


def load_review_module():
    script_path = Path(__file__).resolve().parents[1] / "codex-gpt54-review"
    loader = SourceFileLoader("codex_gpt54_review_for_loop_tests", str(script_path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


loop = load_loop_module()
review_runner = load_review_module()


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

    def test_follow_up_prompt_reads_selected_paths_from_review_artifact_manifest(self):
        with tempfile.TemporaryDirectory() as tempdir:
            base = Path(tempdir)
            review_path = base / "round-01.review.json"
            candidate_dir = base / "round-01.review.json.candidates"
            candidate_dir.mkdir(parents=True, exist_ok=True)
            selected_prompt = candidate_dir / "candidate-02-02-edge-cases.prompt.md"
            selected_prompt.write_text("prompt-2", encoding="utf-8")

            review_payload = {
                "verdict": "revise",
                "summary": "정리 경로 점검 필요",
                "must_fix": ["cleanup 회귀 테스트 추가"],
                "risks": [],
                "tests": ["manifest 기반 follow-up 테스트"],
                "follow_up_prompt": "manifest 경로를 따라 후속 프롬프트를 구성해라",
            }
            review_text = json.dumps(review_payload, ensure_ascii=False)
            review_path.write_text(review_text, encoding="utf-8")

            candidate = review_runner.ReviewCandidate(
                index=2,
                label="02-edge-cases",
                prompt_text="prompt-2",
                review_text=review_text,
                output_path=Path("/tmp/windows-output-02.md"),
                returncode=0,
                stdout_text="",
                stderr_text="",
                metadata={},
            )
            review_runner.write_candidate_artifacts(
                candidate_dir,
                [candidate],
                {
                    "mode": "structured-consensus",
                    "selected_candidate": 2,
                    "selected_label": "02-edge-cases",
                    "valid_candidate_count": 5,
                    "revise_count": 4,
                },
            )

            candidate_manifest = loop.load_review_candidate_manifest(review_path)
            prompt = loop.build_follow_up_prompt(loop.parse_review_decision(review_text), candidate_manifest)

            self.assertIsNotNone(candidate_manifest)
            assert candidate_manifest is not None
            self.assertEqual(candidate_manifest["aggregate"]["selected_candidate"], 2)
            self.assertTrue(candidate_manifest["aggregate"]["selected_review_path"].endswith("candidate-02-02-edge-cases.txt"))
            self.assertTrue(candidate_manifest["aggregate"]["selected_prompt_path"].endswith("candidate-02-02-edge-cases.prompt.md"))
            self.assertIn("선택 후보 02 [02-edge-cases]", prompt)
            self.assertIn("선택된 저장 리뷰:", prompt)
            self.assertIn("선택 후보 프롬프트:", prompt)

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


[truncated]

```


## Review Request

You are the secondary reviewer in a recursive Codex improvement loop.
Judge only the attached local code and its likely behavior.

Original user task:
호출기 코드베이스를 검토해서, 지금 시점에 실제로 개선 가치가 남아 있는 문제만 지적해.

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
- Ground every claim in the attached files or diff. Do not invent missing context.
- Keep every string concise and in Korean.
- must_fix, risks, and tests should each contain up to 5 items.
- follow_up_prompt should be empty when verdict is "pass".
- follow_up_prompt should be a compact instruction Codex can act on immediately when verdict is "revise".
- Do not wrap the JSON in markdown fences.

Extra review emphasis:
우선순위는 1) 실제 오동작 가능성 2) 워크플로우 신뢰성 3) 테스트 공백 4) 유지보수성이다.
특히 ChatGPT 프롬프트 주입 신뢰성, review artifact 생성/소비 연결, 장시간 5.4 Pro 응답 대기, fanout 부분 성공 처리, false positive 리뷰 결과를 엄격히 봐라.

Extra review lens for this run:
- 이번 답변은 빠진 테스트, 재현성, 회귀 방지 측면을 우선 검토한다.