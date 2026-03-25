#!/usr/bin/env python3
"""
generate_games.py — Génère des parties automatiques et les insère en DB
Usage: python generate_games.py --target 1000000 --batch 500
"""
import os
import sys
import time
import random
import argparse
import psycopg2
from game import Connect4, RED, YELLOW
from minmax import get_best_move

DATABASE_URL = os.environ.get("DATABASE_URL", "")

def get_conn():
    url = DATABASE_URL
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    conn = psycopg2.connect(
        url,
        sslmode="require",
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
        connect_timeout=30
    )
    conn.autocommit = False
    return conn

def play_game(mode: str) -> dict:
    """
    Joue une partie complète entre deux IA.
    mode: 'random_vs_random' | 'minmax_vs_random' | 'minmax_vs_minmax'
    Retourne: { winner, is_draw, seq, states }
    """
    game = Connect4()
    seq = []
    states = [game.board_to_str()]

    while not game.game_over:
        player = game.current_player
        col = None

        if mode == 'random_vs_random':
            col = random.choice(game.get_valid_columns())
        elif mode == 'minmax_vs_random':
            if player == RED:
                col = get_best_move(game, depth=2)
            else:
                col = random.choice(game.get_valid_columns())
        elif mode == 'minmax_vs_minmax':
            depth = random.choice([2, 3])
            col = get_best_move(game, depth=depth)
        else:
            col = random.choice(game.get_valid_columns())

        if col is None:
            break
        game.drop_piece(col)
        seq.append(col)
        states.append(game.board_to_str())

    winner_char = None
    if game.winner == RED:    winner_char = 'R'
    elif game.winner == YELLOW: winner_char = 'J'

    seq_str = ''.join(str(c) for c in seq)
    return {
        'winner': winner_char,
        'is_draw': 1 if (game.game_over and game.winner == 0) else 0,
        'seq': seq_str,
        'states': states,
        'moves': seq,
        'ply': game.ply
    }

def insert_batch(conn, games_data: list):
    cur = conn.cursor()
    inserted = 0
    for g in games_data:
        try:
            # Insert game
            cur.execute("""
                INSERT INTO games
                  (lignes, colonnes, nb_colonnes_utilisees, mode, confiance,
                   premier, status, joueur_actuel, winner, is_draw,
                   seq_original, seq_miroir, canonical_key,
                   canonical_hash, final_state_hash)
                VALUES
                  (9, 9, 9, 0, 1,
                   'R', 'TERMINEE', 'R', %s, %s,
                   %s, %s, %s,
                   decode(md5(%s), 'hex'), decode(md5(%s || 'f'), 'hex'))
                ON CONFLICT DO NOTHING
                RETURNING id
            """, (
                g['winner'], g['is_draw'],
                g['seq'], g['seq'][::-1], g['seq'],
                g['seq'], g['seq']
            ))
            row = cur.fetchone()
            if not row:
                continue
            gid = row[0]

            # Insert states
            for ply, grid_str in enumerate(g['states']):
                cur.execute(
                    "INSERT INTO states (game_id, ply, grid_str) VALUES (%s,%s,%s)",
                    (gid, ply, grid_str)
                )

            # Insert moves
            for ply, col in enumerate(g['moves']):
                player = 'R' if ply % 2 == 0 else 'J'
                cur.execute(
                    "INSERT INTO moves (game_id, ply, col, player) VALUES (%s,%s,%s,%s)",
                    (gid, ply+1, col, player)
                )
            inserted += 1
        except Exception as e:
            conn.rollback()
            cur = conn.cursor()
            continue

    conn.commit()
    cur.close()
    return inserted

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', type=int, default=100000)
    parser.add_argument('--batch',  type=int, default=200)
    args = parser.parse_args()

    if not DATABASE_URL:
        print("❌ DATABASE_URL non définie")
        sys.exit(1)

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM games")
    existing = cur.fetchone()[0]
    cur.close()
    print(f"Parties existantes : {existing:,}")

    to_generate = max(0, args.target - existing)
    print(f"À générer : {to_generate:,} parties")
    if to_generate == 0:
        print("✅ Objectif déjà atteint !")
        return

    total_inserted = 0
    start = time.time()
    modes = ['random_vs_random'] * 5 + ['minmax_vs_random'] * 3 + ['minmax_vs_minmax'] * 2

    while total_inserted < to_generate:
        batch = []
        for _ in range(min(args.batch, to_generate - total_inserted)):
            mode = random.choice(modes)
            batch.append(play_game(mode))

        # Reconnexion automatique si la connexion est tombée
        try:
            conn.cursor().execute("SELECT 1")
        except Exception:
            print("\n  Reconnexion...")
            try: conn.close()
            except: pass
            conn = get_conn()

        inserted = insert_batch(conn, batch)
        total_inserted += inserted

        elapsed = time.time() - start
        rate = total_inserted / elapsed if elapsed > 0 else 0
        remaining = (to_generate - total_inserted) / rate if rate > 0 else 0
        pct = (total_inserted / to_generate) * 100

        print(f"\r[{pct:5.1f}%] {total_inserted:>8,}/{to_generate:,} parties"
              f" | {rate:5.0f}/s | reste ~{remaining/60:.1f}min   ", end='', flush=True)

    print(f"\n✅ Terminé ! {total_inserted:,} parties générées en {(time.time()-start)/60:.1f} min")
    conn.close()

if __name__ == '__main__':
    main()
