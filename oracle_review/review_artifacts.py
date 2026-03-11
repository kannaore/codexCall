from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Callable, Sequence

from .common import ReviewCandidate


def candidate_output_dir(write_output: Path) -> Path:
    return write_output.parent / f"{write_output.name}.candidates"


def reset_review_artifacts(
    write_output: Path,
    prompt_artifact: Path,
    candidate_dir: Path,
    *,
    safe_unlink_impl: Callable[[Path], None],
) -> None:
    for path in (write_output, prompt_artifact):
        safe_unlink_impl(path)
    shutil.rmtree(candidate_dir, ignore_errors=True)


def write_candidate_artifacts(
    candidate_dir: Path,
    candidates: Sequence[ReviewCandidate],
    aggregate_meta: dict[str, object],
) -> None:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {
        "aggregate": aggregate_meta,
        "candidates": [],
    }
    selected_entry: dict[str, object] | None = None
    for candidate in candidates:
        review_path = candidate_dir / f"candidate-{candidate.index:02d}-{candidate.label}.txt"
        stdout_path = candidate_dir / f"candidate-{candidate.index:02d}-{candidate.label}.stdout.log"
        stderr_path = candidate_dir / f"candidate-{candidate.index:02d}-{candidate.label}.stderr.log"
        prompt_path = candidate_dir / f"candidate-{candidate.index:02d}-{candidate.label}.prompt.md"
        review_path.write_text(candidate.review_text, encoding="utf-8")
        stdout_path.write_text(candidate.stdout_text, encoding="utf-8")
        stderr_path.write_text(candidate.stderr_text, encoding="utf-8")
        entry = {
            "index": candidate.index,
            "label": candidate.label,
            "returncode": candidate.returncode,
            "prompt_path": str(prompt_path),
            "review_path": str(review_path),
            "stdout_path": str(stdout_path),
            "stderr_path": str(stderr_path),
            "metadata": candidate.metadata,
        }
        manifest["candidates"].append(entry)
        if (
            int(aggregate_meta.get("selected_candidate", -1)) == candidate.index
            and str(aggregate_meta.get("selected_label", "")) == candidate.label
        ):
            selected_entry = entry
    if selected_entry is not None:
        manifest["aggregate"] = {
            **aggregate_meta,
            "selected_prompt_path": selected_entry["prompt_path"],
            "selected_review_path": selected_entry["review_path"],
            "selected_stdout_path": selected_entry["stdout_path"],
            "selected_stderr_path": selected_entry["stderr_path"],
        }
    (candidate_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def finalize_candidate_results(
    *,
    candidate_dir: Path,
    write_output: Path,
    candidate_results: Sequence[ReviewCandidate],
    expected_count: int,
    aggregate_review_candidates_impl: Callable[..., tuple[str, dict[str, object]]],
    write_candidate_artifacts_impl: Callable[[Path, Sequence[ReviewCandidate], dict[str, object]], None],
) -> tuple[int, dict[str, object]]:
    successful_candidates = [candidate for candidate in candidate_results if candidate.returncode == 0 and candidate.review_text.strip()]
    aggregate_meta: dict[str, object] = {}
    completed_code = 0
    if not successful_candidates:
        completed_code = 1
    else:
        try:
            aggregated_text, aggregate_meta = aggregate_review_candidates_impl(
                successful_candidates,
                expected_count=expected_count,
            )
        except ValueError as error:
            aggregate_meta = {
                "mode": "aggregation-error",
                "error": str(error),
                "expected_candidate_count": expected_count,
                "valid_candidate_count": len(successful_candidates),
            }
            print(str(error), file=sys.stderr)
            completed_code = 1
        else:
            write_output.parent.mkdir(parents=True, exist_ok=True)
            write_output.write_text(aggregated_text, encoding="utf-8")
            completed_code = 0
    write_candidate_artifacts_impl(candidate_dir, candidate_results, aggregate_meta)
    for candidate in candidate_results:
        status = "ok" if candidate.returncode == 0 and candidate.review_text.strip() else f"failed({candidate.returncode})"
        print(f"[candidate {candidate.index:02d}] {candidate.label}: {status}")
        if candidate.stderr_text.strip():
            print(candidate.stderr_text.strip(), file=sys.stderr)
    if aggregate_meta:
        print(
            f"Selected review: candidate {int(aggregate_meta.get('selected_candidate', 0)):02d} "
            f"[{aggregate_meta.get('selected_label', '')}] via {aggregate_meta.get('mode', '')}"
        )
    return completed_code, aggregate_meta


def cleanup_paths(
    paths: Sequence[Path],
    *,
    safe_unlink_impl: Callable[[Path], None],
) -> None:
    for path in paths:
        safe_unlink_impl(path)
