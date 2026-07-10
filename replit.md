# SMART Bot — Telegram Movie/AI Bot

## Overview
A Telegram bot (`bot.py`, using `pyTelegramBotAPI`) with:
- Movie search (scrapes via a local PHP endpoint, `movies.php`)
- AI subtitle generation/translation/emoji-tagging via faster-whisper + Gemini
- Local AI image/video upscaling (Real-ESRGAN / GFPGAN, CPU-only torch)
- A credit/referral system (`credits.py`, `referral.py`, backed by `users.json` + optional Google Sheets)
- A companion Flask "Mini App" web UI (`webapp.py`), served on port 5000 and started automatically by `bot.py`
- A reusable, provider-independent AI client (`config.py` + `ai_client.py`) for OpenAI-compatible chat completions (OpenRouter, HuggingFace Router, vLLM, RunPod, Ollama, etc.). Not yet wired into any Telegram handler — call `generate_ai_response(user_message, history, system_prompt)` from `ai_client.py` wherever AI replies are needed. Switching providers/models only requires changing `AI_BASE_URL` / `AI_API_KEY` / `AI_MODEL` in `.env` — no code changes. If `AI_BASE_URL` or `AI_MODEL` is unset, it returns a friendly "not configured yet" message instead of making any request.

## Running the project
Two workflows run in parallel:
- **Start application** — `python bot.py` (main bot + Flask mini app on port 5000)
- **PHP Movie API** — `php -S 127.0.0.1:8000` (serves `movies.php`, used for movie search; `PHP_API_URL` defaults to `http://127.0.0.1:8000/movies.php`)

Both must be running for full functionality; movie search fails silently if the PHP workflow is stopped.

## Environment / secrets
Required: `BOT_TOKEN` (Telegram bot token from @BotFather — must be unique; running the same token elsewhere causes a 409 polling conflict).
Optional: `ADMIN_USER_ID` (plain env var), `GEMINI_API_KEY` (AI subtitle correction/translation), `GOOGLE_SERVICE_ACCOUNT_JSON_BASE64` (Google Sheets referral tracking), `PHP_API_URL`, `ADSTERRA_LINK`, `SHORTENER_API_KEY`, `AD_SMARTLINK`.

## Dependency notes
- `torch`/`torchvision` are installed as **CPU-only** builds (`pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu`) — the default PyPI wheel pulls a huge CUDA build that exceeds the container's disk quota.
- `basicsr`, `facexlib`, `gfpgan`, `realesrgan` were installed with `pip install --no-build-isolation --break-system-packages` against the venv at `.pythonlibs/` (using the already-installed CPU torch) — build isolation would otherwise re-download the CUDA torch during their build step.
- These four packages plus `torch`/`torchvision` are commented out of `requirements.txt` (with a note) since the standard installer resolves `requirements.txt` directly and would otherwise try to fetch CUDA torch again.
- `sift-stack-py` was in the original `requirements.txt` but is not imported anywhere in the code — left out.

## Known follow-ups (not yet addressed)
- The Flask mini app trusts Telegram WebApp `init_data` without HMAC signature verification before granting credits/history/referral actions — a real user-impersonation risk if this app is exposed publicly.
