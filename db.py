# db.py — Connexion PostgreSQL et persistance des nouvelles parties
# Les nouvelles parties sont stockées dans des tables "app_*"
# pour ne pas interférer avec les données historiques importées.

import os
import logging
import psycopg2

logger = logging.getLogger(__name__)
_conn = None


def get_connection():
    global _conn
    if _conn is None or _conn.closed:
        _conn = _create_connection()
    return _conn


def _create_connection():
    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL non définie.")
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(db_url, sslmode="require")
    conn.autocommit = True
    logger.info("Connexion PostgreSQL établie.")
    return conn


def init_db():
    """Crée les tables app_* si elles n'existent pas."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_games (
            id         SERIAL PRIMARY KEY,
            mode       VARCHAR(20),
            ai1_type   VARCHAR(20),
            ai2_type   VARCHAR(20),
            depth      INTEGER DEFAULT 4,
            winner     INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS app_moves (
            id         SERIAL PRIMARY KEY,
            game_id    INTEGER REFERENCES app_games(id) ON DELETE CASCADE,
            player     INTEGER,
            col_played INTEGER,
            ply        INTEGER
        );
        CREATE TABLE IF NOT EXISTS app_states (
            id         SERIAL PRIMARY KEY,
            game_id    INTEGER REFERENCES app_games(id) ON DELETE CASCADE,
            ply        INTEGER,
            grid_str   VARCHAR(81)
        );
    """)
    cur.close()
    logger.info("Tables app_* initialisées.")


def create_game(mode, ai1_type=None, ai2_type=None, depth=4) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_games (mode, ai1_type, ai2_type, depth) VALUES (%s,%s,%s,%s) RETURNING id",
        (mode, ai1_type, ai2_type, depth)
    )
    gid = cur.fetchone()[0]
    cur.close()
    return gid


def save_move(game_id: int, player: int, col: int, ply: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_moves (game_id, player, col_played, ply) VALUES (%s,%s,%s,%s)",
        (game_id, player, col, ply)
    )
    cur.close()


def save_state(game_id: int, ply: int, grid_str: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_states (game_id, ply, grid_str) VALUES (%s,%s,%s)",
        (game_id, ply, grid_str)
    )
    cur.close()


def finish_game(game_id: int, winner: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE app_games SET winner=%s WHERE id=%s", (winner, game_id))
    cur.close()


def get_game_count() -> int:
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Compter les deux sources
        cur.execute("SELECT (SELECT COUNT(*) FROM games) + (SELECT COUNT(*) FROM app_games)")
        count = cur.fetchone()[0]
        cur.close()
        return count
    except Exception:
        try:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM app_games")
            count = cur.fetchone()[0]
            cur.close()
            return count
        except Exception:
            return 0
