from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from pathlib import Path
from typing import Sequence


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
DEFAULT_ATTACHMENT_FORMAT = "auto"
DEFAULT_TIMEOUT_MS = 900000
MIN_TIMEOUT_MS_54 = 1800000
MIN_TIMEOUT_MS_54_PRO = 3600000
WINDOWS_TEMP_DIR = Path("/mnt/c/Users/Administrator/AppData/Local/Temp")
WINDOWS_RUNNER_DIR = Path("/mnt/c/Users/Administrator/AppData/Local/CodexChatGPTRunner")
WINDOWS_NODE = "/mnt/c/Program Files/nodejs/node.exe"
MAX_FILE_CHARS = 12000
MAX_BUNDLE_CHARS = 100000
SNAPSHOT_INLINE_CHAR_THRESHOLD = 30000
SENSITIVE_SNAPSHOT_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".crt", ".cer", ".der"}
SENSITIVE_SNAPSHOT_NAMES = {".oracle-bridge-token"}

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


def normalize_model_label(value: str) -> str:
    return " ".join(str(value or "").lower().replace("chatgpt", "").split())


def effective_timeout_ms(model_label: str, requested_timeout_ms: int) -> int:
    normalized = normalize_model_label(model_label)
    if "5.4 pro" in normalized:
        return max(requested_timeout_ms, MIN_TIMEOUT_MS_54_PRO)
    if "5.4" in normalized:
        return max(requested_timeout_ms, MIN_TIMEOUT_MS_54)
    return requested_timeout_ms


def repo_script_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / name
