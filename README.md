# VoiceLogger Bot

Telegram bot that transcribes voice notes, generates AI summaries, and logs them to Google Sheets.

## Setup

### 1. Activate Virtual Environment

**Windows CMD:**
```cmd
venv\Scripts\activate
```

**Windows PowerShell:**
```powershell
venv\Scripts\Activate.ps1
```

### 2. Install Dependencies

```cmd
pip install python-telegram-bot gspread google-auth groq python-dotenv
```

### 3. Configure Environment Variables

Make sure your `.env` file contains:
```env
TELEGRAM_TOKEN="your_telegram_bot_token"
GROQ_API_KEY="your_groq_api_key"
SPREADSHEET_ID="your_google_spreadsheet_id"
CREDENTIALS_FILE="path\to\your\credentials.json"
```

### 4. Run the Bot

```cmd
python voice_logger_bot.py
```

## Usage

1. Start a chat with your bot on Telegram
2. Send a voice note
3. Bot will transcribe, summarize, and log it to your Google Sheet

## Troubleshooting

**If bot doesn't start:**
- Check that virtual environment is activated (you should see `(venv)` in your prompt)
- Verify all environment variables are set correctly in `.env`
- Ensure Google credentials JSON file exists at the specified path

**To deactivate virtual environment:**
```cmd
deactivate
```
