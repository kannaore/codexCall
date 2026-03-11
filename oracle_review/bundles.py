from __future__ import annotations

from datetime import datetime
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Sequence

from .common import DEFAULT_OUTPUT_DIR, MAX_BUNDLE_CHARS, MAX_FILE_CHARS, SNAPSHOT_INLINE_CHAR_THRESHOLD
from .repo_context import gather_changed_git_paths, is_reviewable_path, repo_relative_path, is_sensitive_snapshot_relpath


def create_temp_context(content: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".oracle-context.md", delete=False)
    try:
        handle.write(content)
        handle.flush()
        return Path(handle.name)
    finally:
        handle.close()


def parse_review_markers(bundle_text: str) -> tuple[str, str]:
    begin_marker = ""
    end_marker = ""
    for line in bundle_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("BEGIN_CDX_REVIEW_") and not begin_marker:
            begin_marker = stripped
        elif stripped.startswith("END_CDX_REVIEW_") and not end_marker:
            end_marker = stripped
    if not begin_marker or not end_marker:
        raise ValueError("Prompt bundle did not contain review markers.")
    return begin_marker, end_marker


def parse_candidate_prompt_filename(path: Path) -> tuple[int, str]:
    stem = path.name.removesuffix(".prompt.md")
    if not stem.startswith("candidate-"):
        raise ValueError(f"Unsupported candidate prompt filename: {path.name}")
    parts = stem.split("-", 2)
    if len(parts) < 3:
        raise ValueError(f"Unsupported candidate prompt filename: {path.name}")
    return int(parts[1]), parts[2]


def default_output_path(repo_root: Path) -> Path:
    output_dir = repo_root / DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir / f"review-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"


def read_file_excerpt(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= MAX_FILE_CHARS:
        return text
    return text[:MAX_FILE_CHARS] + "\n\n[truncated]\n"


def estimate_inline_attachment_chars(paths: Sequence[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += min(path.stat().st_size, MAX_FILE_CHARS)
        except OSError:
            total += MAX_FILE_CHARS
    return total


def resolve_attachment_format(
    requested_format: str,
    *,
    delivery: str,
    inline_attachments: Sequence[Path],
) -> str:
    if requested_format != "auto":
        return requested_format
    if delivery != "cdp":
        return "text"
    if len(inline_attachments) > 3 or estimate_inline_attachment_chars(inline_attachments) > SNAPSHOT_INLINE_CHAR_THRESHOLD:
        return "repo-zip"
    return "text"


def snapshot_member_name(repo_root: Path, path: Path) -> str:
    rel_path = repo_relative_path(repo_root, path)
    if rel_path:
        return f"repo/{rel_path}"
    return f"external/{path.name}"


def create_repo_snapshot_archive(
    *,
    repo_root: Path,
    branch: str,
    prompt_text: str,
    context_text: str,
    selected_files: Sequence[Path],
    review_git_paths: Sequence[str],
    repo_snapshot_paths: Sequence[str],
    status_text: str,
    diff_stat: str,
    diff_payload: str,
) -> Path:
    handle = tempfile.NamedTemporaryFile("wb", suffix=".review-snapshot.zip", delete=False)
    try:
        handle.close()
        archive_path = Path(handle.name)
        deleted_paths = [rel_path for rel_path in review_git_paths if not (repo_root / rel_path).exists()]
        excluded_sensitive_paths = [
            rel_path
            for rel_path in gather_changed_git_paths(repo_root, include_untracked=True)
            if is_sensitive_snapshot_relpath(rel_path)
        ]
        manifest = {
            "repository": repo_root.name,
            "path": str(repo_root),
            "branch": branch,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "review_prompt": prompt_text.strip(),
            "review_git_paths": list(review_git_paths),
            "repo_snapshot_paths": list(repo_snapshot_paths),
            "deleted_paths": deleted_paths,
            "excluded_sensitive_paths": excluded_sensitive_paths,
            "status_text": status_text,
            "diff_stat": diff_stat,
        }
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "README.md",
                (
                    "# Codex Review Snapshot\n\n"
                    "이 압축 파일은 리뷰 시점의 전체 코드베이스 스냅샷과 git 컨텍스트를 담고 있습니다.\n\n"
                    "우선 `manifest.json`, `context/review-context.md`, `context/git-diff.md`를 보고,\n"
                    "필요한 코드 파일은 `repo/` 아래에서 확인하세요.\n"
                ),
            )
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            archive.writestr("context/review-context.md", context_text)
            archive.writestr("context/git-diff.md", diff_payload)
            for rel_path in repo_snapshot_paths:
                file_path = repo_root / rel_path
                if file_path.is_file() and is_reviewable_path(file_path):
                    archive.write(file_path, f"repo/{rel_path}")
            for path in selected_files:
                rel_path = repo_relative_path(repo_root, path)
                if rel_path or not path.is_file() or not is_reviewable_path(path):
                    continue
                archive.write(path, f"external/{path.name}")
        return archive_path
    except Exception:
        archive_path = Path(handle.name)
        archive_path.unlink(missing_ok=True)
        raise


def build_bundle_text(
    *,
    prompt_text: str,
    context_text: str,
    attachments: Sequence[Path],
    uploaded_paths: Sequence[Path],
    begin_marker: str,
    end_marker: str,
) -> str:
    parts = [
        "You are reviewing a local coding change from Codex.",
        "Return the final answer in Korean.",
        "Wrap the full answer exactly between these markers:",
        begin_marker,
        end_marker,
        "",
        context_text.strip(),
        "",
    ]
    if uploaded_paths:
        parts.append("## Uploaded Files")
        for attachment in uploaded_paths:
            parts.append(f"- {attachment.name}")
        parts.append("")
        parts.append("Use the uploaded files directly. The zip contains the full repository snapshot for this review.")
    if attachments:
        parts.append("")
        parts.append("## Attached Material")
        remaining = MAX_BUNDLE_CHARS
        for attachment in attachments:
            body = read_file_excerpt(attachment)
            header = f"\n### {attachment.name}\n"
            block = header + "```text\n" + body + "\n```\n"
            if len(block) > remaining:
                parts.append("\n[remaining attachments omitted due to bundle cap]\n")
                break
            parts.append(block)
            remaining -= len(block)
    parts.append("\n## Review Request\n")
    parts.append(prompt_text.strip())
    return "\n".join(parts)
