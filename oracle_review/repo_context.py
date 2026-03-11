from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from .common import DEFAULT_OUTPUT_DIR, run_command, split_non_empty


def is_reviewable_relpath(rel_path: str) -> bool:
    path = Path(rel_path)
    if not rel_path or path.suffix == ".pyc":
        return False
    blocked_parts = {".git", "__pycache__", DEFAULT_OUTPUT_DIR}
    return not any(part in blocked_parts for part in path.parts)


def is_sensitive_snapshot_relpath(rel_path: str) -> bool:
    from .common import SENSITIVE_SNAPSHOT_NAMES, SENSITIVE_SNAPSHOT_SUFFIXES

    path = Path(rel_path)
    name = path.name.lower()
    if name in SENSITIVE_SNAPSHOT_NAMES:
        return True
    if name == ".env" or name.startswith(".env."):
        return True
    if path.suffix.lower() in SENSITIVE_SNAPSHOT_SUFFIXES:
        return True
    return False


def is_snapshot_includable_relpath(rel_path: str) -> bool:
    return is_reviewable_relpath(rel_path) and not is_sensitive_snapshot_relpath(rel_path)


def is_reviewable_path(path: Path) -> bool:
    return path.is_file() and "__pycache__" not in path.parts and DEFAULT_OUTPUT_DIR not in path.parts and path.suffix != ".pyc"


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


def dedupe_rel_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    selected: list[str] = []
    for rel_path in paths:
        normalized = Path(rel_path).as_posix().strip()
        if not normalized or normalized in seen or not is_reviewable_relpath(normalized):
            continue
        seen.add(normalized)
        selected.append(normalized)
    return selected


def dedupe_snapshot_rel_paths(paths: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    selected: list[str] = []
    for rel_path in paths:
        normalized = Path(rel_path).as_posix().strip()
        if not normalized or normalized in seen or not is_snapshot_includable_relpath(normalized):
            continue
        seen.add(normalized)
        selected.append(normalized)
    return selected


def detect_repo_root(start: Path) -> Path:
    return Path(run_command(["git", "rev-parse", "--show-toplevel"], start))


def detect_branch(repo_root: Path) -> str:
    return run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], repo_root)


def repo_relative_path(repo_root: Path, path: Path) -> str | None:
    try:
        return Path(path.resolve().relative_to(repo_root)).as_posix()
    except ValueError:
        return None


def gather_changed_git_paths(repo_root: Path, *, include_untracked: bool) -> list[str]:
    staged = split_non_empty(run_command(["git", "diff", "--name-only", "--cached", "--diff-filter=ACMRTUXD"], repo_root))
    unstaged = split_non_empty(run_command(["git", "diff", "--name-only", "--diff-filter=ACMRTUXD"], repo_root))
    rel_paths = [*staged, *unstaged]
    if include_untracked:
        rel_paths.extend(split_non_empty(run_command(["git", "ls-files", "--others", "--exclude-standard"], repo_root)))
    return dedupe_rel_paths(rel_paths)


def gather_changed_files(repo_root: Path, *, include_untracked: bool) -> list[Path]:
    return dedupe_paths(repo_root / rel_path for rel_path in gather_changed_git_paths(repo_root, include_untracked=include_untracked))


def collect_review_git_paths(
    repo_root: Path,
    *,
    selected_files: Sequence[Path],
    include_changed_files: bool,
    include_untracked: bool,
) -> list[str]:
    rel_paths: list[str] = []
    if include_changed_files:
        rel_paths.extend(gather_changed_git_paths(repo_root, include_untracked=include_untracked))
    for path in selected_files:
        rel_path = repo_relative_path(repo_root, path)
        if rel_path:
            rel_paths.append(rel_path)
    return dedupe_rel_paths(rel_paths)


def gather_repo_snapshot_paths(repo_root: Path, *, include_untracked: bool) -> list[str]:
    tracked = split_non_empty(run_command(["git", "ls-files"], repo_root))
    rel_paths = tracked
    if include_untracked:
        rel_paths = [*tracked, *split_non_empty(run_command(["git", "ls-files", "--others", "--exclude-standard"], repo_root))]
    return dedupe_snapshot_rel_paths(rel_paths)


def build_review_status_text(repo_root: Path, rel_paths: Sequence[str]) -> str:
    if not rel_paths:
        return ""
    return run_command(["git", "status", "--short", "--", *rel_paths], repo_root)


def build_review_diff_stat(repo_root: Path, rel_paths: Sequence[str]) -> str:
    if not rel_paths:
        return ""
    return run_command(["git", "diff", "--stat", "HEAD", "--", *rel_paths], repo_root)


def build_diff_payload(repo_root: Path, rel_paths: Sequence[str]) -> str:
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
    review_git_paths: Sequence[str],
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
    git_scope_block = "\n".join(f"- {path}" for path in review_git_paths) or "- (none)"
    return f"""# Codex Review Context

Repository: {repo_root.name}
Path: {repo_root}
Branch: {branch}

## Requested Review
{prompt_text.strip()}

## Selected Files
{files_block}

## Git Review Scope
{git_scope_block}

## Git Status
```text
{status_text or "(clean working tree)"}
```

## Diff Stat
```text
{diff_stat or "(no diff stat available)"}
```
"""
