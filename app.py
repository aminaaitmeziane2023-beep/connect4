# app.py — Application Flask principale
# Puissance 4 · Grille 9x9 · 3 modes · 3 IA

import os
import logging
from flask import Flask, render_template, request, jsonify

from game import Connect4, RED, YELLOW
import minmax as minmax_ai
import random_ai
from ia import DatabaseAI, build_knowledge_base
import db as database
from opening_book import get_opening_move

# État des parties en mémoire, indexé par tab_id
# { tab_id: { board, mode, ai1, ai2, depth, human_color, game_id, history } }
_games: dict = {}

def get_game(tab_id: str) -> dict:
    return _games.get(tab_id, {})

def set_game(tab_id: str, data: dict):
    _games[tab_id] = data

def get_tab_id() -> str:
    data = request.get_json(force=True, silent=True) or {}
    return str(data.get("tab_id", "default"))

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
    tab_id = str(data.get("tab_id", "default"))
    mode = data.get("mode", "1player")
    ai1  = data.get("ai1", "minmax")
    ai2  = data.get("ai2", "minmax")
    depth = int(data.get("depth", 4))
    human_color = int(data.get("human_color", RED))

    game = Connect4()
    gid = None
    try:
        gid = database.create_game(mode, ai1, ai2, depth)
        database.save_state(gid, 0, game.board_to_str())
    except Exception as e:
        logger.warning(f"DB save échoué: {e}")

    set_game(tab_id, {
        "board": game.board_to_str(),
        "mode": mode, "ai1": ai1, "ai2": ai2,
        "depth": depth, "human_color": human_color,
        "game_id": gid, "history": []
    })

    return jsonify({"ok": True, "state": game.to_dict()})


@app.route("/api/play", methods=["POST"])
def play():
    """Joue un coup humain."""
    data = request.get_json(force=True)
    tab_id = str(data.get("tab_id", "default"))
    col = int(data.get("col", -1))

    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie en cours"}), 400

    game = Connect4.from_str(g["board"])
    mode = g.get("mode", "1player")

    if game.game_over:
        return jsonify({"error": "Partie terminée"}), 400

    if mode == "1player":
        if game.current_player != g.get("human_color", RED):
            return jsonify({"error": "C'est le tour de l'IA"}), 400

    history = g.get("history", [])
    history.append(game.board_to_str())
    g["history"] = history[-40:]

    if not game.drop_piece(col):
        return jsonify({"error": "Coup invalide"}), 400

    _persist_move(game, col, g)
    g["board"] = game.board_to_str()
    set_game(tab_id, g)

    return jsonify({"ok": True, "state": game.to_dict()})







@app.route("/api/predict", methods=["POST"])
def predict():
    """Prédit l'issue de la partie avec MinMax profond."""
    data   = request.get_json(force=True)
    tab_id = str(data.get("tab_id", "default"))

    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie"}), 400

    game = Connect4.from_str(g["board"])
    if game.game_over:
        return jsonify({"error": "Partie terminée"}), 400

    # Recherche profonde pour prédire
    import math
    player = game.current_player
    result = _deep_predict(game, player, depth=8)

    return jsonify({"ok": True, **result})


def _deep_predict(game: Connect4, ai_player: int, depth: int = 8) -> dict:
    """Analyse profonde : prédit gagnant et nombre de coups."""
    import math
    from minmax import minimax, evaluate_board

    opp = YELLOW if ai_player == RED else RED
    player_name = "Rouge" if ai_player == RED else "Jaune"
    opp_name    = "Jaune" if ai_player == RED else "Rouge"

    # MinMax profond pour trouver le score
    _, score = minimax(game, depth, -math.inf, math.inf, True, ai_player)

    if score >= 9_000_000:
        # Victoire forcée — estimer dans combien de coups
        turns = max(1, (10_000_000 - score))
        turns = min(turns, game.get_valid_columns().__len__() * 2)
        return {
            "prediction": f"🔴 {player_name} gagne dans environ {max(1,turns)} coup(s) !",
            "winner": ai_player,
            "turns": max(1, turns),
            "confidence": "haute"
        }
    elif score <= -9_000_000:
        turns = max(1, (10_000_000 + score))
        turns = min(turns, 20)
        return {
            "prediction": f"🟡 {opp_name} gagne dans environ {max(1,turns)} coup(s) !",
            "winner": opp,
            "turns": max(1, turns),
            "confidence": "haute"
        }
    elif score > 20:
        return {
            "prediction": f"📈 {player_name} est en avantage",
            "winner": None,
            "turns": None,
            "confidence": "moyenne",
            "score": score
        }
    elif score < -20:
        return {
            "prediction": f"📉 {opp_name} est en avantage",
            "winner": None,
            "turns": None,
            "confidence": "moyenne",
            "score": score
        }
    else:
        return {
            "prediction": "⚖️ Position équilibrée",
            "winner": None,
            "turns": None,
            "confidence": "basse",
            "score": score
        }

