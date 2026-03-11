from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .common import effective_timeout_ms, ensure_text_list, extract_json_object


@dataclass
class ReviewDecision:
    verdict: str
    summary: str
    must_fix: list[str]
    risks: list[str]
    tests: list[str]
    follow_up_prompt: str
    raw: dict[str, Any]


def effective_review_timeout_ms(model_label: str, requested_timeout_ms: int) -> int:
    return effective_timeout_ms(model_label, requested_timeout_ms)


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


def build_follow_up_prompt(
    review: ReviewDecision,
    candidate_manifest: dict[str, Any] | None = None,
) -> str:
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
            selected_number = int(selected_candidate)
            if selected_label:
                summary_bits.append(f"선택 후보 {selected_number:02d} [{selected_label}]")
            else:
                summary_bits.append(f"선택 후보 {selected_number:02d}")
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
