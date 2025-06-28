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

    # ─── If they asked for a dry-run, forge one Update and exercise your handler ─
    # if args.dry_run:
    #     # … inside your if args.dry_run: branch …

    #     import asyncio
    #     from types import SimpleNamespace
    #     from datetime import datetime
    #     from zoneinfo import ZoneInfo
    #     from telegram import Update, Message, Chat, User

    #     # 1) Build fake Update/Message
    #     user    = User(id=123, first_name="Tester", is_bot=False)
    #     chat    = Chat(id=123, type="private")
    #     msg_obj = Message(
    #         message_id=1,
    #         date=datetime.now(ZoneInfo("Europe/London")),
    #         chat=chat,
    #         from_user=user,
    #         text=args.test_url
    #     )
    #     update = Update(update_id=1, message=msg_obj)

    #     # 2) DummyBot that just prints send_message calls
    #     class DummyBot:
    #         async def send_message(self, chat_id, text, **kwargs):
    #             print(f"\n📨 BOT would send to {chat_id!r}: {text}\n")

    #     dummy_bot = DummyBot()

    #     # 3) Attach dummy_bot to the Message so reply_text() will use it
    #     object.__setattr__(msg_obj, "_bot", dummy_bot)

    #     # 4) Also make a fake Context with our dummy bot
    #     fake_context = SimpleNamespace(bot=dummy_bot)

    #     # 5) Run your handler — breakpoints inside handle_message (or deeper) will hit
    #     asyncio.run(handle_message(update, fake_context))

    #     # 6) Then exit so the real bot never starts
    #     return

    #   ─── Start the real bot ─────────────────────────────────────────────
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in the environment variables.")
    if not ORS_API_KEY:
        raise ValueError("ORS_API_KEY is not set in the environment variables.")
    
    start_bot(TELEGRAM_BOT_TOKEN)

if __name__ == "__main__":
    main()
