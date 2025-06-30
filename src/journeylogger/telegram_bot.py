# src/journeylogger/telegram_bot.py
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes

from .map_processor import process_maps_link
from .sheet_writer import append_journey_to_sheet, connect_to_sheet

# Initialize once
sheet = connect_to_sheet()
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

def process_and_log_journey(short_url: str, timestamp=None) -> dict:
    """Expands URL, parses it, logs it to the Google Sheet, and returns result dict."""
    result = process_maps_link(short_url)
    if not result:
        raise ValueError("Failed to parse short_url")

    if not timestamp:
        timestamp = datetime.now(ZoneInfo("Europe/London"))

    sheet = connect_to_sheet()
    append_journey_to_sheet(sheet, result, short_url=short_url, timestamp=timestamp)

    return result

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    username = user.username
    user_id = user.id
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

def start_bot(token: str):
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    logger.info("Bot is running…")
    app.run_polling()
