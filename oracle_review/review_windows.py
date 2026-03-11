from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Sequence

from .bundles import parse_candidate_prompt_filename, parse_review_markers
from .common import ReviewCandidate, WINDOWS_NODE, WINDOWS_TEMP_DIR, repo_script_path, run_command

POWERSHELL_PATH = "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"


def write_windows_temp_file(name: str, content: str) -> Path:
    WINDOWS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    path = WINDOWS_TEMP_DIR / name
    path.write_text(content, encoding="utf-8")
    return path


def windows_temp_path(name: str) -> Path:
    WINDOWS_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return WINDOWS_TEMP_DIR / name


def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
        return
    except FileNotFoundError:
        return
    except TypeError:
        pass
    except OSError:
        return

    try:
        if path.exists():
            path.unlink()
    except (FileNotFoundError, OSError):
        return


def terminate_process(process: subprocess.Popen[bytes], *, timeout: float = 5) -> None:
    if process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=timeout)
        return
    except subprocess.TimeoutExpired:
        pass
    except OSError:
        return

    try:
        process.kill()
    except OSError:
        return
    try:
        process.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, OSError):
        return


def to_windows_path(path: Path) -> str:
    if os.environ.get("WSL_DISTRO_NAME"):
        return run_command(["wslpath", "-m", str(path)], Path.cwd())
    return str(path)


def decode_windows_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "cp949", "utf-8-sig"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _json_tail(stdout_text: str) -> dict[str, object]:
    if not stdout_text.strip():
        return {}
    try:
        loaded = json.loads(stdout_text.strip().splitlines()[-1])
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _read_output_text(output_path: Path) -> str:
    if output_path.exists() and output_path.stat().st_size > 0:
        return output_path.read_text(encoding="utf-8", errors="replace")
    return ""


def _cdp_driver_source() -> str:
    return repo_script_path("chatgpt-cdp-smoke.js").read_text(encoding="utf-8")


def run_windows_powershell(script_text: str, *, script_name: str) -> subprocess.CompletedProcess[bytes]:
    ps_script = write_windows_temp_file(script_name, script_text)
    try:
        return subprocess.run(
            [
                POWERSHELL_PATH,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                to_windows_path(ps_script),
            ],
            check=False,
            capture_output=True,
        )
    finally:
        safe_unlink(ps_script)


def run_windows_chatgpt(
    *,
    payload_path: Path,
    output_path: Path,
    project_url: str,
    model_label: str,
    model_strategy: str,
    timeout_ms: int,
    begin_marker: str,
    end_marker: str,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [
            POWERSHELL_PATH,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(repo_script_path("chatgpt-windows-run.ps1")),
            "-PayloadPath",
            to_windows_path(payload_path),
            "-OutputPath",
            to_windows_path(output_path),
            "-ProjectUrl",
            project_url,
            "-ModelLabel",
            model_label,
            "-ModelStrategy",
            model_strategy,
            "-TimeoutMs",
            str(timeout_ms),
            "-BeginMarker",
            begin_marker,
            "-EndMarker",
            end_marker,
        ],
        check=False,
        capture_output=True,
    )


def detect_windows_cdp_debug_url() -> str:
    completed = run_windows_powershell(
        script_name="codex-chatgpt-detect-cdp.ps1",
        script_text=r"""
$sessionPath = Join-Path $env:LOCALAPPDATA 'CodexChatGPTRunner\pinchtab-session.json'
$profileName = ''
if (Test-Path $sessionPath) {
  try {
    $session = Get-Content -Raw $sessionPath | ConvertFrom-Json
    $profileName = [string]$session.profileName
  } catch {
    $profileName = ''
  }
}

$chrome = @(Get-CimInstance Win32_Process | Where-Object {
  $_.Name -eq 'chrome.exe' -and $_.CommandLine -match '--remote-debugging-port=\d+'
})

if ($profileName) {
  $escaped = [regex]::Escape($profileName)
  foreach ($proc in $chrome) {
    if ($proc.CommandLine -match $escaped -and $proc.CommandLine -match '--remote-debugging-port=(\d+)') {
      Write-Output ('http://127.0.0.1:' + $Matches[1])
      exit 0
    }
  }
}

foreach ($proc in $chrome) {
  if ($proc.CommandLine -match '\\\.pinchtab\\profiles\\instance-' -and $proc.CommandLine -match '--remote-debugging-port=(\d+)') {
    Write-Output ('http://127.0.0.1:' + $Matches[1])
    exit 0
  }
}

Write-Error 'Could not find an active Chrome remote-debugging port for the current Pinchtab ChatGPT session.'
exit 1
""",
    )
    if completed.returncode != 0:
        stderr_text = decode_windows_bytes(completed.stderr) if completed.stderr else ""
        stdout_text = decode_windows_bytes(completed.stdout) if completed.stdout else ""
        raise RuntimeError((stderr_text or stdout_text or "Failed to detect Chrome debug URL.").strip())
    debug_url = (decode_windows_bytes(completed.stdout) if completed.stdout else "").strip()
    if not debug_url:
        raise RuntimeError("Chrome debug URL detection returned an empty result.")
    return debug_url


