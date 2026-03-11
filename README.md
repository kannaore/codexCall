# Codex GPT-5.4 Review Helper

Use a small diff-focused review runner from WSL. The default flow uses Chrome DevTools automation against the existing headed ChatGPT browser session. Manual browser delivery remains available as a fallback.

For a recursive improvement loop, you can also let Codex code first, then send each round to the ChatGPT web model for structured review, and automatically feed the review back into Codex.

## Recommended setup

Default flow:

```bash
chatgpt-browser-up
chatgpt-browser-status
codex-gpt54-review
```

Recursive loop:

```bash
codex-gpt54-loop "로그인 리다이렉트 버그를 고치고 회귀 테스트까지 보강해줘."
```

Fallback manual flow:

```bash
codex-gpt54-review --delivery manual
```

## Commands

```bash
codex-gpt54-review
codex-gpt54-review --dry-run
codex-gpt54-review --mode hybrid --file docs/spec.md
codex-gpt54-review --prompt "이번 변경에서 버그, 회귀, 빠진 테스트만 짚어줘."
codex-gpt54-review --write-output /tmp/review.md
codex-gpt54-review --delivery manual
codex-gpt54-review --delivery pinchtab
codex-gpt54-review --model "ChatGPT 5.3 Instant" --model-strategy select
codex-gpt54-loop "결제 실패 재시도 로직을 안정화해줘."
codex-gpt54-loop --feedback-mode manual --max-rounds 4 "파일 업로드 race condition을 잡아줘."
codex-gpt54-loop --codex-full-auto --review-mode hybrid --review-file docs/spec.md "대시보드 필터 버그를 수정해줘."
codex-gpt54-loop --codex-resume-last --review-model "ChatGPT 5.4 Pro" --review-model-strategy select "방금 받은 리뷰 지적을 반영해."
codex-gpt54-loop --codex-session-id 019cda71-cbe0-7533-8e25-2ced2d2ae992 --review-model "ChatGPT 5.4 Pro" "현재 Codex 세션에 후속 작업을 주입해."
```

## Defaults

- target repo: current working directory
- delivery: `cdp`
- browser for automation: Windows headed ChatGPT session started by `chatgpt-browser-up`, reused through Chrome DevTools
- browser for manual fallback: your normal Windows browser
- model: `ChatGPT 5.4 Pro`
- model strategy: `select`
- project URL: `Codex전용`
- attachment mode: `diff`
- output file: `./.oracle-reviews/review-YYYYmmdd-HHMMSS.md`
- auto-selected files: only when `--mode files` or `--mode hybrid`
- extra files: add with `--file`
- untracked files: opt in with `--include-untracked`

Recursive loop defaults:

- max rounds: `3`
- feedback mode: `auto`
- review format: strict JSON verdict (`pass` or `revise`)
- review delivery: `cdp`
- review model strategy: `select`
- session artifacts: `./.oracle-reviews/loop-YYYYmmdd-HHMMSS/`
- saved artifacts per round: Codex JSONL, Codex last message, review JSON, stdout/stderr logs, manifest

## WSL note

Pinchtab mode is the default automation path. WSL builds a compact review bundle, then a Windows-side runner reuses the active Pinchtab ChatGPT browser, opens the project, submits the prompt, and writes the response to a file.

Manual mode exists only as a fallback.

`codex-gpt54-loop` builds on top of that review runner. Each round does:

1. `codex exec` for the requested task
2. `codex-gpt54-review` with a structured JSON review prompt
3. verdict check
4. automatic or manual feedback injection back into the same Codex session

If you already have a live Codex session, add `--codex-session-id <uuid>` or `--codex-resume-last` so the loop injects prompts into that existing session instead of starting a fresh one. For code changes, that existing session should already be opened in the target repository.

If the reviewer returns `pass`, the loop stops. If it returns `revise`, the tool writes a follow-up prompt from the review and continues until `--max-rounds` is reached.

## Testing

```bash
python3 -m unittest -v
```

If the ChatGPT browser is not ready:

```bash
chatgpt-browser-up
chatgpt-browser-status
```

For the lightest token usage, keep the default `--mode diff`. Use `--mode hybrid` only when the diff alone is not enough, and use `--mode files` only when full file context is necessary.

Current limitations:

- Pinchtab mode can still trigger anti-bot checks depending on ChatGPT/Cloudflare.
- Pinchtab mode cannot switch ChatGPT models automatically; use `--delivery cdp` for enforced model selection.
- Manual mode copies the prompt and opens the project URL, but you still paste/send in ChatGPT yourself.
- CDP mode now selects or verifies the project-page model picker on `Codex전용`.
- Keep Python Playwright/browser dependencies installed if you want Scrapling dynamic fetchers.

If you later add an API key, you can still switch to:

```bash
OPENAI_API_KEY=... npx -y @steipete/oracle --engine api ...
```