@app.route("/api/set_board", methods=["POST"])
def set_board():
    """Charge une position personnalisée peinte par l'utilisateur."""
    data = request.get_json(force=True)
    grid_str = data.get("grid_str", "")
    mode     = data.get("mode", "1player")
    ai1      = data.get("ai1", "minmax")
    ai2      = data.get("ai2", "minmax")
    depth    = int(data.get("depth", 4))
    human_color = int(data.get("human_color", RED))

    # Validation longueur
    if len(grid_str) != 81:
        return jsonify({"error": "Grille invalide (81 cases requises)"}), 400

    # Valider caractères
    for ch in grid_str:
        if ch not in ("R", "J", "."):
            return jsonify({"error": f"Caractère invalide : {ch}"}), 400

    game = Connect4.from_str(grid_str)

    # Auto-détecter à qui de jouer
    r_count = grid_str.count("R")
    j_count = grid_str.count("J")
    if r_count == j_count:
        game.current_player = RED    # Rouge commence
    elif r_count == j_count + 1:
        game.current_player = YELLOW  # Jaune joue
    else:
        return jsonify({"error": f"Position invalide : {r_count} rouges vs {j_count} jaunes (différence > 1)"}), 400

    # Créer la partie en DB
    try:
        gid = database.create_game(mode, ai1, ai2, depth)
        database.save_state(gid, game.ply, game.board_to_str())
    except Exception as e:
        logger.warning(f"DB save échoué: {e}")
        gid = None

    data2  = request.get_json(force=True) or {}
    tab_id = str(data2.get("tab_id", "default"))
    set_game(tab_id, {
        "board": game.board_to_str(), "mode": mode,
        "ai1": ai1, "ai2": ai2, "depth": depth,
        "human_color": human_color, "game_id": gid, "history": []
    })

    turn_label = "Rouge" if game.current_player == RED else "Jaune"
    return jsonify({
        "ok": True,
        "state": game.to_dict(),
        "turn": turn_label,
        "r_count": r_count,
        "j_count": j_count
    })


@app.route("/api/switch_player", methods=["POST"])
def switch_player():
    """Bascule Rouge ou Jaune entre Humain et IA en pleine partie."""
    data   = request.get_json(force=True)
    which  = data.get("which", "ai2")   # "ai1" (rouge) ou "ai2" (jaune)
    new_type = data.get("type", "minmax")  # "human", "minmax", "ia", "random"

    data2  = request.get_json(force=True) or {}
    tab_id = str(data2.get("tab_id", "default"))
    g = get_game(tab_id)
    if g:
        g[which] = new_type
        set_game(tab_id, g)
    return jsonify({"ok": True, "which": which, "type": new_type})

@app.route("/api/hint", methods=["POST"])
def hint():
    """Suggère la meilleure colonne pour le joueur humain."""
    data   = request.get_json(force=True)
    tab_id = str(data.get("tab_id", "default"))

    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie"}), 400

    game = Connect4.from_str(g["board"])
    if game.game_over:
        return jsonify({"error": "Partie terminée"}), 400

    depth = g.get("depth", 4)
    best_col   = minmax_ai.get_best_move(game, depth)
    all_scores = minmax_ai.get_all_scores(game, depth)

    return jsonify({
        "ok": True,
        "hint_col": best_col,
        "scores": {str(k): v for k, v in all_scores.items()}
    })

@app.route("/api/undo", methods=["POST"])
def undo():
    """Annule le(s) dernier(s) coup(s) selon le mode."""
    data   = request.get_json(force=True)
    tab_id = str(data.get("tab_id", "default"))

    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie"}), 400

    history = g.get("history", [])
    if not history:
        return jsonify({"error": "Rien à annuler"}), 400

    mode = g.get("mode", "1player")
    nb_undo = 2 if mode == "1player" and len(history) >= 2 else 1
    grid_str = g["board"]
    for _ in range(nb_undo):
        if history:
            grid_str = history.pop()

    g["board"]   = grid_str
    g["history"] = history
    set_game(tab_id, g)

    game = Connect4.from_str(grid_str)
    return jsonify({"ok": True, "state": game.to_dict()})

@app.route("/api/ai_move", methods=["POST"])
def ai_move():
    """L'IA joue son coup."""
    data = request.get_json(force=True)
    tab_id = str(data.get("tab_id", "default"))

    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie en cours"}), 400

    game = Connect4.from_str(g["board"])
    if game.game_over:
        return jsonify({"error": "Partie terminée"}), 400

    mode  = g.get("mode", "1player")
    depth = g.get("depth", 4)

    if mode == "0player":
        ai_type = g.get("ai1") if game.current_player == RED else g.get("ai2")
    else:
        ai_type = g.get("ai2")

    col_scores = _compute_all_scores(game, ai_type, depth)
    col = _compute_ai_move(game, ai_type, depth)
    if col is None:
        return jsonify({"error": "Aucun coup disponible"}), 400

    history = g.get("history", [])
    history.append(game.board_to_str())
    g["history"] = history[-40:]

    game.drop_piece(col)
    _persist_move(game, col, g)
    g["board"] = game.board_to_str()
    set_game(tab_id, g)

    return jsonify({"ok": True, "col": col, "state": game.to_dict(), "scores": col_scores})


