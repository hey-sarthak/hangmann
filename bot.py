import os
import threading
from flask import Flask, jsonify
import discord
from discord.ext import commands

from game import HangmanGame
from groq_words import get_random_word

# 1. Flask server for Render keep-alive ping
app = Flask(__name__)

@app.route("/")
@app.route("/health")
def health_check():
    return jsonify({"status": "ok"}), 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# 2. Discord Bot setup with Message Content Intent enabled
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Active games stored per channel ID
games = {}

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.command(name="hangman", aliases=["start"])
async def start_game(ctx):
    channel_id = ctx.channel.id
    if channel_id in games and not games[channel_id].is_over():
        await ctx.send("A game is already running here! Type a single letter to guess, or `!stop` to end it.")
        return

    word = get_random_word()
    games[channel_id] = HangmanGame(word)
    game = games[channel_id]

    embed = discord.Embed(
        title="🎮 Hangman Started!",
        description=f"```\n{game.get_ascii()}\n```\n**Word:** `{game.get_display_word()}`\n\n**How to play:** Simply type a single letter in chat (e.g. `e`), or use `!guess <letter>`!",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed)

@bot.command(name="stop")
async def stop_game(ctx):
    channel_id = ctx.channel.id
    if channel_id in games:
        del games[channel_id]
        await ctx.send("Game stopped!")
    else:
        await ctx.send("No active game in this channel.")

@bot.command(name="status")
async def status(ctx):
    channel_id = ctx.channel.id
    if channel_id not in games or games[channel_id].is_over():
        await ctx.send("No active game. Start one with `!hangman`!")
        return

    game = games[channel_id]
    embed = discord.Embed(
        title="📊 Hangman Status",
        description=f"```\n{game.get_ascii()}\n```\n**Word:** `{game.get_display_word()}`\n**Guessed:** `{', '.join(sorted(game.guessed_letters)) or 'None'}`\n**Lives left:** {game.max_attempts - game.wrong_attempts}",
        color=discord.Color.gold()
    )
    await ctx.send(embed=embed)

@bot.command(name="guess")
async def guess_cmd(ctx, letter: str):
    await process_guess(ctx.channel, letter)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    # Process prefix commands (!hangman, !stop, !status)
    await bot.process_commands(message)

    # Ignore prefix commands for raw letter matching
    if message.content.startswith("!"):
        return

    # Auto-read single letter messages in active game channels
    channel_id = message.channel.id
    if channel_id in games and not games[channel_id].is_over():
        text = message.content.strip().lower()
        if len(text) == 1 and text.isalpha():
            await process_guess(message.channel, text)

async def process_guess(channel, letter: str):
    channel_id = channel.id
    if channel_id not in games or games[channel_id].is_over():
        return

    game = games[channel_id]
    letter = letter.lower()

    result = game.guess(letter)
    if result == "already_guessed":
        await channel.send(f"You already guessed `{letter.upper()}`!")
        return

    if game.is_won():
        embed = discord.Embed(
            title="🎉 You Won!",
            description=f"```\n{game.get_ascii()}\n```\n**Word:** `{game.word.upper()}`",
            color=discord.Color.green()
        )
        del games[channel_id]
    elif game.is_lost():
        embed = discord.Embed(
            title="💀 Game Over!",
            description=f"```\n{game.get_ascii()}\n```\n**The word was:** `{game.word.upper()}`",
            color=discord.Color.red()
        )
        del games[channel_id]
    else:
        color = discord.Color.green() if result == "correct" else discord.Color.orange()
        embed = discord.Embed(
            title="Correct!" if result == "correct" else "Wrong guess!",
            description=f"```\n{game.get_ascii()}\n```\n**Word:** `{game.get_display_word()}`\n**Guessed:** `{', '.join(sorted(game.guessed_letters))}`",
            color=color
        )

    await channel.send(embed=embed)

if __name__ == "__main__":
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    token = os.environ.get("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN environment variable not set.")
