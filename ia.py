# ia.py — IA hybride : Base de données + MinMax
# Stratégie :
#   1. Toujours vérifier si un coup gagnant immédiat existe → jouer
#   2. Toujours bloquer une victoire adverse immédiate → bloquer
#   3. Si état connu en DB avec score fiable (≥5 parties) → suivre la DB
#   4. Sinon → MinMax profondeur adaptative

import random
import logging
from game import Connect4, RED, YELLOW, COLS
import minmax as minmax_ai

logger = logging.getLogger(__name__)

# Seuil minimum de parties vues pour faire confiance à la DB
MIN_CONFIDENCE = 5
# Score minimum pour préférer la DB (évite de suivre des coups perdants)
MIN_SCORE = 0.45


def build_knowledge_base(conn) -> dict:
    """
    Construit { grid_str: { col: {'win':n,'loss':n,'draw':n} } }
    depuis les parties terminées de la DB.
    """
    knowledge: dict = {}

    try:
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT id, winner, is_draw FROM games "
                "WHERE status = 'TERMINEE' "
                "AND (lignes = 9 OR lignes IS NULL) "
                "AND (colonnes = 9 OR colonnes IS NULL)"
            )
        except Exception:
            conn.rollback()
            cur.execute("SELECT id, winner, is_draw FROM games WHERE status = 'TERMINEE'")
        games_raw = cur.fetchall()
        cur.close()
    except Exception as e:
        logger.error(f"Erreur lecture games: {e}")
        return knowledge

    game_results = {gid: (winner, is_draw) for gid, winner, is_draw in games_raw}
    if not game_results:
        logger.warning("Aucune partie terminée trouvée.")
        return knowledge
    logger.info(f"Parties terminées: {len(game_results)}")

    all_states = []
    gids = list(game_results.keys())
    for i in range(0, len(gids), 500):
        batch = gids[i:i+500]
        try:
            cur = conn.cursor()
            ph = ','.join(['%s'] * len(batch))
            cur.execute(
                f"SELECT game_id, ply, grid_str FROM states "
                f"WHERE game_id IN ({ph}) ORDER BY game_id, ply",
                batch
            )
            all_states.extend(cur.fetchall())
            cur.close()
        except Exception as e:
            logger.error(f"Erreur states batch {i}: {e}")

    by_game: dict = {}
    for game_id, ply, grid_str in all_states:
        if grid_str:
            by_game.setdefault(game_id, []).append((ply, grid_str))

    nb = 0
    for game_id, plies in by_game.items():
        plies.sort(key=lambda x: x[0])
        if len(plies) < 2:
            continue
        winner_char, is_draw = game_results.get(game_id, (None, 0))
        for i in range(len(plies) - 1):
            curr_grid = plies[i][1]
            next_grid = plies[i+1][1]
            col = _find_column_played(curr_grid, next_grid)
            if col is None:
                continue
            r = curr_grid.count('R')
            j = curr_grid.count('J')
            curr_char = 'R' if r == j else 'J'
            stats = knowledge.setdefault(curr_grid, {}).setdefault(
                col, {'win': 0, 'loss': 0, 'draw': 0}
            )
            if is_draw or winner_char is None:
                stats['draw'] += 1
            elif winner_char == curr_char:
                stats['win'] += 1
            else:
                stats['loss'] += 1
        nb += 1

    logger.info(f"Base de connaissances: {len(knowledge)} états uniques depuis {nb} parties.")
    return knowledge


def _find_column_played(grid_before: str, grid_after: str) -> int | None:
    for i, (b, a) in enumerate(zip(grid_before, grid_after)):
        if b == '.' and a != '.':
            return i % COLS
    return None


class DatabaseAI:
    def __init__(self, knowledge: dict):
        self.knowledge = knowledge

    def get_best_move(self, game: Connect4) -> int | None:
        valid = game.get_valid_columns()
        if not valid:
            return None

        # ── 1. Coup gagnant immédiat ──────────────────────────────────
        for col in valid:
            g = _clone_and_play(game, col)
            if g and g.winner == game.current_player:
                logger.debug(f"IA DB: coup gagnant immédiat col={col}")
                return col

        # ── 2. Bloquer victoire adverse ───────────────────────────────
        opponent = YELLOW if game.current_player == RED else RED
        for col in valid:
            g = _clone_and_play_as(game, col, opponent)
            if g and g.winner == opponent:
                logger.debug(f"IA DB: blocage adverse col={col}")
                return col

        # ── 3. Consulter la base de données ───────────────────────────
        col_stats = self.knowledge.get(game.board_to_str(), {})
        best_col, best_score, best_total = None, -1.0, 0

        for col, stats in col_stats.items():
            col_int = int(col)
            if col_int not in valid:
                continue
            total = stats['win'] + stats['loss'] + stats['draw']
            if total < MIN_CONFIDENCE:
                continue
            score = (stats['win'] + 0.5 * stats['draw']) / total
            if score > best_score or (score == best_score and total > best_total):
                best_score, best_col, best_total = score, col_int, total

        if best_col is not None and best_score >= MIN_SCORE:
            logger.debug(f"IA DB: col={best_col} score={best_score:.2f} n={best_total}")
            return best_col

        # ── 4. Fallback MinMax (profondeur selon stade de la partie) ──
        depth = _adaptive_depth(game)
        logger.debug(f"IA DB: fallback MinMax profondeur={depth}")
        return minmax_ai.get_best_move(game, depth)


    def get_all_scores(self, game) -> dict:
        """Retourne {col: score_normalisé} pour affichage des poids."""
        import math
        valid = game.get_valid_columns()
        if not valid:
            return {}

        scores = {}

        # Vérifier coups gagnants / blocages
        opponent = YELLOW if game.current_player == RED else RED
        for col in valid:
            g = _clone_and_play(game, col)
            if g and g.winner == game.current_player:
                scores[col] = 999999   # coup gagnant
                continue
            g2 = _clone_and_play_as(game, col, opponent)
            if g2 and g2.winner == opponent:
                scores[col] = 500000   # blocage nécessaire
                continue

        # Scores DB
        col_stats = self.knowledge.get(game.board_to_str(), {})
        for col in valid:
            if col in scores:
                continue
            stats = col_stats.get(col, col_stats.get(str(col), None))
            if stats:
                total = stats['win'] + stats['loss'] + stats['draw']
                if total >= 1:
                    score = (stats['win'] + 0.5 * stats['draw']) / total
                    scores[col] = round(score * 100)   # 0-100
                    continue
            # Fallback MinMax score
            mm_scores = minmax_ai.get_all_scores(game, _adaptive_depth(game))
            for c, s in mm_scores.items():
                if c not in scores:
                    scores[c] = s

        return scores


def _adaptive_depth(game: Connect4) -> int:
    """Profondeur MinMax adaptée au stade de la partie."""
    ply = game.ply
    if ply < 10:
        return 3   # début : rapide
    elif ply < 30:
        return 4   # milieu
    else:
        return 5   # fin : plus de réflexion


def _clone_and_play(game: Connect4, col: int):
    """Clone la partie et joue col avec le joueur courant."""
    g = Connect4.from_str(game.board_to_str())
    if g.drop_piece(col):
        return g
    return None


def _clone_and_play_as(game: Connect4, col: int, player: int):
    """Clone et joue comme si c'était le tour de player."""
    g = Connect4.from_str(game.board_to_str())
    g.current_player = player
    if g.drop_piece(col):
        return g
    return None
