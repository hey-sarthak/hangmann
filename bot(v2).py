import discord
import asyncio
import random
import logging
import os
import aiohttp
import threading
from datetime import datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv
from flask import Flask

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

TOKEN = os.getenv("DISCORD_TOKEN")

GUILD_ID = int(os.getenv("GUILD_ID", "0"))
VOICE_CHANNEL_ID = int(os.getenv("VOICE_CHANNEL_ID", "0"))
TEXT_CHANNEL_ID = int(os.getenv("TEXT_CHANNEL_ID", "0"))

INTERVAL = int(os.getenv("INTERVAL_MINUTES", "4"))
SONG_REFRESH_INTERVAL = 10

LASTFM_KEY = os.getenv("LASTFM_API_KEY")

# Hosting platforms normally provide PORT automatically
PORT = int(os.getenv("PORT", "10000"))

# ============================================================
# LOGGING
# ============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(message)s"
)

logger = logging.getLogger(__name__)

# Don't print Flask request logs every time the health URL
# gets pinged.
logging.getLogger("werkzeug").setLevel(logging.ERROR)


# ============================================================
# FLASK HEALTH SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
@app.route("/health")
def health():
    return "OK", 200


def run_health_server():

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


# ============================================================
# RADIO BOT
# ============================================================

class RadioBot:

    def __init__(self):

        self.bot = discord.Client(intents=None)

        self.voice_client = None

        self.songs = []

        self.last_update = None
        self.song_count = 0

        self.is_connected = False
        self._joining = False

        # Register events
        self.bot.event(self.on_ready)
        self.bot.event(self.on_message)
        self.bot.event(self.on_voice_state_update)

    # ========================================================
    # NORMAL SONG FETCHING
    # ========================================================

    async def fetch_songs_from_internet(self):

        songs = []

        # ----------------------------------------------------
        # DEEZER
        # ----------------------------------------------------

        try:

            async with aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            ) as session:

                url = (
                    "https://api.deezer.com/"
                    "playlist/3155776842/tracks"
                )

                async with session.get(
                    url,
                    timeout=10
                ) as response:

                    if response.status == 200:

                        data = await response.json()

                        for track in data.get(
                            "data",
                            []
                        )[:30]:

                            artist = track.get(
                                "artist",
                                {}
                            ).get(
                                "name",
                                ""
                            )

                            title = track.get(
                                "title",
                                ""
                            )

                            if title and artist:

                                songs.append(
                                    f"{title} {artist}"
                                )

                        logger.info(
                            f"Deezer: {len(songs)} songs"
                        )

        except Exception as e:

            logger.warning(
                f"Deezer API failed: {e}"
            )

        # ----------------------------------------------------
        # APPLE MUSIC / ITUNES
        # ----------------------------------------------------

        try:

            async with aiohttp.ClientSession() as session:

                url = (
                    "https://itunes.apple.com/"
                    "search?term=popular"
                    "&media=music"
                    "&entity=song"
                    "&limit=50"
                )

                async with session.get(
                    url,
                    timeout=10
                ) as response:

                    if response.status == 200:

                        data = await response.json()

                        for item in data.get(
                            "results",
                            []
                        ):

                            title = item.get(
                                "trackName",
                                ""
                            )

                            artist = item.get(
                                "artistName",
                                ""
                            )

                            if title and artist:

                                songs.append(
                                    f"{title} {artist}"
                                )

                        logger.info(
                            "Apple/iTunes songs fetched"
                        )

        except Exception as e:

            logger.warning(
                f"Apple API failed: {e}"
            )

        # ----------------------------------------------------
        # LAST.FM
        # ----------------------------------------------------

        if LASTFM_KEY:

            try:

                async with aiohttp.ClientSession() as session:

                    url = (
                        "https://ws.audioscrobbler.com/2.0/"
                        "?method=chart.gettoptracks"
                        f"&api_key={LASTFM_KEY}"
                        "&format=json"
                        "&limit=50"
                    )

                    async with session.get(
                        url,
                        timeout=10
                    ) as response:

                        if response.status == 200:

                            data = await response.json()

                            for track in data.get(
                                "tracks",
                                {}
                            ).get(
                                "track",
                                []
                            ):

                                title = track.get(
                                    "name",
                                    ""
                                )

                                artist = track.get(
                                    "artist",
                                    {}
                                ).get(
                                    "name",
                                    ""
                                )

                                if title and artist:

                                    songs.append(
                                        f"{title} {artist}"
                                    )

                            logger.info(
                                "Last.fm songs fetched"
                            )

            except Exception as e:

                logger.warning(
                    f"Last.fm API failed: {e}"
                )

        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        songs = list(
            dict.fromkeys(songs)
        )

        # ----------------------------------------------------
        # FALLBACK
        # ----------------------------------------------------

        if len(songs) < 20:

            songs = self.get_fallback_songs()

        elif len(songs) < 50:

            songs.extend(
                self.get_fallback_songs()
            )

            songs = list(
                dict.fromkeys(songs)
            )

        return songs[:200]

    # ========================================================
    # GENRE SONG FETCHER
    # ========================================================

    async def fetch_genre_songs(self, genre):

        songs = []

        # ====================================================
        # DEEZER
        # ====================================================

        try:

            async with aiohttp.ClientSession(
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            ) as session:

                search_term = quote_plus(
                    genre
                )

                url = (
                    "https://api.deezer.com/search"
                    f"?q={search_term}"
                    "&limit=50"
                )

                async with session.get(
                    url,
                    timeout=10
                ) as response:

                    if response.status == 200:

                        data = await response.json()

                        for track in data.get(
                            "data",
                            []
                        ):

                            title = track.get(
                                "title",
                                ""
                            )

                            artist = track.get(
                                "artist",
                                {}
                            ).get(
                                "name",
                                ""
                            )

                            if title and artist:

                                songs.append(
                                    f"{title} {artist}"
                                )

                        logger.info(
                            f"Deezer genre '{genre}': "
                            f"{len(songs)} results"
                        )

        except Exception as e:

            logger.warning(
                f"Deezer genre search failed: {e}"
            )

        # ====================================================
        # APPLE / ITUNES
        # ====================================================

        try:

            async with aiohttp.ClientSession() as session:

                search_term = quote_plus(
                    genre
                )

                url = (
                    "https://itunes.apple.com/"
                    f"search?term={search_term}"
                    "&media=music"
                    "&entity=song"
                    "&limit=50"
                )

                async with session.get(
                    url,
                    timeout=10
                ) as response:

                    if response.status == 200:

                        data = await response.json()

                        for item in data.get(
                            "results",
                            []
                        ):

                            title = item.get(
                                "trackName",
                                ""
                            )

                            artist = item.get(
                                "artistName",
                                ""
                            )

                            if title and artist:

                                songs.append(
                                    f"{title} {artist}"
                                )

                        logger.info(
                            f"Apple genre '{genre}' "
                            f"search completed"
                        )

        except Exception as e:

            logger.warning(
                f"Apple genre search failed: {e}"
            )

        # ====================================================
        # LAST.FM
        # ====================================================

        if LASTFM_KEY:

            try:

                async with aiohttp.ClientSession() as session:

                    search_term = quote_plus(
                        genre
                    )

                    url = (
                        "https://ws.audioscrobbler.com/2.0/"
                        "?method=tag.gettoptracks"
                        f"&tag={search_term}"
                        f"&api_key={LASTFM_KEY}"
                        "&format=json"
                        "&limit=50"
                    )

                    async with session.get(
                        url,
                        timeout=10
                    ) as response:

                        if response.status == 200:

                            data = await response.json()

                            for track in data.get(
                                "tracks",
                                {}
                            ).get(
                                "track",
                                []
                            ):

                                title = track.get(
                                    "name",
                                    ""
                                )

                                artist = track.get(
                                    "artist",
                                    {}
                                ).get(
                                    "name",
                                    ""
                                )

                                if title and artist:

                                    songs.append(
                                        f"{title} {artist}"
                                    )

                            logger.info(
                                f"Last.fm genre '{genre}' "
                                f"search completed"
                            )

            except Exception as e:

                logger.warning(
                    f"Last.fm genre search failed: {e}"
                )

        # ====================================================
        # CLEAN RESULTS
        # ====================================================

        cleaned = []

        seen = set()

        for song in songs:

            normalized = (
                song.lower()
                .replace("-", "")
                .strip()
            )

            if normalized not in seen:

                seen.add(normalized)

                cleaned.append(song)

        return cleaned[:150]

    # ========================================================
    # FALLBACK SONGS
    # ========================================================

    def get_fallback_songs(self):

        return [

            "Blinding Lights The Weeknd",
            "Save Your Tears The Weeknd",
            "Levitating Dua Lipa",
            "Positions Ariana Grande",
            "Mood 24kGoldn",
            "drivers license Olivia Rodrigo",
            "Montero Lil Nas X",
            "Kiss Me More Doja Cat",
            "good 4 u Olivia Rodrigo",
            "Butter BTS",
            "Peaches Justin Bieber",
            "Stay The Kid LAROI",
            "Industry Baby Lil Nas X",
            "Bad Habits Ed Sheeran",
            "Beggin Maneskin",
            "Shivers Ed Sheeran",
            "Cold Heart Elton John",
            "Easy On Me Adele",
            "Heat Waves Glass Animals",
            "As It Was Harry Styles",
            "About Damn Time Lizzo",
            "Break My Soul Beyonce",
            "Unholy Sam Smith",
            "Anti-Hero Taylor Swift",
            "Kill Bill SZA",
            "Flowers Miley Cyrus",
            "Die For You The Weeknd",
            "Creepin Metro Boomin",
            "Lavender Haze Taylor Swift",
            "Late Night Talking Harry Styles",
            "Watermelon Sugar Harry Styles",
            "Adore You Harry Styles",
            "Falling Harry Styles",
            "Sign of the Times Harry Styles",
            "Golden Harry Styles",
            "Steve Lacy Bad Habit",
            "Imagine Dragons Enemy",
            "Imagine Dragons Bones",
            "Imagine Dragons Sharks",
            "Imagine Dragons Wrecked",
            "Imagine Dragons Follow You",
            "Imagine Dragons Natural",
            "Imagine Dragons Radioactive",
            "Imagine Dragons Demons",
            "Imagine Dragons Thunder",
            "Imagine Dragons Whatever It Takes",
            "Imagine Dragons Believer",
            "Imagine Dragons Warriors",
            "Imagine Dragons It's Time",
            "Imagine Dragons On Top Of The World",
            "Imagine Dragons I Bet My Life",
            "Imagine Dragons Shots",
            "Imagine Dragons Gold",
            "Imagine Dragons Smoke And Mirrors",
            "Imagine Dragons I'm So Sorry",
            "Imagine Dragons Dream",
            "Imagine Dragons Hopeless Opus",
            "Imagine Dragons The Fall",
            "Imagine Dragons Polaroid",
            "Imagine Dragons Friction",
            "Imagine Dragons Release",
            "Imagine Dragons Cha-Ching",
            "Imagine Dragons Who We Are",
            "Imagine Dragons Battle Cry",
            "Imagine Dragons Monster",
            "Imagine Dragons Roots",
            "Imagine Dragons Not Today",
            "Imagine Dragons Levitate",
            "Imagine Dragons Real Life",
            "Imagine Dragons Burn Out",
            "Imagine Dragons Machine",
            "Imagine Dragons Digital",
            "Imagine Dragons Bullet In A Gun",
            "Imagine Dragons Only",
            "Imagine Dragons Zero",
            "Imagine Dragons Walking The Wire",
            "Imagine Dragons Rise Up",
            "Imagine Dragons Yesterday",
            "Imagine Dragons Mouth Of The River",
            "Imagine Dragons Start Over",
            "Imagine Dragons Dancing In The Dark"
        ]

    # ========================================================
    # UPDATE NORMAL SONGS
    # ========================================================

    async def update_songs(self):

        logger.info(
            "🔄 Refreshing songs..."
        )

        self.songs = (
            await self.fetch_songs_from_internet()
        )

        self.last_update = datetime.now()

        self.song_count += 1

        logger.info(
            f"📋 Loaded {len(self.songs)} songs "
            f"(Update #{self.song_count})"
        )

    # ========================================================
    # DISCORD READY
    # ========================================================

    async def on_ready(self):

        logger.info(
            f"✅ Logged in as {self.bot.user.name}"
        )

        logger.info(
            f"🎵 Refreshing songs every "
            f"{SONG_REFRESH_INTERVAL} minutes"
        )

        logger.info(
            f"🎵 Sending command every "
            f"{INTERVAL} minutes"
        )

        await self.update_songs()

        asyncio.create_task(
            self.main_loop()
        )

        asyncio.create_task(
            self.song_refresh_loop()
        )

        asyncio.create_task(
            self.keep_voice_alive()
        )

    # ========================================================
    # MESSAGE COMMANDS
    # ========================================================

    async def on_message(self, message):

        if message.author.id == self.bot.user.id:
            return

        content = (
            message.content
            .lower()
            .strip()
        )

        # ====================================================
        # GENRE COMMANDS
        # ====================================================

        genre_commands = {

            "!punjabi": "punjabi",

            "!hindi": "hindi",

            "!bollywood": "bollywood",

            "!english": "english",

            "!pop": "pop",

            "!hiphop": "hip hop",

            "!rap": "rap",

            "!rock": "rock",

            "!lofi": "lofi",

            "!sad": "sad",

            "!romantic": "romantic",

            "!love": "love",

            "!party": "party",

            "!chill": "chill",

            "!workout": "workout",

            "!phonk": "phonk",

            "!kpop": "k-pop",

            "!tamil": "tamil",

            "!telugu": "telugu",

            "!bhojpuri": "bhojpuri",

            "!marathi": "marathi",

            "!bengali": "bengali",

            "!punjabisongs": "punjabi"

        }

        # ----------------------------------------------------
        # GENRE REQUEST
        # ----------------------------------------------------

        if content in genre_commands:

            genre = genre_commands[content]

            await message.channel.send(
                f"🔎 Finding **{genre}** songs..."
            )

            songs = await self.fetch_genre_songs(
                genre
            )

            if not songs:

                await message.channel.send(
                    f"❌ Couldn't find any "
                    f"**{genre}** songs."
                )

                return

            song = random.choice(songs)

            music_channel = self.bot.get_channel(
                TEXT_CHANNEL_ID
            )

            if not music_channel:

                await message.channel.send(
                    "❌ Music channel not found."
                )

                return

            await music_channel.send(
                f"-p {song}"
            )

            await message.channel.send(
                f"🎵 Playing **{song}**"
            )

            return

        # ====================================================
        # RANDOM
        # ====================================================

        if content == "!random":

            all_genres = [
                "punjabi",
                "hindi",
                "bollywood",
                "english",
                "pop",
                "hip hop",
                "rap",
                "rock",
                "lofi",
                "sad",
                "romantic",
                "party",
                "chill",
                "phonk",
                "k-pop",
                "tamil",
                "telugu"
            ]

            genre = random.choice(
                all_genres
            )

            await message.channel.send(
                f"🎲 Random genre: **{genre}**\n"
                f"🔎 Finding a song..."
            )

            songs = await self.fetch_genre_songs(
                genre
            )

            if not songs:

                await message.channel.send(
                    "❌ Couldn't find a song."
                )

                return

            song = random.choice(songs)

            music_channel = self.bot.get_channel(
                TEXT_CHANNEL_ID
            )

            if music_channel:

                await music_channel.send(
                    f"-p {song}"
                )

                await message.channel.send(
                    f"🎵 Playing **{song}**"
                )

            return

        # ====================================================
        # SONG LIST
        # ====================================================

        if content == "!songs":

            await message.channel.send(
                f"📋 Loaded {len(self.songs)} songs "
                f"(Updated "
                f"{self.last_update.strftime('%H:%M') "
                f"if self.last_update else 'Never'})"
            )

            return

        # ====================================================
        # REFRESH
        # ====================================================

        if content == "!refresh":

            await self.update_songs()

            await message.channel.send(
                f"✅ Refreshed! "
                f"Loaded {len(self.songs)} songs"
            )

            return

        # ====================================================
        # STATUS
        # ====================================================

        if content == "!status":

            connected = (
                self.voice_client
                and self.voice_client.is_connected()
            )

            status = (
                "✅ Connected"
                if connected
                else "❌ Disconnected"
            )

            await message.channel.send(
                f"🎵 **Radio Status**\n"
                f"📋 Songs: {len(self.songs)}\n"
                f"🔄 Last update: "
                f"{self.last_update.strftime('%H:%M:%S') "
                f"if self.last_update else 'Never'}\n"
                f"🔊 Voice: {status}\n"
                f"⏰ Command interval: "
                f"{INTERVAL} minutes"
            )

            return

        # ====================================================
        # HELP
        # ====================================================

        if content == "!helpgenre":

            await message.channel.send(
                "**🎵 Genre Commands**\n\n"
                "`!punjabi`\n"
                "`!hindi`\n"
                "`!bollywood`\n"
                "`!english`\n"
                "`!pop`\n"
                "`!hiphop`\n"
                "`!rap`\n"
                "`!rock`\n"
                "`!lofi`\n"
                "`!sad`\n"
                "`!romantic`\n"
                "`!party`\n"
                "`!chill`\n"
                "`!workout`\n"
                "`!phonk`\n"
                "`!kpop`\n"
                "`!tamil`\n"
                "`!telugu`\n"
                "`!bhojpuri`\n"
                "`!marathi`\n"
                "`!bengali`\n"
                "`!random`"
            )

            return

    # ========================================================
    # VOICE STATE
    # ========================================================

    async def on_voice_state_update(
        self,
        member,
        before,
        after
    ):

        if member.id != self.bot.user.id:
            return

        if after.channel is None:

            logger.warning(
                "🔇 Disconnected from voice channel"
            )

            self.voice_client = None
            self.is_connected = False

        elif before.channel != after.channel:

            logger.info(
                f"🔄 Moved to {after.channel.name}"
            )

            if self.bot.voice_clients:

                self.voice_client = (
                    self.bot.voice_clients[0]
                )

                self.is_connected = True

    # ========================================================
    # KEEP VOICE ALIVE
    # ========================================================

    async def keep_voice_alive(self):

        while True:

            await asyncio.sleep(30)

            if (
                self.voice_client is None
                or not self.voice_client.is_connected()
            ):

                logger.warning(
                    "⚠️ Voice connection lost! "
                    "Attempting to reconnect..."
                )

                await self.join_voice()

    # ========================================================
    # SONG REFRESH LOOP
    # ========================================================

    async def song_refresh_loop(self):

        while True:

            await asyncio.sleep(
                SONG_REFRESH_INTERVAL * 60
            )

            await self.update_songs()

    # ========================================================
    # MAIN LOOP
    # ========================================================

    async def main_loop(self):

        logger.info(
            "🔄 Bot is live!"
        )

        while True:

            try:

                if (
                    self.voice_client is None
                    or not self.voice_client.is_connected()
                ):

                    await self.join_voice()

                await self.send_play_command()

                logger.info(
                    f"⏰ Next command in "
                    f"{INTERVAL} minutes..."
                )

                await asyncio.sleep(
                    INTERVAL * 60
                )

            except Exception as e:

                logger.error(
                    f"❌ Main loop error: {e}"
                )

                await asyncio.sleep(300)

    # ========================================================
    # JOIN VOICE
    # ========================================================

    async def join_voice(self):

        if self._joining:
            return

        self._joining = True

        try:

            guild = self.bot.get_guild(
                GUILD_ID
            )

            if not guild:

                logger.error(
                    "❌ Guild not found!"
                )

                return

            channel = guild.get_channel(
                VOICE_CHANNEL_ID
            )

            if not channel:

                logger.error(
                    "❌ Voice channel not found!"
                )

                return

            # Already connected
            if (
                self.voice_client
                and self.voice_client.is_connected()
            ):

                if (
                    self.voice_client.channel.id
                    != VOICE_CHANNEL_ID
                ):

                    await self.voice_client.move_to(
                        channel
                    )

                self.is_connected = True

                return

            # Remove stale connection
            if self.voice_client:

                try:

                    await self.voice_client.disconnect()

                except Exception:
                    pass

                self.voice_client = None

            logger.info(
                f"🔊 Connecting to "
                f"{channel.name}..."
            )

            self.voice_client = (
                await channel.connect()
            )

            self.is_connected = True

            logger.info(
                f"✅ Connected to "
                f"{channel.name}"
            )

        except discord.ClientException as e:

            logger.error(
                f"❌ Discord voice error: {e}"
            )

            self.voice_client = None
            self.is_connected = False

        except Exception as e:

            logger.error(
                f"❌ Voice join error: {e}"
            )

            self.voice_client = None
            self.is_connected = False

        finally:

            self._joining = False

    # ========================================================
    # SEND PLAY COMMAND
    # ========================================================

    async def send_play_command(self):

        try:

            if not self.songs:

                await self.update_songs()

            if not self.songs:

                self.songs = (
                    self.get_fallback_songs()
                )

            song = random.choice(
                self.songs
            )

            channel = self.bot.get_channel(
                TEXT_CHANNEL_ID
            )

            if not channel:

                logger.error(
                    "❌ Text channel not found!"
                )

                return

            await channel.send(
                f"-p {song}"
            )

            logger.info(
                f"🎵 Sent command: -p {song}"
            )

        except Exception as e:

            logger.error(
                f"❌ Command error: {e}"
            )

    # ========================================================
    # RUN
    # ========================================================

    def run(self):

        try:

            self.bot.run(TOKEN)

        except discord.LoginFailure:

            logger.error(
                "❌ Invalid token!"
            )

        except KeyboardInterrupt:

            logger.info(
                "⏹️ Bot stopped"
            )

        except Exception as e:

            logger.error(
                f"❌ Error: {e}"
            )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    if not TOKEN:

        print(
            "❌ Error: DISCORD_TOKEN "
            "not set in .env file!"
        )

        raise SystemExit(1)

    if not all([
        GUILD_ID,
        VOICE_CHANNEL_ID,
        TEXT_CHANNEL_ID
    ]):

        print(
            "❌ Error: Check "
            "GUILD_ID, "
            "VOICE_CHANNEL_ID, "
            "TEXT_CHANNEL_ID "
            "in .env"
        )

        raise SystemExit(1)

    # Start Flask health server
    threading.Thread(
        target=run_health_server,
        daemon=True
    ).start()

    # Start Discord bot
    bot = RadioBot()
    bot.run()
