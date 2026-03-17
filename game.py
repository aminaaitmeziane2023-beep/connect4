# game.py — Logique du jeu Puissance 4 sur grille 9x9
# Encodage: 81 caractères, row-major, row 0 = bas, row 8 = haut
# R = Rouge (joueur 1), J = Jaune (joueur 2), . = vide

ROWS = 9
COLS = 9
WIN_LENGTH = 4
EMPTY = 0
RED = 1       # 'R'
YELLOW = 2    # 'J'


class Connect4:
    def __init__(self):
        # board[row][col], row 0 = bas
        self.board = [[EMPTY] * COLS for _ in range(ROWS)]
        self.current_player = RED
        self.game_over = False
        self.winner = None   # RED, YELLOW, ou 0 (nul)
        self.ply = 0
        self.last_move = None

    # ------------------------------------------------------------------ #
    #  Placer une pièce                                                     #
    # ------------------------------------------------------------------ #
    def drop_piece(self, col):
        """Fait tomber une pièce dans la colonne col.
        Retourne True si le coup est valide, False sinon."""
        if col < 0 or col >= COLS or self.game_over:
            return False
        for row in range(ROWS):
            if self.board[row][col] == EMPTY:
                self.board[row][col] = self.current_player
                self.ply += 1
                self.last_move = (row, col)
                if self._check_win(self.current_player):
                    self.game_over = True
                    self.winner = self.current_player
                elif self._check_draw():
                    self.game_over = True
                    self.winner = 0
                else:
                    self.current_player = YELLOW if self.current_player == RED else RED
                return True
        return False  # colonne pleine

    # ------------------------------------------------------------------ #
    #  Utilitaires                                                          #
    # ------------------------------------------------------------------ #
    def get_valid_columns(self):
        return [c for c in range(COLS) if self.board[ROWS - 1][c] == EMPTY]

    def is_valid_column(self, col):
        return 0 <= col < COLS and self.board[ROWS - 1][col] == EMPTY

    def _check_win(self, player):
        b = self.board
        # Horizontal
        for r in range(ROWS):
            for c in range(COLS - WIN_LENGTH + 1):
                if all(b[r][c + i] == player for i in range(WIN_LENGTH)):
                    return True
        # Vertical
        for c in range(COLS):
            for r in range(ROWS - WIN_LENGTH + 1):
                if all(b[r + i][c] == player for i in range(WIN_LENGTH)):
                    return True
        # Diagonale montante
        for r in range(ROWS - WIN_LENGTH + 1):
            for c in range(COLS - WIN_LENGTH + 1):
                if all(b[r + i][c + i] == player for i in range(WIN_LENGTH)):
                    return True
        # Diagonale descendante
        for r in range(WIN_LENGTH - 1, ROWS):
            for c in range(COLS - WIN_LENGTH + 1):
                if all(b[r - i][c + i] == player for i in range(WIN_LENGTH)):
                    return True
        return False

    def _check_draw(self):
        return len(self.get_valid_columns()) == 0

    # ------------------------------------------------------------------ #
    #  Sérialisation                                                        #
    # ------------------------------------------------------------------ #
    def board_to_str(self):
        """Convertit le plateau en chaîne de 81 caractères (row 0 = bas)."""
        result = []
        for row in range(ROWS):
            for col in range(COLS):
                v = self.board[row][col]
                result.append('.' if v == EMPTY else ('R' if v == RED else 'J'))
        return ''.join(result)

    @classmethod
    def from_str(cls, s):
        """Reconstruit un plateau depuis une chaîne de 81 caractères."""
        g = cls()
        for i, ch in enumerate(s):
            row, col = divmod(i, COLS)
            if ch == 'R':
                g.board[row][col] = RED
            elif ch == 'J':
                g.board[row][col] = YELLOW
        r_count = s.count('R')
        j_count = s.count('J')
        g.ply = r_count + j_count
        g.current_player = RED if r_count == j_count else YELLOW
        # Vérifier si la partie est terminée
        if g._check_win(RED):
            g.game_over = True
            g.winner = RED
        elif g._check_win(YELLOW):
            g.game_over = True
            g.winner = YELLOW
        elif g._check_draw():
            g.game_over = True
            g.winner = 0
        return g

    def copy(self):
        g = Connect4.__new__(Connect4)
        g.board = [row[:] for row in self.board]
        g.current_player = self.current_player
        g.game_over = self.game_over
        g.winner = self.winner
        g.ply = self.ply
        g.last_move = self.last_move
        return g

    def to_dict(self):
        """Sérialise l'état pour l'API JSON."""
        grid = []
        for row in range(ROWS - 1, -1, -1):  # de haut en bas pour l'affichage
            for col in range(COLS):
                grid.append(self.board[row][col])
        return {
            'grid': grid,
            'grid_str': self.board_to_str(),
            'current_player': self.current_player,
            'game_over': self.game_over,
            'winner': self.winner,
            'ply': self.ply,
            'valid_columns': self.get_valid_columns(),
        }
