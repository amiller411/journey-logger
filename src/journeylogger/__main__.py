# __main__py
import os
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import argparse
from dotenv import load_dotenv
from .telegram_bot import start_bot
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
    SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    DEFAULT_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

    # ── Use args.dry_run, args.verbose later in your logic ─────────────
    if args.verbose:
        print(f"Loaded env: {env_file}")

    #   ─── Start the real bot ─────────────────────────────────────────────
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in the environment variables.")
    if not ORS_API_KEY:
        raise ValueError("ORS_API_KEY is not set in the environment variables.")
    
    start_bot(TELEGRAM_BOT_TOKEN)


def configure_logging(log_dir="logs"):
    """
    Configures logging:
    - INFO+ to info log
    - ERROR+ to error log
    - WARNING+ to console
    - Silences HTTP + Telegram noise
    """
    os.makedirs(log_dir, exist_ok=True)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)  # Set high, handlers control output

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

    # ── Console handler: only WARNING+ ─────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(logging.Formatter(
        "%(levelname)s: %(message)s"
    ))
    root.addHandler(console_handler)

    # ── Suppress external noise ────────────────────────────────
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("telegram.ext._application").setLevel(logging.WARNING)

    logging.info("Logging configured. Logs at '%s'.", log_dir)


if __name__ == "__main__":
    configure_logging()
    main()
