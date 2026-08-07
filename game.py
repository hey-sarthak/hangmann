"""
Core Hangman game state machine. No Discord-specific code lives here,
so it's easy to test in isolation.
"""

HANGMAN_STAGES = [
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========```",
]
MAX_WRONG = len(HANGMAN_STAGES) - 1


class HangmanGame:
    def __init__(self, word: str, category: str, starter_id: int):
        self.word = word.lower()
        self.category = category
        self.starter_id = starter_id
        self.guessed_letters: set[str] = set()
        self.wrong_letters: set[str] = set()
        self.finished = False
        self.won = False

    @property
    def wrong_count(self) -> int:
        return len(self.wrong_letters)

    def guess(self, letter: str) -> str:
        """Apply a guess, return a status string: 'already', 'correct', 'wrong'."""
        letter = letter.lower()
        if letter in self.guessed_letters or letter in self.wrong_letters:
            return "already"

        if letter in self.word:
            self.guessed_letters.add(letter)
            if self.is_word_complete():
                self.finished = True
                self.won = True
            return "correct"
        else:
            self.wrong_letters.add(letter)
            if self.wrong_count >= MAX_WRONG:
                self.finished = True
                self.won = False
            return "wrong"

    def is_word_complete(self) -> bool:
        return all(c in self.guessed_letters for c in self.word if c.isalpha())

    def display_word(self) -> str:
        return " ".join(c if c in self.guessed_letters else "\\_" for c in self.word)

    def gallows(self) -> str:
        return HANGMAN_STAGES[min(self.wrong_count, MAX_WRONG)]

    def remaining_guesses(self) -> int:
        return MAX_WRONG - self.wrong_count
