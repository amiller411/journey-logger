# __main__py
import os
import logging
from pathlib import Path
import argparse
from dotenv import load_dotenv
from .telegram_bot import start_bot
from telegram.ext import ApplicationBuilder, MessageHandler, filters

from .map_processor import process_maps_link
from .sheet_writer import connect_to_sheet, append_journey_to_sheet

sheet = connect_to_sheet()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

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

if __name__ == "__main__":
    main()
