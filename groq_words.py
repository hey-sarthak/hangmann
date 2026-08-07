"""
Groq API integration for generating random hangman words.
Uses Groq's OpenAI-compatible chat completions endpoint.
"""

import os
import random
import re
import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

# Local fallback word bank, used if Groq is unreachable or misconfigured
FALLBACK_WORDS = [
    "python", "discord", "elephant", "keyboard", "mountain", "sandwich",
    "guitar", "volcano", "penguin", "umbrella", "asteroid", "chocolate",
    "backpack", "dinosaur", "hospital", "notebook", "rainbow", "spaghetti",
    "telescope", "waterfall", "airplane", "butterfly", "calendar", "diamond",
]

CATEGORIES = [
    "animals", "food", "technology", "sports", "movies", "countries",
    "science", "music", "nature", "everyday objects", "video games", "jobs",
]

_WORD_RE = re.compile(r"^[a-zA-Z]+$")


def _clean(word: str) -> str | None:
    word = word.strip().strip(".\"'").lower()
    if 3 <= len(word) <= 15 and _WORD_RE.match(word):
        return word
    return None


def get_random_word(recent_words: set[str] | None = None) -> tuple[str, str]:
    """
    Returns (word, category). Tries Groq first, falls back to a local list.
    recent_words: optional set of recently-used words to avoid repeats.
    """
    recent_words = recent_words or set()
    category = random.choice(CATEGORIES)

    if GROQ_API_KEY:
        try:
            resp = requests.post(
                GROQ_URL,
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": GROQ_MODEL,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You generate single words for a Hangman game. "
                                "Reply with ONLY the word, lowercase, no punctuation, "
                                "no explanation, no quotes. The word must be a common "
                                "English noun between 4 and 12 letters, no spaces or hyphens."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Give me one random hangman word from the category: "
                                f"{category}. Avoid these already-used words: "
                                f"{', '.join(sorted(recent_words)) or 'none'}."
                            ),
                        },
                    ],
                    "temperature": 1.0,
                    "max_tokens": 10,
                },
                timeout=10,
            )
            resp.raise_for_status()
            raw = resp.json()["choices"][0]["message"]["content"]
            word = _clean(raw)
            if word and word not in recent_words:
                return word, category
        except Exception as e:
            print(f"[groq_words] Groq API failed, falling back: {e}")

    # Fallback path
    choices = [w for w in FALLBACK_WORDS if w not in recent_words] or FALLBACK_WORDS
    return random.choice(choices), "general"
