# app.py — Application Flask principale
# Puissance 4 · Grille 9x9 · 3 modes · 3 IA

import os
import logging
from flask import Flask, render_template, request, jsonify, session

from game import Connect4, RED, YELLOW
import minmax as minmax_ai
import random_ai
from ia import DatabaseAI, build_knowledge_base
import db as database

# ------------------------------------------------------------------ #
#  Configuration                                                        #
# ------------------------------------------------------------------ #
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "puissance4-secret-2024")

# Base de connaissances IA (chargée au démarrage)
_db_ai: DatabaseAI | None = None

# ------------------------------------------------------------------ #
#  Initialisation                                                       #
# ------------------------------------------------------------------ #

def get_db_ai() -> DatabaseAI | None:
    global _db_ai
    if _db_ai is None:
        try:
            conn = database.get_connection()
            kb = build_knowledge_base(conn)
            _db_ai = DatabaseAI(kb)
        except Exception as e:
            logger.warning(f"IA DB non disponible: {e}")
    return _db_ai


@app.before_request
def ensure_db():
    """Initialise la DB au premier appel."""
    pass  # init_db() est appelé au démarrage


# ------------------------------------------------------------------ #
#  Routes                                                               #
# ------------------------------------------------------------------ #

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/new_game", methods=["POST"])
def new_game():
    """Crée une nouvelle partie."""
    data = request.get_json(force=True)
    mode = data.get("mode", "1player")          # "0player", "1player", "2player"
    ai1  = data.get("ai1", "minmax")            # AI du joueur 1 (mode 0player)
    ai2  = data.get("ai2", "minmax")            # AI du joueur 2
    depth = int(data.get("depth", 4))
    human_color = int(data.get("human_color", RED))  # 1player: couleur humain

    game = Connect4()
    session["board"] = game.board_to_str()
    session["mode"] = mode
    session["ai1"] = ai1        # IA pour RED en mode 0p / IA adverse en mode 1p
    session["ai2"] = ai2
    session["depth"] = depth
    session["human_color"] = human_color
    session["game_id"] = None

    # Persister en DB
    try:
        gid = database.create_game(mode, ai1, ai2, depth)
        session["game_id"] = gid
        database.save_state(gid, 0, game.board_to_str())
    except Exception as e:
        logger.warning(f"DB save échoué: {e}")

    return jsonify({"ok": True, "state": game.to_dict()})


@app.route("/api/play", methods=["POST"])
def play():
    """Joue un coup humain."""
    data = request.get_json(force=True)
    col = int(data.get("col", -1))

    grid_str = session.get("board")
    if not grid_str:
        return jsonify({"error": "Pas de partie en cours"}), 400

    game = Connect4.from_str(grid_str)
    mode = session.get("mode", "1player")

    if game.game_over:
        return jsonify({"error": "Partie terminée"}), 400

    # Vérifier que c'est bien au tour de l'humain
    if mode == "1player":
        human_color = session.get("human_color", RED)
        if game.current_player != human_color:
            return jsonify({"error": "C'est le tour de l'IA"}), 400

    if not game.drop_piece(col):
        return jsonify({"error": "Coup invalide"}), 400

    _persist_move(game, col)
    session["board"] = game.board_to_str()

    return jsonify({"ok": True, "state": game.to_dict()})


@app.route("/api/ai_move", methods=["POST"])
def ai_move():
    """L'IA joue son coup."""
    grid_str = session.get("board")
    if not grid_str:
        return jsonify({"error": "Pas de partie en cours"}), 400

    game = Connect4.from_str(grid_str)
    if game.game_over:
        return jsonify({"error": "Partie terminée"}), 400

    mode = session.get("mode", "1player")
    depth = session.get("depth", 4)

    # Déterminer quel type d'IA joue
    if mode == "0player":
        ai_type = session.get("ai1") if game.current_player == RED else session.get("ai2")
    else:  # 1player
        ai_type = session.get("ai2")  # ai2 = IA adverse

    # Calculer les scores de toutes les colonnes pour affichage
    col_scores = _compute_all_scores(game, ai_type, depth)

    col = _compute_ai_move(game, ai_type, depth)
    if col is None:
        return jsonify({"error": "Aucun coup disponible"}), 400

    game.drop_piece(col)
    _persist_move(game, col)
    session["board"] = game.board_to_str()

    return jsonify({"ok": True, "col": col, "state": game.to_dict(), "scores": col_scores})


@app.route("/api/state", methods=["GET"])
def get_state():
    """Retourne l'état courant de la partie."""
    grid_str = session.get("board")
    if not grid_str:
        return jsonify({"error": "Pas de partie"}), 400
    game = Connect4.from_str(grid_str)
    return jsonify(game.to_dict())


@app.route("/api/stats", methods=["GET"])
def stats():
    """Statistiques globales."""
    count = database.get_game_count()
    kb_size = len(get_db_ai().knowledge) if get_db_ai() else 0
    return jsonify({"total_games": count, "kb_states": kb_size})


@app.route("/historique")
def page_historique():
    return render_template("historique.html")


