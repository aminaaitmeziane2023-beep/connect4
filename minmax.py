# minmax.py — IA MinMax avec élagage alpha-bêta
# Profondeur configurable de 0 à 6

import math
from game import Connect4, RED, YELLOW, EMPTY, ROWS, COLS, WIN_LENGTH


# ------------------------------------------------------------------ #
#  Évaluation heuristique                                               #
# ------------------------------------------------------------------ #

def _score_window(window, player):
    opp = YELLOW if player == RED else RED
    score = 0
    p_count = window.count(player)
    e_count = window.count(EMPTY)
    o_count = window.count(opp)

    if p_count == 4:
        score += 100
    elif p_count == 3 and e_count == 1:
        score += 10
    elif p_count == 2 and e_count == 2:
        score += 2
    if o_count == 3 and e_count == 1:
        score -= 80   # était -8 : trop faible, l'IA ignorait les menaces à 3 pions
    if o_count == 2 and e_count == 2:
        score -= 3
    return score


def evaluate_board(game, player):
    """Évalue le plateau pour le joueur donné."""
    score = 0
    b = game.board

    # Préférence centrale (colonnes du milieu)
    for col in range(COLS):
        dist = abs(col - COLS // 2)
        weight = max(0, COLS // 2 - dist + 1)
        for row in range(ROWS):
            if b[row][col] == player:
                score += weight

    # Horizontal
    for r in range(ROWS):
        for c in range(COLS - WIN_LENGTH + 1):
            window = [b[r][c + i] for i in range(WIN_LENGTH)]
            score += _score_window(window, player)

    # Vertical
    for c in range(COLS):
        for r in range(ROWS - WIN_LENGTH + 1):
            window = [b[r + i][c] for i in range(WIN_LENGTH)]
            score += _score_window(window, player)

    # Diagonale montante
    for r in range(ROWS - WIN_LENGTH + 1):
        for c in range(COLS - WIN_LENGTH + 1):
            window = [b[r + i][c + i] for i in range(WIN_LENGTH)]
            score += _score_window(window, player)

    # Diagonale descendante
    for r in range(WIN_LENGTH - 1, ROWS):
        for c in range(COLS - WIN_LENGTH + 1):
            window = [b[r - i][c + i] for i in range(WIN_LENGTH)]
            score += _score_window(window, player)

    return score


# ------------------------------------------------------------------ #
#  Algorithme MinMax                                                    #
# ------------------------------------------------------------------ #

def minimax(game, depth, alpha, beta, maximizing, ai_player):
    opp = YELLOW if ai_player == RED else RED
    valid = game.get_valid_columns()

    if game.game_over:
        if game.winner == ai_player:
            return None, 10_000_000 + depth   # victoire rapide = mieux
        elif game.winner == opp:
            return None, -10_000_000 - depth
        else:
            return None, 0  # nul

    if depth == 0:
        return None, evaluate_board(game, ai_player)

    if not valid:
        return None, 0

    # Ordonner les colonnes: centre d'abord (améliore l'élagage)
    center = COLS // 2
    ordered = sorted(valid, key=lambda c: abs(c - center))

    best_col = ordered[0]

    if maximizing:
        value = -math.inf
        for col in ordered:
            g2 = game.copy()
            g2.drop_piece(col)
            _, score = minimax(g2, depth - 1, alpha, beta, False, ai_player)
            if score > value:
                value = score
                best_col = col
            alpha = max(alpha, value)
            if alpha >= beta:
                break
        return best_col, value
    else:
        value = math.inf
        for col in ordered:
            g2 = game.copy()
            g2.drop_piece(col)
            _, score = minimax(g2, depth - 1, alpha, beta, True, ai_player)
            if score < value:
                value = score
                best_col = col
            beta = min(beta, value)
            if alpha >= beta:
                break
        return best_col, value


def get_best_move(game, depth=4):
    """Retourne la meilleure colonne pour le joueur courant.
    depth : profondeur de recherche (0 = aucune, 6 = max recommandé).
    """
    if depth < 0:
        depth = 0
    if depth > 6:
        depth = 6

    valid = game.get_valid_columns()
    if not valid:
        return None

    if depth == 0:
        # Depth 0 : évaluation pure sans récursion
        ai_player = game.current_player
        best_col = valid[0]
        best_score = -math.inf
        for col in valid:
            g2 = game.copy()
            g2.drop_piece(col)
            if g2.game_over and g2.winner == ai_player:
                return col  # victoire immédiate
            s = evaluate_board(g2, ai_player)
            if s > best_score:
                best_score = s
                best_col = col
        return best_col

    col, _ = minimax(game, depth, -math.inf, math.inf, True, game.current_player)
    return col


def get_all_scores(game, depth=4):
    """Retourne un dict {col: score} pour toutes les colonnes valides."""
    import math
    valid = game.get_valid_columns()
    if not valid:
        return {}

    ai_player = game.current_player
    scores = {}

    if depth == 0:
        for col in valid:
            g2 = game.copy()
            g2.drop_piece(col)
            if g2.game_over and g2.winner == ai_player:
                scores[col] = 10_000_000
            else:
                scores[col] = evaluate_board(g2, ai_player)
        return scores

    for col in valid:
        g2 = game.copy()
        g2.drop_piece(col)
        if g2.game_over and g2.winner == ai_player:
            scores[col] = 10_000_000
            continue
        _, score = minimax(g2, depth - 1, -math.inf, math.inf, False, ai_player)
        scores[col] = score

    return scores
