from __future__ import annotations

import argparse
from datetime import datetime
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .common import DEFAULT_DELIVERY, DEFAULT_FANOUT_COUNT, DEFAULT_FANOUT_STRATEGY, DEFAULT_MODEL, DEFAULT_MODEL_STRATEGY, DEFAULT_OUTPUT_DIR, DEFAULT_TIMEOUT_MS, repo_script_path
from .loop_git import detect_repo_root, has_repo_changes, has_untracked_files
from .loop_review import ReviewDecision, build_follow_up_prompt, build_review_prompt, effective_review_timeout_ms, load_review_candidate_manifest, parse_review_decision, review_candidate_manifest_path

DEFAULT_MAX_ROUNDS = 3
DEFAULT_REVIEW_MODEL = DEFAULT_MODEL
DEFAULT_REVIEW_MODEL_STRATEGY = DEFAULT_MODEL_STRATEGY
DEFAULT_REVIEW_DELIVERY = DEFAULT_DELIVERY
DEFAULT_REVIEW_MODE = "diff"
DEFAULT_REVIEW_TIMEOUT_MS = DEFAULT_TIMEOUT_MS
DEFAULT_REVIEW_FANOUT_COUNT = DEFAULT_FANOUT_COUNT
DEFAULT_REVIEW_FANOUT_STRATEGY = DEFAULT_FANOUT_STRATEGY


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


def read_task(task_arg: str | None) -> str:
    if task_arg == "-":
        return sys.stdin.read().strip()
    if task_arg:
        return task_arg.strip()
    return ""


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


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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
        command.append("-")
    return command


def run_codex_round(
    *,
    repo_root: Path,
    round_index: int,
    thread_id: str | None,
    prompt: str,
    session_dir: Path,
    args: argparse.Namespace,
    run_command_impl: Callable[..., Any] = run_command,
    write_text_impl: Callable[[Path, str], None] = write_text,
    build_codex_command_impl: Callable[..., list[str]] = build_codex_command,
    parse_thread_id_impl: Callable[[str], str] = parse_thread_id,
) -> str:
    message_path = session_dir / f"round-{round_index:02d}.codex.md"
    stdout_path = session_dir / f"round-{round_index:02d}.codex.jsonl"
    stderr_path = session_dir / f"round-{round_index:02d}.codex.stderr.log"
    command = build_codex_command_impl(
        repo_root=repo_root,
        thread_id=thread_id,
        message_path=message_path,
        args=args,
    )
    result = run_command_impl(command, cwd=repo_root, input_text=prompt)
    write_text_impl(stdout_path, result.stdout)
    write_text_impl(stderr_path, result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"Codex round {round_index} failed. See {stdout_path} and {stderr_path}."
        )
    next_thread_id = parse_thread_id_impl(result.stdout)
    print(f"[round {round_index}] codex complete. thread={next_thread_id}")
    return next_thread_id


def review_command_path() -> Path:
    return repo_script_path("codex-gpt54-review")


