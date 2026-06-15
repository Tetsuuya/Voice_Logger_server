# 🎙️ VoiceLogger Bot

A Telegram bot that **transcribes voice notes**, generates **AI-powered summaries**, and logs everything to **Google Sheets** — automatically.

Built as a portfolio project to demonstrate real-world integration of Telegram Bot API, Groq AI (Whisper + LLaMA), and Google Sheets API.

---

## ✨ Features

- 🎙️ **Voice transcription** — powered by Whisper via Groq API
- 🤖 **AI summaries** — concise 1–2 sentence summaries via LLaMA 3
- 📊 **Google Sheets logging** — timestamped logs with sender, duration, transcript & summary
- 📋 **Per-user sheet support** — each user can link their own Google Sheet
- 🔄 **Rate limiting** — 15s cooldown + 20 voice notes/hour per user
- 🗑️ **Reset command** — clear sheet logs without affecting Telegram history
- ☁️ **Deployed on Render** — always online via UptimeRobot keep-alive

---

## 🤖 Try It

Search for the bot on Telegram: **`@YourBotUsername`**

### Commands
| Command | Description |
|---|---|
| `/start` | Set up your own Google Sheet |
| `/setsheet` | Change your Google Sheet |
| `/mysheet` | See which sheet is active |
| `/skip` | Use the default shared sheet |
| `/reset` | Clear all log rows from your sheet |

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Bot framework | [python-telegram-bot 21.9](https://python-telegram-bot.org/) |
| Transcription | [Groq Whisper large-v3-turbo](https://groq.com/) |
| AI summary | [LLaMA 3.1 8B Instant via Groq](https://groq.com/) |
| Sheets integration | [gspread](https://gspread.readthedocs.io/) + Google Sheets API |
| Deployment | [Render](https://render.com/) (Web Service, free tier) |
| Keep-alive | [UptimeRobot](https://uptimerobot.com/) (pings every 5 min) |
| Language | Python 3.12 |

---

## 🚀 Self-Hosting

### 1. Clone the repo
```bash
git clone https://github.com/Tetsuuya/Voice_Logger_server.git
cd Voice_Logger_server
```

### 2. Create virtual environment & install dependencies
```bash
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 3. Configure environment variables
Create a `.env` file:
```env
TELEGRAM_TOKEN="your_telegram_bot_token"
GROQ_API_KEY="your_groq_api_key"
SPREADSHEET_ID="your_default_spreadsheet_id"
CREDENTIALS_FILE=path/to/your/google-credentials.json
```

### 4. Run the bot
```bash
python voice_logger_bot.py
```

---

## 📋 Google Sheets Setup

1. Go to [sheets.new](https://sheets.new) and create a new sheet
2. Click **Share → General access → Anyone with the link → Editor**
3. Copy the sheet link and send it to the bot via `/start`

No service account sharing required — just make it publicly editable.

---

## 📁 Project Structure

```
VoiceLogger/
├── voice_logger_bot.py   # Main bot logic
├── requirements.txt      # Python dependencies
├── render.yaml           # Render deployment config
├── .python-version       # Python 3.12 pin for Render
├── .env                  # Environment variables (not committed)
└── user_prefs.json       # Per-user sheet preferences (auto-generated)
```

---

## 📄 License

MIT — free to use, modify, and distribute.
