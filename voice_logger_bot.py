"""
VoiceLogger Bot
---------------
Logs Telegram voice notes to Google Sheets with AI auto-summaries.

Users can provide their own Google Sheet on /start, or skip to use the
bot owner's default sheet.

Setup:
  pip install python-telegram-bot gspread google-auth groq

Usage:
  python voice_logger_bot.py
"""

import os
import re
import json
import logging
import tempfile
import datetime
import asyncio

from telegram import Update, ReplyKeyboardRemove, BotCommand
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)

import gspread
from google.oauth2.service_account import Credentials

from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── CONFIG ────────────────────────────────────────────────────────────────────

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_TOKEN")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY")
DEFAULT_SHEET_ID  = os.getenv("SPREADSHEET_ID")   # fallback / bot-owner's sheet
CREDENTIALS_FILE  = os.getenv("CREDENTIALS_FILE")

SHEET_NAME        = "Voice Logs"   # Tab name — created automatically if missing

# Simple JSON file to persist per-user sheet choices across restarts
USER_PREFS_FILE   = os.path.join(os.path.dirname(__file__), "user_prefs.json")

# Conversation states
WAITING_FOR_SHEET = 1

# ── LOGGING ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
log = logging.getLogger(__name__)


# ── USER PREFS (sheet per user) ───────────────────────────────────────────────

def load_prefs() -> dict:
    if os.path.exists(USER_PREFS_FILE):
        try:
            with open(USER_PREFS_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_prefs(prefs: dict):
    with open(USER_PREFS_FILE, "w") as f:
        json.dump(prefs, f, indent=2)


user_prefs: dict = load_prefs()   # { str(user_id): sheet_id }


def get_sheet_id_for_user(user_id: int) -> str:
    """Return the sheet ID configured for this user, or the default."""
    return user_prefs.get(str(user_id), DEFAULT_SHEET_ID)


def set_sheet_id_for_user(user_id: int, sheet_id: str):
    user_prefs[str(user_id)] = sheet_id
    save_prefs(user_prefs)


def extract_sheet_id(text: str) -> str | None:
    """
    Accept either a full Google Sheets URL or a bare spreadsheet ID.
    Returns the ID string, or None if it can't be parsed.
    """
    # URL pattern: /spreadsheets/d/<ID>/
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", text)
    if match:
        return match.group(1)
    # Bare ID: only URL-safe base64 chars, at least 20 chars long
    bare = text.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{20,}", bare):
        return bare
    return None

# ── GOOGLE SHEETS ─────────────────────────────────────────────────────────────

def _gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scopes)
    return gspread.authorize(creds)


def get_sheet(sheet_id: str):
    client = _gspread_client()
    book   = client.open_by_key(sheet_id)

    try:
        sheet = book.worksheet(SHEET_NAME)
    except gspread.WorksheetNotFound:
        sheet = book.add_worksheet(title=SHEET_NAME, rows=1000, cols=6)
        sheet.append_row(
            ["Timestamp", "Sender", "Duration (s)", "Transcript", "Summary", "File ID"],
            value_input_option="RAW",
        )
        sheet.format("A1:F1", {"textFormat": {"bold": True}})

    return sheet


def verify_sheet_access(sheet_id: str) -> bool:
    """Return True if the service account can open and write to this sheet."""
    try:
        sheet = get_sheet(sheet_id)
        # Try a lightweight read to confirm access
        sheet.row_count
        return True
    except Exception as e:
        log.warning(f"Sheet access check failed for {sheet_id}: {e}")
        return False


def log_to_sheet(sheet, sender: str, duration: int, transcript: str, summary: str, file_id: str):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sheet.append_row(
        [timestamp, sender, duration, transcript, summary, file_id],
        value_input_option="RAW",
    )

# ── GROQ TRANSCRIPTION + SUMMARY ─────────────────────────────────────────────

groq_client = Groq(api_key=GROQ_API_KEY)


def transcribe_audio(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        result = groq_client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), f),
            model="whisper-large-v3-turbo",
            response_format="text",
        )
    return result.strip() if isinstance(result, str) else result.text.strip()


def summarize(transcript: str) -> str:
    response = groq_client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a concise assistant. Summarize the voice note in 1–2 sentences. "
                    "Be direct — no filler phrases like 'The speaker says' or 'In this voice note'."
                ),
            },
            {"role": "user", "content": transcript},
        ],
        max_tokens=120,
    )
    return response.choices[0].message.content.strip()