def run_review_round(
    *,
    repo_root: Path,
    round_index: int,
    task: str,
    session_dir: Path,
    args: argparse.Namespace,
    has_untracked_files_impl: Callable[..., bool] = has_untracked_files,
    run_command_impl: Callable[..., Any] = run_command,
    write_text_impl: Callable[[Path, str], None] = write_text,
    build_review_prompt_impl: Callable[[str, str], str] = build_review_prompt,
    effective_review_timeout_ms_impl: Callable[[str, int], int] = effective_review_timeout_ms,
    review_command_path_impl: Callable[[], Path] = review_command_path,
    parse_review_decision_impl: Callable[[str], ReviewDecision] = parse_review_decision,
    print_review_summary_impl: Callable[[int, ReviewDecision, Path], None] = print_review_summary,
) -> tuple[ReviewDecision, Path]:
    review_path = session_dir / f"round-{round_index:02d}.review.json"
    stdout_path = session_dir / f"round-{round_index:02d}.review.stdout.log"
    stderr_path = session_dir / f"round-{round_index:02d}.review.stderr.log"
    review_mode = args.review_mode
    include_untracked = args.include_untracked
    if review_mode == "diff" and has_untracked_files_impl(
        repo_root,
        session_dir=session_dir,
    ):
        review_mode = "hybrid"
        include_untracked = True
        print(f"[round {round_index}] untracked files detected; escalating review mode to hybrid with untracked files.")
    review_timeout_ms = effective_review_timeout_ms_impl(args.review_model, args.review_timeout_ms)
    command = [
        str(review_command_path_impl()),
        "--repo",
        str(repo_root),
        "--prompt",
        build_review_prompt_impl(task, args.review_note),
        "--write-output",
        str(review_path),
        "--delivery",
        args.review_delivery,
        "--mode",
        review_mode,
        "--model",
        args.review_model,
        "--model-strategy",
        args.review_model_strategy,
        "--timeout-ms",
        str(review_timeout_ms),
        "--fanout-count",
        str(args.review_fanout_count),
        "--fanout-strategy",
        args.review_fanout_strategy,
    ]
    if args.cdp_debug_url:
        command.extend(["--cdp-debug-url", args.cdp_debug_url])
    if args.no_project_url:
        command.append("--no-project-url")
    elif args.project_url:
        command.extend(["--project-url", args.project_url])
    if include_untracked:
        command.append("--include-untracked")
    for path in args.review_files:
        command.extend(["--file", path])

    result = run_command_impl(command, cwd=repo_root)
    write_text_impl(stdout_path, result.stdout)
    write_text_impl(stderr_path, result.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"Review round {round_index} failed. See {stdout_path} and {stderr_path}."
        )
    review_text = review_path.read_text(encoding="utf-8", errors="replace")
    review = parse_review_decision_impl(review_text)
    print_review_summary_impl(round_index, review, review_path)
    return review, review_path


