"""
auto_play.py — Génère des parties IA vs IA via l'API de ton site Render
Les parties sont sauvegardées directement dans ta BD PostgreSQL Render.
Usage: python auto_play.py
"""

import requests
import time
import uuid

# ← Mets l'URL de ton site Render ici
URL = "https://connect4-1-ngkq.onrender.com"

TARGET = 40000
DEPTH  = 3      # profondeur MinMax (3 = bon compromis vitesse/qualité)

def play_one_game() -> bool:
    tab_id = str(uuid.uuid4())
    try:
        # 1. Créer une partie IA vs IA
        r = requests.post(f"{URL}/api/new_game", json={
            "tab_id": tab_id,
            "mode":   "0player",
            "ai1":    "minmax",
            "ai2":    "minmax",
            "depth":  DEPTH
        }, timeout=10)
        if not r.ok:
            return False

        # 2. Jouer jusqu'à la fin (max 81 coups sur 9x9)
        for _ in range(90):
            r = requests.post(f"{URL}/api/ai_move", json={"tab_id": tab_id}, timeout=15)
            if not r.ok:
                return False
            state = r.json().get("state", {})
            if state.get("game_over"):
                return True
            time.sleep(0.05)  # petit délai pour ne pas surcharger Render

        return False

    except Exception as e:
        print(f"\n⚠️  Erreur: {e}")
        time.sleep(2)
        return False


def get_current_count() -> int:
    try:
        r = requests.get(f"{URL}/api/stats", timeout=5)
        return r.json().get("total_games", 0)
    except:
        return 0


def main():
    print(f"🎮 Auto-play vers {URL}")
    print(f"🎯 Objectif : {TARGET} parties\n")

    # Vérifier que le site est accessible
    try:
        requests.get(URL, timeout=10)
    except Exception as e:
        print(f"❌ Site inaccessible : {e}")
        print("   Vérifie l'URL dans auto_play.py !")
        return

    current = get_current_count()
    print(f"📊 Parties actuelles en BD : {current}")

    to_generate = max(0, TARGET - current)
    print(f"⚙️  À générer : {to_generate}\n")

    if to_generate == 0:
        print("✅ Objectif déjà atteint !")
        return

    done = 0
    errors = 0
    start = time.time()

    while done < to_generate:
        success = play_one_game()

        if success:
            done += 1
            errors = 0
        else:
            errors += 1
            if errors > 10:
                print("\n❌ Trop d'erreurs consécutives, arrêt.")
                break

        elapsed = time.time() - start
        rate    = done / elapsed if elapsed > 0 else 0
        reste   = (to_generate - done) / rate / 60 if rate > 0 else 0
        pct     = done / to_generate * 100

        print(f"\r[{pct:5.1f}%] {done:>6}/{to_generate} parties"
              f" | {rate:4.1f}/s | reste ~{reste:.0f}min   ", end="", flush=True)

        # Afficher le total réel toutes les 500 parties
        if done % 500 == 0 and done > 0:
            total = get_current_count()
            print(f"\n  📊 Total en BD : {total}")

    total = get_current_count()
    print(f"\n\n✅ Terminé ! {done} parties générées.")
    print(f"📊 Total en BD : {total}")

if __name__ == "__main__":
    main()
