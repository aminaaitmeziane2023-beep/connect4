# opening_book.py — Bibliothèque d'ouverture pour grille 9x9
# Les 6-8 premiers coups sont pré-calculés pour être instantanés.
# Stratégie : centrage + contrôle du milieu

from game import Connect4, RED, YELLOW, ROWS, COLS
import minmax

def _build_book():
    """Pré-calcule les meilleurs coups pour les positions de début de partie."""
    book = {}
    CENTER = COLS // 2  # colonne 4

    # Ouvertures courantes pour grille 9x9
    # Format: grid_str -> best_col
    # On pré-calcule récursivement les 5 premiers plies

    def explore(game, depth_limit=5):
        if game.ply >= depth_limit or game.game_over:
            return
        gs = game.board_to_str()
        if gs in book:
            return
        # Calculer le meilleur coup avec MinMax profondeur 5
        col = minmax.get_best_move(game, 5)
        if col is not None:
            book[gs] = col
            # Explorer les réponses possibles
            for c in game.get_valid_columns():
                g2 = game.copy()
                g2.drop_piece(c)
                explore(g2, depth_limit)

    print("Construction de la bibliothèque d'ouverture...")
    g = Connect4()
    explore(g, depth_limit=6)
    print(f"Bibliothèque : {len(book)} positions pré-calculées")
    return book

# Bibliothèque simple basée sur des règles pour les débuts de partie
# (évite le calcul long au démarrage)
OPENING_RULES = {
    0: 4,   # Premier coup toujours au centre
}

# Coups de réponse courants (symétrie)
SIMPLE_RESPONSES = {
    # Si l'adversaire joue en colonne X, répondre en colonne Y
}

def get_opening_move(game: Connect4) -> int | None:
    """
    Retourne un coup d'ouverture instantané si disponible.
    Utilisé pour les ply < 8.
    """
    if game.ply >= 8:
        return None

    valid = game.get_valid_columns()
    if not valid:
        return None

    center = COLS // 2  # 4

    # Ply 0 : toujours centre
    if game.ply == 0:
        return center

    # Ply 1-3 : si centre libre, centre ou adjacent
    gs = game.board_to_str()
    r_count = gs.count('R')
    j_count = gs.count('J')

    # Priorité 1 : coup gagnant immédiat
    for col in valid:
        g2 = game.copy()
        g2.drop_piece(col)
        if g2.game_over and g2.winner == game.current_player:
            return col

    # Priorité 2 : bloquer victoire adverse
    opp = YELLOW if game.current_player == RED else RED
    for col in valid:
        g2 = game.copy()
        orig_player = g2.current_player
        g2.current_player = opp
        g2.drop_piece(col)
        if g2.game_over and g2.winner == opp:
            return col

    # Ply < 6 : préférer colonnes centrales (4,3,5,2,6)
    if game.ply < 6:
        preferred = [4, 3, 5, 2, 6, 1, 7, 0, 8]
        for col in preferred:
            if col in valid:
                return col

    return None  # Laisser MinMax décider
