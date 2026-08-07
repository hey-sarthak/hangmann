# Hangman Discord Bot (Groq-powered, Render-hosted)

A Discord bot that plays Hangman using slash commands. Words are generated
live by the Groq API for variety, with a local fallback list if Groq is
unreachable.

## Commands
- `/hangman` — start a new game in the current channel
- `/guess letter:<a-z>` — guess a letter (or the whole word)
- `/hangman-status` — show the current board
- `/hangman-stop` — cancel the active game

## 1. Create the Discord bot
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) → **New Application**.
2. Go to **Bot** → **Add Bot** → copy the **Token** (this is your `DISCORD_TOKEN`).
3. No privileged intents are needed (the bot only uses slash commands), so you
   can leave Presence/Server Members/Message Content intents off.
4. Go to **OAuth2 → URL Generator**:
   - Scopes: `bot`, `applications.commands`
   - Bot permissions: `Send Messages`, `Embed Links`, `Use Slash Commands`
   - Open the generated URL and invite the bot to your server.

## 2. Get a Groq API key
Sign up at [console.groq.com](https://console.groq.com) → **API Keys** →
create a key. This is your `GROQ_API_KEY`.

## 3. Run locally (optional, for testing)
```bash
cp .env.example .env
# fill in DISCORD_TOKEN and GROQ_API_KEY in .env
pip install -r requirements.txt
python bot.py
```

## 4. Deploy to Render (Web Service)
1. Push this folder to a GitHub repo.
2. In Render, **New → Web Service**, connect the repo.
3. Root Directory: leave blank if these files sit at the repo root.
4. Settings:
   - **Environment:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Instance Type:** Free
5. Under **Environment Variables**, add:
   - `DISCORD_TOKEN` — your bot token
   - `GROQ_API_KEY` — your Groq key
   - `GROQ_MODEL` — `llama-3.3-70b-versatile`
   - `PYTHON_VERSION` — `3.11.9`
6. Click **Create Web Service**. Render will build and deploy, giving you a
   URL like `https://your-app-name.onrender.com`. The bot also starts a tiny
   Flask server on `$PORT` with a `/health` route — this is what makes
   Render treat it as a live web service, and it's also the endpoint your
   keep-alive pinger will hit.

(`render.yaml` in this repo is only used if you deploy via Render's
**Blueprint** option instead — with a manual Web Service it's ignored, kept
here just as a settings reference.)

## 5. Keep it awake 24/7 with cron-job.org (free)
Render's **free** web services spin down after ~15 minutes with no HTTP
traffic. Keep it warm for $0 using [cron-job.org](https://cron-job.org):

1. Create a free account, click **Create cronjob**.
2. URL: `https://<your-app-name>.onrender.com/health`
3. Schedule: every 5 minutes.
4. Save. The periodic request keeps the Render instance from spinning down.

(Render's own Cron Job service type is a paid feature — roughly $1/month
minimum — so it isn't used in this setup.)

## Notes
- Free Render instances also have limited monthly hours (750/month across
  your account) — a single always-on service comfortably fits within that,
  but be aware if you run other free services too.
- One game is tracked per Discord channel at a time.
- If `GROQ_API_KEY` is missing or the Groq call fails for any reason, the
  bot silently falls back to a built-in word list so gameplay never breaks.
