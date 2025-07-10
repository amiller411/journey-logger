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
logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger = logging.getLogger(__name__)
    logger.warning("Unhandled exception: %s", context.error)


def process_and_log_journey(short_url: str, timestamp=None) -> dict:
    """Expands URL, parses it, logs it to the Google Sheet, and returns result dict."""
    result = process_maps_link(short_url)
    if not result:
        # Log failed links for later inspection
        logger.error("process_maps_link() returned no result for URL: %s", short_url)
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

    now_london = datetime.now(ZoneInfo("Europe/London"))
    timestamp_str = now_london.strftime("%d %B %Y, %H:%M %Z")
    logger.info("Received message from user %s (ID: %s): %s", username, user_id, text)

    allowed_user_ids = [
    int(uid.strip())
    for uid in os.environ.get("ALLOWED_TELEGRAM_IDS", "").split(",")
    if uid.strip().isdigit()
]

    print(f"Allowed user IDs: {allowed_user_ids}")

    if user_id not in allowed_user_ids:
        logger.warning("Unauthorized user %s (ID: %s) tried to send a message: %s", username, user_id, text)
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return
        
    # Only process if it “looks like” a maps.app.goo.gl URL
    if text.startswith("https://maps"):
        # 1) Record current time in Europe/London

        await update.message.reply_text("Got your link—processing…")

        try:
            result = process_maps_link(text)
        except Exception as e:
            logger.error("Error processing link %s: %s from user %s: %s", text, e, username, user_id)
            await update.message.reply_text(f"❌ Error processing link: {e}")
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
            f"👤 User: @{username} (ID: {user_id})",
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

def start_bot(use_webhook=False, webhook_url=None, port=8080):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    # 🔹 Register error handler
    app.add_error_handler(error_handler)

    logger.info("Bot is running…")

    if use_webhook:
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=webhook_url,
        )
    else:
        app.run_polling()
