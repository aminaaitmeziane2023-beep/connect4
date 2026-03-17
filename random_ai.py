# random_ai.py — IA Aléatoire
import random
from game import Connect4


def get_best_move(game: Connect4):
    """Choisit une colonne valide au hasard."""
    valid = game.get_valid_columns()
    if not valid:
        return None
    return random.choice(valid)
