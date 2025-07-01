# main.py
import os
from dotenv import load_dotenv
from journeylogger.telegram_bot import start_bot
from pathlib import Path

# ── Load the env file they asked for ───────────────────────────────
root = Path(__file__).resolve()
env_file = root / ".env.production"
load_dotenv(env_file)

USE_WEBHOOK = os.getenv("USE_WEBHOOK", True)
PORT = int(os.getenv("PORT", 8080))
WEBHOOK_URL = os.getenv("WEBHOOK_URL")
ALLOWED_USER_IDS = {
    int(uid.strip())
    for uid in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",")
    if uid.strip().isdigit()
}

if USE_WEBHOOK and not WEBHOOK_URL:
    raise ValueError("WEBHOOK_URL must be set when USE_WEBHOOK is True")

start_bot(use_webhook=USE_WEBHOOK, webhook_url=WEBHOOK_URL, port=PORT)