# ── ONBOARDING CONVERSATION ───────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask the user if they want to use their own sheet."""
    await update.message.reply_text(
        "👋 *Welcome to VoiceLogger!*\n\n"
        "I transcribe your voice notes, summarise them with AI, and log everything to Google Sheets.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Want to use your own Google Sheet?*\n\n"
        "1️⃣ Go to [Google Sheets](https://sheets.new) and create a new sheet.\n"
        "2️⃣ Click *Share* → *General access* → change to *\"Anyone with the link\"* → set role to *Editor*.\n"
        "3️⃣ Copy the sheet link and send it to me here.\n\n"
        "— or —\n\n"
        "Type /skip to use the *default shared sheet* instead.\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📌 You can always change your sheet later with /setsheet.",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    return WAITING_FOR_SHEET


async def receive_sheet_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Validate and save the sheet link/ID the user sent."""
    text = update.message.text.strip()
    user_id = update.effective_user.id

    sheet_id = extract_sheet_id(text)
    if not sheet_id:
        await update.message.reply_text(
            "❌ That doesn't look like a valid Google Sheets link or ID.\n\n"
            "Please send the full URL (e.g. `https://docs.google.com/spreadsheets/d/…`) "
            "or just the ID, or type /skip to use the default sheet.",
            parse_mode="Markdown",
        )
        return WAITING_FOR_SHEET   # stay in conversation

    await update.message.reply_text("🔍 Checking access to your sheet…")

    if not verify_sheet_access(sheet_id):
        await update.message.reply_text(
            "⚠️ *I couldn't access that sheet.*\n\n"
            "Please make sure your sheet is set to *\"Anyone with the link can edit\"*:\n"
            "1️⃣ Open your sheet → Click *Share*\n"
            "2️⃣ Under *General access*, select *\"Anyone with the link\"*\n"
            "3️⃣ Set the role to *Editor*\n\n"
            "Then send me the link again, or type /skip to use the default sheet.",
            parse_mode="Markdown",
        )
        return WAITING_FOR_SHEET

    set_sheet_id_for_user(user_id, sheet_id)
    await update.message.reply_text(
        "✅ *Sheet connected!*\n\n"
        "All your voice notes will now be logged to your Google Sheet. "
        "Just send me a voice note to get started! 🎙️\n\n"
        "_(You can change your sheet anytime with /setsheet)_",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Skip sheet setup — use the default sheet."""
    user_id = update.effective_user.id
    # Remove any custom sheet → fall back to default
    user_prefs.pop(str(user_id), None)
    save_prefs(user_prefs)

    await update.message.reply_text(
        "👍 No problem! I'll use the *default shared sheet* for your logs.\n\n"
        "Just send me a voice note whenever you're ready! 🎙️\n\n"
        "_(You can set your own sheet anytime with /setsheet)_",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def cmd_setsheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Re-open the sheet-setup flow."""
    return await cmd_start(update, context)


async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Cancelled. Send a voice note anytime — I'll use the default sheet.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /reset — clears all log rows from the user's sheet (keeps the header).
    NOTE: This does NOT delete Telegram chat history — that stays in Telegram.
    """
    user_id = update.effective_user.id
    sheet_id = get_sheet_id_for_user(user_id)

    await update.message.reply_text(
        "🗑️ *Resetting your sheet logs…*\n\n"
        "⚠️ *Note:* This will delete all rows in your sheet (except the header). "
        "It does *NOT* delete your Telegram chat history — those messages stay in Telegram.",
        parse_mode="Markdown",
    )

    try:
        sheet = get_sheet(sheet_id)
        # Keep row 1 (header), delete everything below
        all_rows = sheet.get_all_values()
        if len(all_rows) > 1:
            sheet.delete_rows(2, len(all_rows))
        await update.message.reply_text(
            "✅ *Done!* All log entries have been cleared from your sheet.\n\n"
            "Your sheet header is still intact and ready for new voice notes. 🎙️",
            parse_mode="Markdown",
        )
    except Exception as e:
        log.error(f"Reset failed: {e}")
        await update.message.reply_text(
            f"❌ Couldn't clear the sheet: {e}\n\n"
            "Make sure your sheet is still set to *\"Anyone with the link can edit\"*.",
            parse_mode="Markdown",
        )


async def cmd_mysheet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tell the user which sheet is currently configured for them."""
    user_id = update.effective_user.id
    sheet_id = get_sheet_id_for_user(user_id)
    if sheet_id == DEFAULT_SHEET_ID:
        source = "the *default shared sheet*"
    else:
        source = f"your personal sheet:\nhttps://docs.google.com/spreadsheets/d/{sheet_id}"
    await update.message.reply_text(
        f"📋 Your voice logs are going to {source}.\n\n"
        "Use /setsheet to change it.",
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

# ── VOICE HANDLER ─────────────────────────────────────────────────────────────

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg    = update.message
    user   = msg.from_user
    sender = (
        f"{user.first_name} {user.last_name or ''}".strip()
        + (f" (@{user.username})" if user.username else "")
    )
    voice    = msg.voice
    duration = voice.duration

    await msg.reply_text("🎙️ Got it — transcribing…")

    # Download the voice file
    tg_file = await context.bot.get_file(voice.file_id)
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
    await tg_file.download_to_drive(tmp_path)

    try:
        transcript = transcribe_audio(tmp_path)
        log.info(f"Transcript: {transcript[:80]}…")
    except Exception as e:
        log.error(f"Transcription failed: {e}")
        await msg.reply_text(f"❌ Transcription failed: {e}")
        return
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)

    try:
        summary = summarize(transcript)
    except Exception as e:
        log.error(f"Summary failed: {e}")
        summary = "(summary unavailable)"

    # Determine which sheet to use for this user
    sheet_id = get_sheet_id_for_user(update.effective_user.id)

    try:
        sheet = get_sheet(sheet_id)
        log_to_sheet(sheet, sender, duration, transcript, summary, voice.file_id)
        log.info("Logged to sheet ✓")
    except Exception as e:
        log.error(f"Sheet write failed: {e}")
        await msg.reply_text(
            f"⚠️ Transcription done but sheet write failed: {e}\n\n"
            "If you're using a custom sheet, make sure it's still set to *\"Anyone with the link can edit\"* with Editor access.\n"
            "Use /setsheet to reconfigure.",
            parse_mode="Markdown",
        )
        return

    # Decide where we logged
    if sheet_id == DEFAULT_SHEET_ID:
        sheet_note = "_(logged to default sheet — use /setsheet to use your own)_"
    else:
        sheet_note = f"_(logged to [your sheet](https://docs.google.com/spreadsheets/d/{sheet_id}))_"

    reply = (
        f"✅ *Logged!*\n\n"
        f"📝 *Transcript:*\n{transcript}\n\n"
        f"💡 *Summary:*\n{summary}\n\n"
        f"{sheet_note}"
    )
    await msg.reply_text(reply, parse_mode="Markdown", disable_web_page_preview=True)


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me a voice note and I'll transcribe it, summarise it, and log it to Google Sheets.\n\n"
        "Commands:\n"
        "• /start or /setsheet — configure your own sheet\n"
        "• /mysheet — see which sheet is active\n"
        "• /skip — use the default sheet\n"
        "• /reset — clear all rows from your sheet _(does not delete Telegram chat history)_",
        parse_mode="Markdown",
    )

# ── MAIN ──────────────────────────────────────────────────────────────────────

async def post_init(app):
    """Automatically register bot commands in Telegram on startup."""
    await app.bot.set_my_commands([
        BotCommand("start",    "Set up your Google Sheet"),
        BotCommand("setsheet", "Change your Google Sheet"),
        BotCommand("mysheet",  "See which sheet is active"),
        BotCommand("skip",     "Use the default shared sheet"),
        BotCommand("reset",    "Clear all log rows from your sheet"),
        BotCommand("cancel",   "Cancel current action"),
    ])
    log.info("Bot commands registered with Telegram ✓")


def main():
    log.info("Starting VoiceLogger bot…")
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(post_init).build()

    # Conversation handler for sheet setup (/start and /setsheet)
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start",    cmd_start),
            CommandHandler("setsheet", cmd_setsheet),
        ],
        states={
            WAITING_FOR_SHEET: [
                CommandHandler("skip",   cmd_skip),
                CommandHandler("cancel", cmd_cancel),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_sheet_link),
            ],
        },
        fallbacks=[CommandHandler("cancel", cmd_cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("skip",    cmd_skip))
    app.add_handler(CommandHandler("mysheet", cmd_mysheet))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    log.info("Bot is running. Send a voice note to test.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