@app.route("/api/historique", methods=["GET"])
def historique():
    """Retourne l'historique de toutes les parties (app_games + games historiques)."""
    source = request.args.get("source", "all")  # all, app, historique
    page   = int(request.args.get("page", 1))
    limit  = 50
    offset = (page - 1) * limit

    try:
        conn = database.get_connection()
        cur  = conn.cursor()
        parties = []

        # ---- Parties jouées via l'appli ----
        if source in ("all", "app"):
            cur.execute("""
                SELECT id, mode, ai1_type, ai2_type, winner, created_at, 'app' as src
                FROM app_games
                ORDER BY created_at DESC
            """)
            for gid, mode, ai1, ai2, winner, created_at, src in cur.fetchall():
                parties.append(_format_party(gid, mode, ai1, ai2, winner, created_at, src))

        # ---- Parties historiques importées ----
        if source in ("all", "historique"):
            cur.execute("""
                SELECT id,
                       CASE mode WHEN 0 THEN 'IA vs IA' WHEN 1 THEN '1 joueur' WHEN 2 THEN '2 joueurs' ELSE 'inconnu' END,
                       premier,
                       joueur_actuel,
                       CASE WHEN is_draw = 1 THEN 0
                            WHEN winner = 'R' THEN 1
                            WHEN winner = 'J' THEN 2
                            ELSE NULL END,
                       created_at,
                       'historique' as src
                FROM games
                ORDER BY created_at DESC
            """)
            for gid, mode, ai1, ai2, winner, created_at, src in cur.fetchall():
                parties.append(_format_party(gid, mode, ai1 or "-", ai2 or "-", winner, created_at, src))

        cur.close()

        total = len(parties)
        parties_page = parties[offset:offset+limit]
        return jsonify({"parties": parties_page, "total": total, "page": page, "limit": limit})

    except Exception as e:
        logger.error(f"Erreur historique: {e}")
        return jsonify({"parties": [], "total": 0, "error": str(e)})


def _format_party(gid, mode, ai1, ai2, winner, created_at, source):
    if winner is None:
        resultat = "⏳ En cours"
    elif winner == 1:
        resultat = "🔴 Rouge gagne"
    elif winner == 2:
        resultat = "🟡 Jaune gagne"
    elif winner == 0:
        resultat = "⚪ Match nul"
    else:
        resultat = "❓"
    return {
        "id":      gid,
        "mode":    mode or "-",
        "ai1":     ai1 or "-",
        "ai2":     ai2 or "-",
        "winner":  winner,
        "resultat": resultat,
        "source":  source,
        "date":    created_at.strftime("%d/%m/%Y %H:%M") if created_at else "-"
    }


# ------------------------------------------------------------------ #
#  Helpers                                                              #
# ------------------------------------------------------------------ #

def _compute_all_scores(game: Connect4, ai_type: str, depth: int) -> dict:
    """Retourne les scores de toutes les colonnes pour affichage."""
    try:
        if ai_type == "random":
            return {}
        elif ai_type == "ia":
            ai = get_db_ai()
            if ai:
                raw = ai.get_all_scores(game)
            else:
                raw = minmax_ai.get_all_scores(game, depth)
        else:
            raw = minmax_ai.get_all_scores(game, depth)
        # Normaliser pour l'affichage : convertir en str keys pour JSON
        return {str(k): v for k, v in raw.items()}
    except Exception as e:
        logger.warning(f"Erreur scores: {e}")
        return {}


def _compute_ai_move(game: Connect4, ai_type: str, depth: int) -> int | None:
    if ai_type == "random":
        return random_ai.get_best_move(game)
    elif ai_type == "ia":
        ai = get_db_ai()
        if ai:
            return ai.get_best_move(game)
        return random_ai.get_best_move(game)
    else:  # minmax (défaut)
        return minmax_ai.get_best_move(game, depth)


def _persist_move(game: Connect4, col: int):
    gid = session.get("game_id")
    if not gid:
        return
    try:
        player = YELLOW if game.current_player != game.current_player else RED  # joueur qui vient de jouer
        # current_player a déjà changé après drop_piece si pas game_over
        played_by = YELLOW if game.current_player == RED and not game.game_over else RED
        # plus simple : déduire depuis ply (impair = rouge, pair = jaune)
        played_by = RED if game.ply % 2 == 1 else YELLOW
        database.save_move(gid, played_by, col, game.ply)
        database.save_state(gid, game.ply, game.board_to_str())
        if game.game_over:
            database.finish_game(gid, game.winner if game.winner else 0)
    except Exception as e:
        logger.warning(f"DB persist échoué: {e}")


# ------------------------------------------------------------------ #
#  Démarrage                                                            #
# ------------------------------------------------------------------ #

def startup():
    logger.info("Démarrage de l'application…")
    try:
        database.init_db()
        logger.info("Base de données initialisée.")
    except Exception as e:
        logger.warning(f"DB non disponible au démarrage: {e}")
    try:
        get_db_ai()
        logger.info("IA chargée.")
    except Exception as e:
        logger.warning(f"IA non chargée: {e}")


with app.app_context():
    startup()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
