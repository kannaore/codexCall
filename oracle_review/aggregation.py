from __future__ import annotations

from collections import Counter
import json
from typing import Sequence

from .common import REVIEW_ANGLE_PRESETS, ReviewCandidate, ensure_text_list, extract_json_object


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


def consensus_threshold(count: int) -> int:
    if count <= 1:
        return 1
    return (count // 2) + 1


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


def aggregate_structured_candidates(
    candidates: Sequence[ReviewCandidate],
    *,
    expected_count: int | None = None,
) -> tuple[str, dict[str, object]]:
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

    expected_total = expected_count or len(candidates)
    required_valid_count = consensus_threshold(expected_total)
    if len(parsed) < required_valid_count:
        raise ValueError(
            f"Only {len(parsed)} valid structured review responses were collected; at least {required_valid_count} are required."
        )

    revise = [(candidate, payload) for candidate, payload in parsed if str(payload.get("verdict", "")).strip().lower() == "revise"]
    passed = [(candidate, payload) for candidate, payload in parsed if str(payload.get("verdict", "")).strip().lower() == "pass"]
    verdict_threshold = consensus_threshold(len(parsed))
    if len(revise) >= verdict_threshold:
        verdict = "revise"
        consensus_source = revise
    elif len(passed) >= verdict_threshold:
        verdict = "pass"
        consensus_source = passed
    else:
        raise ValueError(
            f"Structured review verdicts did not reach consensus (pass={len(passed)}, revise={len(revise)}, valid={len(parsed)})."
        )

    anchor_candidate, anchor_payload = max(consensus_source, key=lambda item: score_structured_payload(item[1]))
    must_fix = rank_text_items([ensure_text_list(payload.get("must_fix")) for _candidate, payload in consensus_source])
    risks = rank_text_items([ensure_text_list(payload.get("risks")) for _candidate, payload in consensus_source])
    tests = rank_text_items([ensure_text_list(payload.get("tests")) for _candidate, payload in consensus_source])
    follow_up_prompt = ""
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
        "expected_candidate_count": expected_total,
        "required_valid_candidate_count": required_valid_count,
        "valid_candidate_count": len(parsed),
        "pass_count": len(passed),
        "revise_count": len(revise),
    }
    return json.dumps(aggregated, ensure_ascii=False, indent=2) + "\n", metadata


def score_plaintext_review(text: str) -> tuple[int, int]:
    body = text.strip()
    score = len(body)
    for keyword in ("핵심", "리스크", "테스트", "바로 고칠 것", "must_fix", "follow_up_prompt"):
        if keyword in body:
            score += 120
    score += min(len([line.strip() for line in body.splitlines() if line.strip()]), 12) * 25
    return score, len(body)


def aggregate_plaintext_candidates(
    candidates: Sequence[ReviewCandidate],
    *,
    expected_count: int | None = None,
) -> tuple[str, dict[str, object]]:
    expected_total = expected_count or len(candidates)
    required_valid_count = consensus_threshold(expected_total)
    if len(candidates) < required_valid_count:
        raise ValueError(f"Only {len(candidates)} plaintext review responses were collected; at least {required_valid_count} are required.")
    selected = max(candidates, key=lambda candidate: score_plaintext_review(candidate.review_text))
    metadata = {
        "mode": "best-text",
        "selected_candidate": selected.index,
        "selected_label": selected.label,
        "expected_candidate_count": expected_total,
        "required_valid_candidate_count": required_valid_count,
        "valid_candidate_count": len(candidates),
    }
    return selected.review_text, metadata


def aggregate_review_candidates(
    candidates: Sequence[ReviewCandidate],
    *,
    expected_count: int | None = None,
) -> tuple[str, dict[str, object]]:
    structured_count = 0
    for candidate in candidates:
        try:
            payload = extract_json_object(candidate.review_text)
        except ValueError:
            continue
        verdict = str(payload.get("verdict", "")).strip().lower()
        if verdict in {"pass", "revise"}:
            structured_count += 1
    if structured_count:
        return aggregate_structured_candidates(candidates, expected_count=expected_count)
    return aggregate_plaintext_candidates(candidates, expected_count=expected_count)
