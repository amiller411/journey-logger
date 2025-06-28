# __main__py
import os
import logging
from pathlib import Path
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

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

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    # await update.message.reply_text(f"🔍 Normalized link:\n{text}")

    # Only process if it “looks like” a maps.app.goo.gl URL
    if text.startswith("https://maps"):
        # 1) Record current time in Europe/London
        now_london = datetime.now(ZoneInfo("Europe/London"))
        timestamp_str = now_london.strftime("%d %B %Y, %H:%M %Z")

        await update.message.reply_text("Got your link—processing…")
        result = process_maps_link(text)
        if not result:
            await update.message.reply_text("❌ Failed to process the link.")
            return
        
        # Append to Google Sheet
        now_london = datetime.now(ZoneInfo("Europe/London"))
        try:
            append_journey_to_sheet(sheet, result, short_url=text, timestamp=now_london)
        except Exception as e:
            await update.message.reply_text(f"⚠️ Failed to write to sheet: {e}")

        # 2) Build a reply text from result
        origin = result["origin"]
        dest = result["destination"]

        parts = [
            f"🕑 Processed: {timestamp_str}",
            "",
            f"🏠 Origin:",
            f"   • Town:     {origin.get('town', 'N/A')}",
            f"   • Postcode: {origin.get('postcode', 'N/A')}",
            f"   • Lat/Lon:  {origin.get('lat', 'N/A')}, {origin.get('lon', 'N/A')}",
            "",
            f"📍 Destination:",
            f"   • Town:       {dest.get('town', 'N/A')}",
            f"   • Postcode:   {dest.get('postcode', 'N/A')}",
            f"   • Lat/Lon:    {dest.get('lat', 'N/A')}, {dest.get('lon', 'N/A')}",
            f"   • Visit Type: {dest.get('visit_type', 'N/A')}",
        ]

        # 3) Include the estimated miles if available
        if result.get("distance_miles") is not None:
            parts.append(f"\n🛣️ Estimated Road Distance: {result['distance_miles']:.2f} miles")

        reply = "\n".join(parts)
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("Please send a maps.app.goo.gl link.")

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
    if args.dry_run:
        # … inside your if args.dry_run: branch …

        import asyncio
        from types import SimpleNamespace
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from telegram import Update, Message, Chat, User

        # 1) Build fake Update/Message
        user    = User(id=123, first_name="Tester", is_bot=False)
        chat    = Chat(id=123, type="private")
        msg_obj = Message(
            message_id=1,
            date=datetime.now(ZoneInfo("Europe/London")),
            chat=chat,
            from_user=user,
            text=args.test_url
        )
        update = Update(update_id=1, message=msg_obj)

        # 2) DummyBot that just prints send_message calls
        class DummyBot:
            async def send_message(self, chat_id, text, **kwargs):
                print(f"\n📨 BOT would send to {chat_id!r}: {text}\n")

        dummy_bot = DummyBot()

        # 3) Attach dummy_bot to the Message so reply_text() will use it
        object.__setattr__(msg_obj, "_bot", dummy_bot)

        # 4) Also make a fake Context with our dummy bot
        fake_context = SimpleNamespace(bot=dummy_bot)

        # 5) Run your handler — breakpoints inside handle_message (or deeper) will hit
        asyncio.run(handle_message(update, fake_context))

        # 6) Then exit so the real bot never starts
        return

    #   ─── Start the real bot ─────────────────────────────────────────────
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in the environment variables.")
    if not ORS_API_KEY:
        raise ValueError("ORS_API_KEY is not set in the environment variables.")
    
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    print("Bot is running…")
    app.run_polling()

if __name__ == "__main__":
    main()
