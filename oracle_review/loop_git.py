from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .common import DEFAULT_OUTPUT_DIR

RunCommand = Callable[..., Any]


def detect_repo_root(start: Path, *, run_command_impl: RunCommand) -> Path:
    result = run_command_impl(["git", "rev-parse", "--show-toplevel"], cwd=start)
    if result.returncode != 0:
        raise SystemExit(result.stderr.strip() or "Failed to detect git repository.")
    return Path(str(result.stdout).strip()).resolve()


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


def has_repo_changes(
    repo_root: Path,
    *,
    session_dir: Path | None = None,
    run_command_impl: RunCommand,
) -> bool:
    result = run_command_impl(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed.")
    return any(
        is_reviewable_status_path(path, session_dir=session_dir)
        for _status, path in iter_status_entries(repo_root, result.stdout)
    )


def has_untracked_files(
    repo_root: Path,
    *,
    session_dir: Path | None = None,
    run_command_impl: RunCommand,
) -> bool:
    result = run_command_impl(["git", "ls-files", "--others", "--exclude-standard"], cwd=repo_root)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed.")
    for line in result.stdout.splitlines():
        text = line.strip()
        if text and is_reviewable_status_path(repo_root / text, session_dir=session_dir):
            return True
    return False