def run_windows_cdp_chatgpt(
    *,
    payload_path: Path | None,
    output_path: Path | None,
    attachment_paths: Sequence[Path] | None,
    project_url: str,
    model_label: str,
    model_strategy: str,
    timeout_ms: int,
    begin_marker: str | None,
    end_marker: str | None,
    debug_url: str | None,
    marker_suffix: str,
    prefer_new_page: bool = False,
    prepare_only: bool = False,
    inspect_existing_reviews_only: bool = False,
    recover_existing_only: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    driver_path = write_windows_temp_file(f"chatgpt-cdp-driver-{marker_suffix}.js", _cdp_driver_source())
    config_path = write_windows_temp_file(
        f"codex-chatgpt-cdp-{marker_suffix}.json",
        json.dumps(
            {
                "debugUrl": debug_url or detect_windows_cdp_debug_url(),
                "timeoutMs": timeout_ms,
                "connectTimeoutMs": max(timeout_ms, 120000),
                "projectUrl": project_url,
                "modelLabel": model_label,
                "modelStrategy": model_strategy,
                "preferNewPage": prefer_new_page,
                "prepareOnly": prepare_only,
                "inspectExistingReviewsOnly": inspect_existing_reviews_only,
                "recoverExistingOnly": recover_existing_only,
                **({"payloadPath": to_windows_path(payload_path)} if payload_path is not None else {}),
                **({"outputPath": to_windows_path(output_path)} if output_path is not None else {}),
                **(
                    {"attachmentPaths": [to_windows_path(path) for path in attachment_paths]}
                    if attachment_paths
                    else {}
                ),
                **({"beginMarker": begin_marker} if begin_marker is not None else {}),
                **({"endMarker": end_marker} if end_marker is not None else {}),
            },
            ensure_ascii=False,
        ),
    )
    try:
        return subprocess.run(
            [WINDOWS_NODE, to_windows_path(driver_path), to_windows_path(config_path)],
            check=False,
            capture_output=True,
        )
    finally:
        safe_unlink(driver_path)
        safe_unlink(config_path)


def inspect_windows_cdp_reviews(*, project_url: str, debug_url: str | None, marker_suffix: str) -> dict[str, object]:
    completed = run_windows_cdp_chatgpt(
        payload_path=None,
        output_path=None,
        attachment_paths=None,
        project_url=project_url,
        model_label="",
        model_strategy="ignore",
        timeout_ms=120000,
        begin_marker=None,
        end_marker=None,
        debug_url=debug_url,
        marker_suffix=f"{marker_suffix}-inspect",
        inspect_existing_reviews_only=True,
    )
    stdout_text = decode_windows_bytes(completed.stdout) if completed.stdout else ""
    stderr_text = decode_windows_bytes(completed.stderr) if completed.stderr else ""
    if completed.returncode != 0:
        raise RuntimeError((stderr_text or stdout_text or "Failed to inspect existing ChatGPT review tabs.").strip())
    payload = _json_tail(stdout_text)
    if not isinstance(payload, dict):
        raise RuntimeError("Existing review inspection returned an invalid payload.")
    return payload


def ensure_no_pending_windows_cdp_reviews(*, project_url: str, debug_url: str | None, marker_suffix: str) -> None:
    pending = inspect_windows_cdp_reviews(
        project_url=project_url,
        debug_url=debug_url,
        marker_suffix=marker_suffix,
    ).get("pendingReviews", [])
    if not isinstance(pending, list) or not pending:
        return
    pending_urls: list[str] = []
    for entry in pending:
        if isinstance(entry, dict):
            url = str(entry.get("url", "")).strip()
            state = str(entry.get("state", "")).strip()
            pending_urls.append(f"{state or 'pending'}:{url}" if url else state or "pending")
        else:
            pending_urls.append(str(entry))
    raise RuntimeError(
        "Existing ChatGPT review tabs are still pending or incomplete. Wait for them to finish before starting a new review batch.\n"
        + "\n".join(pending_urls[:10])
    )


def recover_existing_windows_cdp_candidates(
    *,
    candidate_dir: Path,
    project_url: str,
    model_label: str,
    timeout_ms: int,
    debug_url: str | None,
    marker_suffix: str,
) -> list[ReviewCandidate]:
    recovered: list[ReviewCandidate] = []
    for prompt_path in sorted(candidate_dir.glob("candidate-*.prompt.md")):
        try:
            index, label = parse_candidate_prompt_filename(prompt_path)
            bundle_text = prompt_path.read_text(encoding="utf-8")
            begin_marker, end_marker = parse_review_markers(bundle_text)
        except (OSError, ValueError):
            continue
        output_path = windows_temp_path(f"codex-chatgpt-recover-{marker_suffix}-{index:02d}.md")
        try:
            completed = run_windows_cdp_chatgpt(
                payload_path=None,
                output_path=output_path,
                attachment_paths=None,
                project_url=project_url,
                model_label=model_label,
                model_strategy="ignore",
                timeout_ms=timeout_ms,
                begin_marker=begin_marker,
                end_marker=end_marker,
                debug_url=debug_url,
                marker_suffix=f"{marker_suffix}-recover-{index:02d}",
                recover_existing_only=True,
            )
            stdout_text = decode_windows_bytes(completed.stdout) if completed.stdout else ""
            recovered.append(
                ReviewCandidate(
                    index=index,
                    label=label,
                    prompt_text=bundle_text,
                    review_text=_read_output_text(output_path) or stdout_text.strip(),
                    output_path=output_path,
                    returncode=completed.returncode,
                    stdout_text=stdout_text,
                    stderr_text=decode_windows_bytes(completed.stderr) if completed.stderr else "",
                    metadata=_json_tail(stdout_text),
                )
            )
        finally:
            safe_unlink(output_path)
    return recovered


def prepare_windows_cdp_chatgpt(
    *,
    project_url: str,
    model_label: str,
    model_strategy: str,
    debug_url: str | None,
    marker_suffix: str,
) -> None:
    last_error = ""
    for attempt in range(1, 3):
        completed = run_windows_cdp_chatgpt(
            payload_path=None,
            output_path=None,
            attachment_paths=None,
            project_url=project_url,
            model_label=model_label,
            model_strategy=model_strategy,
            timeout_ms=180000,
            begin_marker=None,
            end_marker=None,
            debug_url=debug_url,
            marker_suffix=f"{marker_suffix}-prepare-{attempt}",
            prepare_only=True,
        )
        if completed.returncode == 0:
            return
        stdout_text = decode_windows_bytes(completed.stdout) if completed.stdout else ""
        stderr_text = decode_windows_bytes(completed.stderr) if completed.stderr else ""
        last_error = (stderr_text or stdout_text or "Failed to prepare ChatGPT project page.").strip()
        if "connectOverCDP: Timeout" not in last_error or attempt == 2:
            break
        time.sleep(2)
    raise RuntimeError(last_error or "Failed to prepare ChatGPT project page.")


def run_windows_cdp_chatgpt_fanout(
    *,
    review_jobs: Sequence[tuple[int, str, str]],
    attachment_paths: Sequence[Path] | None,
    project_url: str,
    model_label: str,
    model_strategy: str,
    timeout_ms: int,
    debug_url: str | None,
    marker_suffix: str,
) -> list[ReviewCandidate]:
    resolved_debug_url = debug_url or detect_windows_cdp_debug_url()
    effective_model_strategy = model_strategy
    if model_strategy == "select":
        prepare_windows_cdp_chatgpt(
            project_url=project_url,
            model_label=model_label,
            model_strategy=model_strategy,
            debug_url=resolved_debug_url,
            marker_suffix=marker_suffix,
        )
        effective_model_strategy = "ignore"

    driver_path = write_windows_temp_file(f"chatgpt-cdp-driver-{marker_suffix}.js", _cdp_driver_source())
    running: list[tuple[ReviewCandidate, subprocess.Popen[bytes], Path, Path]] = []
    try:
        for index, label, prompt_text in review_jobs:
            payload_path = write_windows_temp_file(
                f"codex-chatgpt-payload-{marker_suffix}-{index:02d}.txt",
                prompt_text,
            )
            output_path = windows_temp_path(f"codex-chatgpt-output-{marker_suffix}-{index:02d}.md")
            config_path = write_windows_temp_file(
                f"codex-chatgpt-cdp-{marker_suffix}-{index:02d}.json",
                json.dumps(
                    {
                        "debugUrl": resolved_debug_url,
                        "payloadPath": to_windows_path(payload_path),
                        "outputPath": to_windows_path(output_path),
                        "attachmentPaths": [to_windows_path(path) for path in (attachment_paths or [])],
                        "beginMarker": f"BEGIN_CDX_REVIEW_{marker_suffix}_{index:02d}",
                        "endMarker": f"END_CDX_REVIEW_{marker_suffix}_{index:02d}",
                        "timeoutMs": timeout_ms,
                        "projectUrl": project_url,
                        "modelLabel": model_label,
                        "modelStrategy": effective_model_strategy,
                        "preferNewPage": True,
                    },
                    ensure_ascii=False,
                ),
            )
            running.append(
                (
                    ReviewCandidate(
                        index=index,
                        label=label,
                        prompt_text=prompt_text,
                        review_text="",
                        output_path=output_path,
                        returncode=-1,
                        stdout_text="",
                        stderr_text="",
                        metadata={},
                    ),
                    subprocess.Popen(
                        [WINDOWS_NODE, to_windows_path(driver_path), to_windows_path(config_path)],
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    ),
                    payload_path,
                    config_path,
                )
            )

        completed_candidates: list[ReviewCandidate] = []
        for candidate, process, payload_path, config_path in running:
            stdout_bytes, stderr_bytes = process.communicate()
            stdout_text = decode_windows_bytes(stdout_bytes) if stdout_bytes else ""
            completed_candidates.append(
                ReviewCandidate(
                    index=candidate.index,
                    label=candidate.label,
                    prompt_text=candidate.prompt_text,
                    review_text=_read_output_text(candidate.output_path) or stdout_text.strip(),
                    output_path=candidate.output_path,
                    returncode=process.returncode or 0,
                    stdout_text=stdout_text,
                    stderr_text=decode_windows_bytes(stderr_bytes) if stderr_bytes else "",
                    metadata=_json_tail(stdout_text),
                )
            )
            safe_unlink(payload_path)
            safe_unlink(config_path)
        return completed_candidates
    finally:
        for candidate, process, payload_path, config_path in running:
            terminate_process(process)
            safe_unlink(payload_path)
            safe_unlink(config_path)
            safe_unlink(candidate.output_path)
        safe_unlink(driver_path)


def copy_to_windows_clipboard(text: str) -> None:
    payload_path = write_windows_temp_file("codex-chatgpt-manual-payload.txt", text)
    subprocess.run(
        [
            POWERSHELL_PATH,
            "-NoProfile",
            "-Command",
            f"Get-Content -Raw '{to_windows_path(payload_path)}' | Set-Clipboard",
        ],
        check=True,
        capture_output=True,
    )


def open_windows_browser(url: str) -> None:
    if not url:
        return
    subprocess.run(
        [
            "/mnt/c/Windows/System32/cmd.exe",
            "/c",
            "start",
            "",
            url,
        ],
        check=True,
        capture_output=True,
    )
