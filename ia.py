# ia.py — IA par apprentissage depuis la base de données
# Utilise les tables games (winner, is_draw) et states (grid_str).

import random
import logging
from game import Connect4, RED, YELLOW, COLS

logger = logging.getLogger(__name__)


def build_knowledge_base(conn) -> dict:
    """
    Construit { grid_str: { col: {'win':n,'loss':n,'draw':n} } }
    depuis les parties terminées de la DB.
    """
    knowledge: dict = {}

    # 1. Récupérer les résultats des parties terminées
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

    # 2. Récupérer les états de ces parties (par batch de 500 pour éviter les timeouts)
    all_states = []
    gids = list(game_results.keys())
    batch_size = 500
    for i in range(0, len(gids), batch_size):
        batch = gids[i:i+batch_size]
        try:
            cur = conn.cursor()
            placeholder = ','.join(['%s'] * len(batch))
            cur.execute(
                f"SELECT game_id, ply, grid_str FROM states "
                f"WHERE game_id IN ({placeholder}) ORDER BY game_id, ply",
                batch
            )
            all_states.extend(cur.fetchall())
            cur.close()
        except Exception as e:
            logger.error(f"Erreur lecture states batch {i}: {e}")

    # 3. Grouper par partie
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

        col_stats = self.knowledge.get(game.board_to_str(), {})
        best_col, best_score, best_total = None, -1.0, 0

        for col, stats in col_stats.items():
            col_int = int(col)
            if col_int not in valid:
                continue
            total = stats['win'] + stats['loss'] + stats['draw']
            if total == 0:
                continue
            score = (stats['win'] + 0.5 * stats['draw']) / total
            if score > best_score or (score == best_score and total > best_total):
                best_score, best_col, best_total = score, col_int, total

        if best_col is not None:
            logger.debug(f"IA DB col={best_col} score={best_score:.2f} n={best_total}")
            return best_col

        return random.choice(valid)