def default_session_dir(repo_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return repo_root / DEFAULT_OUTPUT_DIR / f"loop-{stamp}"


def write_manifest(path: Path, payload: dict[str, Any]) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def run_loop(
    args: argparse.Namespace,
    *,
    read_task_impl: Callable[[str | None], str] = read_task,
    detect_repo_root_impl: Callable[[Path], Path] = lambda start: detect_repo_root(start, run_command_impl=run_command),
    default_session_dir_impl: Callable[[Path], Path] = default_session_dir,
    write_manifest_impl: Callable[[Path, dict[str, Any]], None] = write_manifest,
    run_codex_round_impl: Callable[..., str] = run_codex_round,
    has_repo_changes_impl: Callable[..., bool] = lambda repo_root, session_dir=None: has_repo_changes(repo_root, session_dir=session_dir, run_command_impl=run_command),
    run_review_round_impl: Callable[..., tuple[ReviewDecision, Path]] = run_review_round,
    load_review_candidate_manifest_impl: Callable[[Path], dict[str, Any] | None] = load_review_candidate_manifest,
    review_candidate_manifest_path_impl: Callable[[Path], Path] = review_candidate_manifest_path,
    build_follow_up_prompt_impl: Callable[[ReviewDecision, dict[str, Any] | None], str] = build_follow_up_prompt,
    confirm_manual_continue_impl: Callable[[], bool] = confirm_manual_continue,
    write_text_impl: Callable[[Path, str], None] = write_text,
) -> int:
    if args.max_rounds < 1:
        print("--max-rounds must be at least 1.", file=sys.stderr)
        return 2
    if args.review_fanout_count < 1:
        print("--review-fanout-count must be at least 1.", file=sys.stderr)
        return 2
    if args.codex_full_auto and args.codex_bypass_approvals:
        print("Choose either --codex-full-auto or --codex-bypass-approvals, not both.", file=sys.stderr)
        return 2
    if args.codex_session_id and args.codex_resume_last:
        print("Choose either --codex-session-id or --codex-resume-last, not both.", file=sys.stderr)
        return 2

    task = read_task_impl(args.task)
    if not task:
        print("An initial task is required. Pass it as an argument or via stdin with '-'.", file=sys.stderr)
        return 2

    repo_root = detect_repo_root_impl(Path(args.repo).resolve())
    session_dir = Path(args.session_dir).resolve() if args.session_dir else default_session_dir_impl(repo_root)
    session_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = session_dir / "manifest.json"

    manifest: dict[str, Any] = {
        "repo_root": str(repo_root),
        "task": task,
        "feedback_mode": args.feedback_mode,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "status": "running",
        "thread_id": None,
        "initial_session_id": args.codex_session_id,
        "resume_last": args.codex_resume_last,
        "rounds": [],
    }
    write_manifest_impl(manifest_path, manifest)

    thread_id: str | None = None
    next_prompt = task

    try:
        for round_index in range(1, args.max_rounds + 1):
            print(f"[round {round_index}/{args.max_rounds}] running Codex...")
            thread_id = run_codex_round_impl(
                repo_root=repo_root,
                round_index=round_index,
                thread_id=thread_id,
                prompt=next_prompt,
                session_dir=session_dir,
                args=args,
            )
            manifest["thread_id"] = thread_id

            round_record: dict[str, Any] = {
                "round": round_index,
                "codex_message": str(session_dir / f"round-{round_index:02d}.codex.md"),
                "codex_jsonl": str(session_dir / f"round-{round_index:02d}.codex.jsonl"),
                "codex_stderr": str(session_dir / f"round-{round_index:02d}.codex.stderr.log"),
            }
            manifest["rounds"].append(round_record)
            write_manifest_impl(manifest_path, manifest)

            if not has_repo_changes_impl(repo_root, session_dir=session_dir):
                round_record["status"] = "no_changes"
                manifest["status"] = "stopped-no-changes"
                print(f"[round {round_index}] no git changes detected after Codex. Stopping before review.")
                break

            print(f"[round {round_index}/{args.max_rounds}] running ChatGPT review...")
            review, review_path = run_review_round_impl(
                repo_root=repo_root,
                round_index=round_index,
                task=task,
                session_dir=session_dir,
                args=args,
            )
            candidate_manifest = load_review_candidate_manifest_impl(review_path)
            aggregate = candidate_manifest.get("aggregate") if isinstance(candidate_manifest, dict) else {}
            candidate_manifest_path = review_candidate_manifest_path_impl(review_path)
            round_record.update(
                {
                    "status": review.verdict,
                    "review_path": str(review_path),
                    "review_stdout": str(session_dir / f"round-{round_index:02d}.review.stdout.log"),
                    "review_stderr": str(session_dir / f"round-{round_index:02d}.review.stderr.log"),
                    "review_summary": review.summary,
                    "must_fix": review.must_fix,
                    "risks": review.risks,
                    "tests": review.tests,
                    "review_candidate_manifest": str(candidate_manifest_path) if candidate_manifest_path.exists() else None,
                    "review_selected_candidate": aggregate.get("selected_candidate") if isinstance(aggregate, dict) else None,
                    "review_selected_label": aggregate.get("selected_label") if isinstance(aggregate, dict) else None,
                    "review_selected_review_path": aggregate.get("selected_review_path") if isinstance(aggregate, dict) else None,
                }
            )
            write_manifest_impl(manifest_path, manifest)

            if review.verdict == "pass":
                manifest["status"] = "passed"
                print(f"[round {round_index}] reviewer passed the changes.")
                break

            if round_index >= args.max_rounds:
                manifest["status"] = "max-rounds"
                print(f"[round {round_index}] max rounds reached with remaining review items.")
                break

            if args.feedback_mode == "manual" and not confirm_manual_continue_impl():
                manifest["status"] = "manual-stop"
                print(f"[round {round_index}] stopped by user before sending follow-up to Codex.")
                break

            next_prompt = build_follow_up_prompt_impl(review, candidate_manifest)
            follow_up_path = session_dir / f"round-{round_index:02d}.followup.md"
            write_text_impl(follow_up_path, next_prompt)
            round_record["follow_up_prompt_path"] = str(follow_up_path)
            write_manifest_impl(manifest_path, manifest)
        else:
            manifest["status"] = "max-rounds"
    except Exception as exc:  # noqa: BLE001
        manifest["status"] = "failed"
        manifest["error"] = str(exc)
        write_manifest_impl(manifest_path, manifest)
        print(str(exc), file=sys.stderr)
        return 1

    manifest["finished_at"] = datetime.now().isoformat(timespec="seconds")
    write_manifest_impl(manifest_path, manifest)
    print(f"Session dir: {session_dir}")
    print(f"Manifest: {manifest_path}")
    if manifest["thread_id"]:
        print(f"Codex thread: {manifest['thread_id']}")

    if manifest["status"] == "passed":
        return 0
    if manifest["status"] in {"manual-stop", "stopped-no-changes"}:
        return 0
    if manifest["status"] == "max-rounds":
        return 3
    return 1
