#!/usr/bin/env python3
"""
import_db.py — Importe connect4_pg.sql dans la base PostgreSQL Render
Usage: python import_db.py
"""

import psycopg2

# ---------------------------------------------------------------
# 👇 REMPLACEZ PAR VOTRE EXTERNAL DATABASE URL RENDER
#    (Dashboard Render → votre DB → Connections → External Database URL)
# ---------------------------------------------------------------
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"
# ---------------------------------------------------------------

print("Connexion à la base de données Render...")
conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

print("Lecture du fichier connect4_pg.sql...")
with open("connect4_pg.sql", "r", encoding="utf-8", errors="replace") as f:
    sql = f.read()

statements = [s.strip() for s in sql.split(";") if s.strip()]
total = len(statements)
print(f"{total} instructions SQL à exécuter...\n")

errors = 0
for i, stmt in enumerate(statements):
    try:
        cur.execute(stmt)
        if i % 500 == 0 and i > 0:
            print(f"  {i}/{total} traités...")
    except Exception as e:
        errors += 1
        if errors <= 5:
            print(f"  ⚠ Instruction {i}: {str(e)[:80]}")

print(f"\n✅ Terminé ! {total - errors}/{total} réussies, {errors} erreurs mineures.")
print()

# Vérification
try:
    cur.execute("SELECT COUNT(*) FROM states")
    print(f"✅ Lignes dans 'states' : {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM games")
    print(f"✅ Lignes dans 'games'  : {cur.fetchone()[0]:,}")
    cur.execute("SELECT COUNT(*) FROM moves")
    print(f"✅ Lignes dans 'moves'  : {cur.fetchone()[0]:,}")
except Exception as e:
    print(f"Erreur vérification : {e}")

cur.close()
conn.close()
print("\nImport terminé. Vous pouvez déployer votre site sur Render !")