@app.route("/api/state", methods=["GET"])
def get_state():
    """Retourne l'état courant de la partie."""
    tab_id = request.args.get("tab_id", "default")
    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie"}), 400
    game = Connect4.from_str(g["board"])
    return jsonify(game.to_dict())



@app.route("/api/abandon", methods=["POST"])
def abandon():
    """Abandonne la partie et génère une raison via analyse."""
    data   = request.get_json(force=True)
    tab_id = str(data.get("tab_id", "default"))

    g = get_game(tab_id)
    if not g:
        return jsonify({"error": "Pas de partie"}), 400

    game = Connect4.from_str(g["board"])

    # Analyser la position pour donner une raison
    import math
    from minmax import minimax, evaluate_board

    player      = game.current_player
    opp         = YELLOW if player == RED else RED
    player_name = "Rouge" if player == RED else "Jaune"
    opp_name    = "Jaune" if player == RED else "Rouge"

    _, score = minimax(game, 6, -math.inf, math.inf, True, player)

    if score <= -9_000_000:
        raison = f"Position perdue — {opp_name} avait une séquence gagnante forcée."
    elif score < -50:
        raison = f"Désavantage matériel important — {opp_name} contrôlait mieux le centre."
    elif score < -10:
        raison = f"Légère infériorité positionelle — difficile de renverser la situation."
    else:
        raison = f"Position encore jouable — abandon prématuré !"

    # Terminer la partie en DB
    gid = g.get("game_id")
    if gid:
        try:
            database.finish_game(gid, opp)
        except Exception:
            pass

    _games.pop(tab_id, None)

    return jsonify({
        "ok": True,
        "raison": raison,
        "score": score,
        "gagnant": opp_name
    })


@app.route("/api/elo", methods=["GET"])
def get_elo():
    """Retourne les stats Elo des IA."""
    try:
        conn = database.get_connection()
        cur  = conn.cursor()
        # Calculer Elo simple depuis les parties app_games
        cur.execute("""
            SELECT ai2_type,
                   COUNT(*) as total,
                   SUM(CASE WHEN winner = 1 THEN 1 ELSE 0 END) as rouge_wins,
                   SUM(CASE WHEN winner = 2 THEN 1 ELSE 0 END) as jaune_wins,
                   SUM(CASE WHEN winner = 0 THEN 1 ELSE 0 END) as draws
            FROM app_games
            WHERE mode = '1player' AND winner IS NOT NULL
            GROUP BY ai2_type
        """)
        rows = cur.fetchall()
        cur.close()

        stats = []
        for ai_type, total, rw, jw, draws in rows:
            if not total: continue
            win_rate = rw / total if total else 0
            # Elo approximatif basé sur win rate humain
            human_wr = jw / total if total else 0.5
            elo = round(1500 + 400 * (human_wr - 0.5))
            stats.append({
                "ia": ai_type or "minmax",
                "total": total,
                "rouge_wins": rw,
                "jaune_wins": jw,
                "draws": draws,
                "human_win_rate": round(human_wr * 100, 1),
                "elo_estimate": elo
            })
        return jsonify({"ok": True, "stats": stats})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

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
    """Retourne les scores de toutes les colonnes pour affichage (normalisés 0-100)."""
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

        if not raw:
            return {}

        # Normaliser 0-100 pour l'affichage (scores minmax bruts = ±10^9)
        vals = list(raw.values())
        min_v = min(vals)
        max_v = max(vals)
        if max_v - min_v > 0:
            return {
                str(k): round((v - min_v) / (max_v - min_v) * 100)
                for k, v in raw.items()
            }
        else:
            return {str(k): 50 for k in raw}

    except Exception as e:
        logger.warning(f"Erreur scores: {e}")
        return {}


def _compute_ai_move(game: Connect4, ai_type: str, depth: int) -> int | None:
    valid = game.get_valid_columns()
    if not valid:
        return None

    # ── PRIORITÉ ABSOLUE 1 : coup gagnant immédiat ────────────────
    # (avant opening book, avant tout)
    for col in valid:
        g2 = game.copy()
        g2.drop_piece(col)
        if g2.game_over and g2.winner == game.current_player:
            return col

    # ── PRIORITÉ ABSOLUE 2 : bloquer victoire adverse immédiate ───
    opp = YELLOW if game.current_player == RED else RED
    for col in valid:
        g2 = game.copy()
        g2.current_player = opp
        g2.drop_piece(col)
        if g2.game_over and g2.winner == opp:
            return col

    if ai_type == "random":
        return random_ai.get_best_move(game)

    # Bibliothèque d'ouverture pour les premiers coups (instantané)
    opening = get_opening_move(game)
    if opening is not None:
        return opening

    if ai_type == "ia":
        ai = get_db_ai()
        if ai:
            return ai.get_best_move(game)
        return random_ai.get_best_move(game)
    else:  # minmax (défaut)
        return minmax_ai.get_best_move(game, depth)


def _persist_move(game: Connect4, col: int, g: dict = None):
    gid = g.get("game_id") if g else None
    if not gid:
        return
    try:
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
