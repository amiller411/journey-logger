# __main__py
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import argparse
from dotenv import load_dotenv
from .telegram_bot import start_bot
from typing import Optional
from telegram.ext import ApplicationBuilder, MessageHandler, filters

from .map_processor import process_maps_link
from .sheet_writer import connect_to_sheet, append_journey_to_sheet

sheet = connect_to_sheet()

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--env", choices=["dev","prod"], default="prod")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--verbose", action="store_true")
    p.add_argument("-u", "--test-url", dest="test_url", type=str, help="(dry-run) Google Maps short link to process")
    return p.parse_args()


def main():
    args = parse_args()

    # ── Load the env file they asked for ───────────────────────────────
    root = Path(__file__).resolve().parent.parent.parent
    env_file = root / (".env.production" if args.env=="prod" else ".env.development")
    load_dotenv(env_file)

    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    ORS_API_KEY = os.getenv("ORS_API_KEY")
    GMAPS_API_KEY = os.getenv("GMAPS_API_KEY")
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    DEFAULT_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
    ALLOWED_USER_IDS = {
        int(uid.strip())
        for uid in os.getenv("ALLOWED_TELEGRAM_IDS", "").split(",")
        if uid.strip().isdigit()
    }

    # ── Use args.dry_run, args.verbose later in your logic ─────────────
    if args.verbose:
        print(f"Loaded env: {env_file}")

    #   ─── Start the real bot ─────────────────────────────────────────────
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in the environment variables.")
    if not ORS_API_KEY:
        raise ValueError("ORS_API_KEY is not set in the environment variables.")
    
    start_bot()


class MaxLevelFilter(logging.Filter):
    """
    Filter that allows only log records up to a certain level.
    """
    def __init__(self, max_level: int):
        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= self.max_level


def configure_logging(log_dir: str = "logs") -> None:
    """
    Configures logging:
    - INFO+ to info log
    - ERROR+ to error log
    - DEBUG/INFO only to console (no WARNING+)
    - Silences HTTP + Telegram noise
    """
    os.makedirs(log_dir, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Capture everything, let handlers decide

    # ── File handler: INFO and above ───────────────────────────
    info_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "journeylogger-info.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8"
    )
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root.addHandler(info_handler)

    # ── File handler: ERROR only ───────────────────────────────
    error_handler = RotatingFileHandler(
        filename=os.path.join(log_dir, "journeylogger-errors.log"),
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    root.addHandler(error_handler)

    # ── Console handler: only DEBUG and INFO ───────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)  # Minimum level to accept
    console_handler.addFilter(MaxLevelFilter(logging.INFO))  # Max level allowed
    console_handler.setFormatter(logging.Formatter(
        "%(levelname)s: %(message)s"
    ))
    root.addHandler(console_handler)

    # ── Suppress external noise ────────────────────────────────
    noisy_modules = [
        "urllib3",
        "httpx",
        "telegram",
        "telegram.ext._application",
        "telegram.ext.Application"
    ]
    for module in noisy_modules:
        logging.getLogger(module).setLevel(logging.WARNING)

if __name__ == "__main__":
    configure_logging()
    main()
