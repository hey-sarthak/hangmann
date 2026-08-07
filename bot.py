"""
Hangman Discord bot.
- Slash commands: /hangman (start), /guess, /hangman-status, /hangman-stop
- Words are generated live via Groq API (see groq_words.py), with a local fallback.
- Runs a tiny Flask server alongside the bot so a free host (Render) can be
  pinged by an external uptime service to prevent it from spinning down.
"""

import os
import threading
import logging

import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask

from game import HangmanGame
from groq_words import get_random_word

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("hangman-bot")

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
PORT = int(os.environ.get("PORT", 10000))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# One active game per channel, plus a rolling set of recently used words
# per channel so Groq doesn't repeat itself too often.
active_games: dict[int, HangmanGame] = {}
recent_words: dict[int, set[str]] = {}
RECENT_WORDS_LIMIT = 25


# ---------------------------------------------------------------------------
# Keep-alive web server (for Render free tier + external uptime pinger)
# ---------------------------------------------------------------------------
flask_app = Flask(__name__)


@flask_app.route("/")
@flask_app.route("/health")
def health():
    return {
        "status": "ok",
        "bot_ready": bot.is_ready(),
        "active_games": len(active_games),
    }, 200


def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT)


# ---------------------------------------------------------------------------
# Discord bot events & commands
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    log.info("Logged in as %s (id: %s)", bot.user, bot.user.id)
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash command(s)", len(synced))
    except Exception as e:
        log.exception("Failed to sync commands: %s", e)


def _build_embed(game: HangmanGame, title: str, color: discord.Color) -> discord.Embed:
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Word", value=f"`{game.display_word()}`", inline=False)
    embed.add_field(name="Category", value=game.category.title(), inline=True)
    embed.add_field(name="Guesses left", value=str(game.remaining_guesses()), inline=True)
    wrong = ", ".join(sorted(game.wrong_letters)) or "none"
    embed.add_field(name="Wrong letters", value=wrong, inline=False)
    embed.description = game.gallows()
    return embed


@bot.tree.command(name="hangman", description="Start a new game of Hangman in this channel")
async def hangman_start(interaction: discord.Interaction):
    channel_id = interaction.channel_id

    if channel_id in active_games and not active_games[channel_id].finished:
        await interaction.response.send_message(
            "A game is already running in this channel. Use `/guess` to play, "
            "or `/hangman-stop` to cancel it.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    used = recent_words.setdefault(channel_id, set())
    word, category = get_random_word(recent_words=used)
    used.add(word)
    if len(used) > RECENT_WORDS_LIMIT:
        used.pop()

    game = HangmanGame(word=word, category=category, starter_id=interaction.user.id)
    active_games[channel_id] = game

    embed = _build_embed(game, "🎯 New Hangman game started!", discord.Color.blurple())
    embed.set_footer(text=f"Started by {interaction.user.display_name} • Use /guess to play")
    await interaction.followup.send(embed=embed)


@bot.tree.command(name="guess", description="Guess a letter or the whole word")
@app_commands.describe(letter="A single letter, or the full word if you're feeling confident")
async def hangman_guess(interaction: discord.Interaction, letter: str):
    channel_id = interaction.channel_id
    game = active_games.get(channel_id)

    if not game or game.finished:
        await interaction.response.send_message(
            "No active game here. Start one with `/hangman`.", ephemeral=True
        )
        return

    guess_text = letter.strip().lower()

    # Whole-word guess
    if len(guess_text) > 1:
        if guess_text == game.word:
            game.guessed_letters.update(set(game.word))
            game.finished = True
            game.won = True
        else:
            game.wrong_letters.add(guess_text[:1] or "?")
            if game.wrong_count >= 6:
                game.finished = True
                game.won = False
        status = "correct" if game.won and game.finished else "wrong"
    elif not guess_text.isalpha():
        await interaction.response.send_message(
            "Please guess a single letter (a-z).", ephemeral=True
        )
        return
    else:
        status = game.guess(guess_text)

    if game.finished:
        if game.won:
            embed = _build_embed(game, "🎉 You got it!", discord.Color.green())
            embed.add_field(name="The word was", value=f"**{game.word}**", inline=False)
        else:
            embed = _build_embed(game, "💀 Game over!", discord.Color.red())
            embed.add_field(name="The word was", value=f"**{game.word}**", inline=False)
        await interaction.response.send_message(embed=embed)
        return

    if status == "already":
        await interaction.response.send_message(
            f"`{guess_text}` was already guessed.", ephemeral=True
        )
        return

    title = "✅ Correct!" if status == "correct" else "❌ Wrong!"
    color = discord.Color.green() if status == "correct" else discord.Color.orange()
    embed = _build_embed(game, title, color)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="hangman-status", description="Show the current game state")
async def hangman_status(interaction: discord.Interaction):
    game = active_games.get(interaction.channel_id)
    if not game or game.finished:
        await interaction.response.send_message(
            "No active game here. Start one with `/hangman`.", ephemeral=True
        )
        return
    embed = _build_embed(game, "Current Hangman game", discord.Color.blurple())
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="hangman-stop", description="Cancel the current game in this channel")
async def hangman_stop(interaction: discord.Interaction):
    game = active_games.get(interaction.channel_id)
    if not game or game.finished:
        await interaction.response.send_message("No active game to cancel.", ephemeral=True)
        return
    active_games.pop(interaction.channel_id, None)
    await interaction.response.send_message(
        f"Game cancelled. The word was **{game.word}**."
    )


def main():
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN environment variable is not set.")

    # Run Flask in a background thread so Render sees an open port
    # (required for it to treat this as a live web service) and so an
    # external uptime pinger has something to hit.
    threading.Thread(target=run_flask, daemon=True).start()
    log.info("Keep-alive server listening on port %s", PORT)

    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
