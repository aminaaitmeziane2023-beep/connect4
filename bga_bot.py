#!/usr/bin/env python3
"""
bga_bot.py — Bot Playwright pour BGA Connect Four (Puissance 4)
Lance le bot : python bga_bot.py --email TON_EMAIL --password TON_MDP

Prérequis :
    pip install playwright
    playwright install chromium
"""

import asyncio
import argparse
import sys
import os
import logging

from playwright.async_api import async_playwright, Page

# Ajouter le dossier du jeu au path pour importer l'IA
sys.path.insert(0, os.path.dirname(__file__))
from game import Connect4, RED, YELLOW, ROWS, COLS
from minmax import get_best_move
from opening_book import get_opening_move
from ia import DatabaseAI, build_knowledge_base
import db as database

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger(__name__)

BGA_URL      = "https://boardgamearena.com"
BGA_LOGIN    = f"{BGA_URL}/account/account/login.html"

# ── Sélecteurs BGA Connect Four ─────────────────────────────────────
# À adapter si BGA change son DOM
BOARD_SEL   = "#game_play_area"
CELL_SEL    = ".cell, [id^='cell_']"   # ajuster selon BGA
COL_SEL     = ".col_selector, [id^='col_']"

# BGA représente la grille dans des divs avec data-col / data-row
# ou des ids comme "cell_1_1"

async def login(page: Page, email: str, password: str):
    logger.info("Connexion à BGA...")
    await page.goto(BGA_LOGIN)
    await page.wait_for_load_state("networkidle")

    # Remplir email
    await page.fill('input[name="email"]', email)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"], input[type="submit"]')
    await page.wait_for_load_state("networkidle")

    # Vérifier connexion
    if "boardgamearena.com" in page.url and "login" not in page.url:
        logger.info("✅ Connecté !")
        return True
    logger.error("❌ Échec de connexion")
    return False


async def goto_game(page: Page, table_id: str = None):
    """Va sur une partie en cours ou attend une invitation."""
    if table_id:
        url = f"{BGA_URL}/table/table/joingame.html?table={table_id}"
        logger.info(f"Rejoindre table {table_id}...")
        await page.goto(url)
    else:
        logger.info("En attente d'une partie...")
        await page.goto(f"{BGA_URL}/")
    await page.wait_for_load_state("networkidle")


async def read_board(page: Page) -> tuple[list[list[int]], int]:
    """
    Lit l'état de la grille BGA.
    Retourne (board 9x9, mon_joueur).
    BGA numérote les colonnes 1-9 et les rangées 1-9.
    """
    board = [[0]*COLS for _ in range(ROWS)]
    my_player = RED  # À détecter dynamiquement

    try:
        # Récupérer toutes les cellules
        # BGA Connect Four utilise des éléments avec class contenant
        # 'piece_1' (joueur 1 = rouge) ou 'piece_2' (joueur 2 = jaune)
        # et position via data-col / data-row ou id="cell_COL_ROW"

        cells = await page.evaluate("""
        () => {
            const result = [];
            // Essayer différents sélecteurs BGA
            const cells = document.querySelectorAll(
                '[id*="cell_"], [class*="cell"], .square, [data-col]'
            );
            cells.forEach(cell => {
                // Extraire row/col depuis id ou data attributes
                const id = cell.id || '';
                const dataCol = cell.getAttribute('data-col');
                const dataRow = cell.getAttribute('data-row');
                let col = null, row = null;

                if (dataCol !== null) {
                    col = parseInt(dataCol);
                    row = parseInt(dataRow);
                } else {
                    // Parse id comme "cell_3_5" → col=3, row=5
                    const match = id.match(/cell_(\d+)_(\d+)/);
                    if (match) { col = parseInt(match[1]); row = parseInt(match[2]); }
                }

                if (col !== null && row !== null) {
                    // Détecter la couleur de la pièce
                    const html = cell.innerHTML + ' ' + cell.className;
                    let player = 0;
                    if (html.includes('player_1') || html.includes('piece_1') ||
                        html.includes('color_1') || html.includes('red')) {
                        player = 1;
                    } else if (html.includes('player_2') || html.includes('piece_2') ||
                               html.includes('color_2') || html.includes('yellow')) {
                        player = 2;
                    }
                    result.push({col, row, player});
                }
            });
            return result;
        }
        """)

        for cell in cells:
            col = cell['col'] - 1  # BGA commence à 1
            row = cell['row'] - 1
            if 0 <= row < ROWS and 0 <= col < COLS:
                board[row][col] = cell['player']

        # Détecter mon joueur (chercher "You are playing as...")
        player_text = await page.evaluate("""
        () => {
            const els = document.querySelectorAll(
                '.player-name, #player_name, .myplayer, [class*="active_player"]'
            );
            for (const el of els) {
                if (el.textContent.includes('1') || el.style.color === 'red') return 1;
                if (el.textContent.includes('2') || el.style.color === 'yellow') return 2;
            }
            return 1;
        }
        """)
        my_player = player_text if player_text in [1, 2] else RED

    except Exception as e:
        logger.error(f"Erreur lecture grille: {e}")

    return board, my_player


async def is_my_turn(page: Page) -> bool:
    """Vérifie si c'est notre tour."""
    try:
        result = await page.evaluate("""
        () => {
            // BGA indique le tour via #pagemaintitletext ou .active_player
            const title = document.querySelector(
                '#pagemaintitletext, .page-title, #gameaction_status'
            );
            if (title) {
                const text = title.textContent.toLowerCase();
                return text.includes('your turn') ||
                       text.includes('votre tour') ||
                       text.includes('à vous') ||
                       text.includes('c\'est à vous');
            }
            // Vérifier si les colonnes sont cliquables
            const cols = document.querySelectorAll(
                '[id^="col_"], .col_selector, .clickable_col'
            );
            return cols.length > 0;
        }
        """)
        return bool(result)
    except:
        return False


async def click_column(page: Page, col: int) -> bool:
    """
    Clique sur la colonne 'col' (0-indexé).
    BGA numérote les colonnes à partir de 1.
    """
    bga_col = col + 1
    logger.info(f"Cliquer colonne {bga_col} (index {col})")

    try:
        # Essayer différents sélecteurs pour cliquer une colonne
        selectors = [
            f'#col_{bga_col}',
            f'[data-col="{bga_col}"]',
            f'.col_{bga_col}',
            f'#column_{bga_col}',
            f'[id="col_{bga_col}"]',
        ]

        for sel in selectors:
            try:
                elem = await page.query_selector(sel)
                if elem:
                    await elem.click()
                    logger.info(f"✅ Cliqué via sélecteur: {sel}")
                    return True
            except:
                continue

        # Fallback: cliquer sur la cellule du haut de la colonne
        for row in range(ROWS-1, -1, -1):
            sel = f'#cell_{bga_col}_{row+1}'
            try:
                elem = await page.query_selector(sel)
                if elem:
                    await elem.click()
                    logger.info(f"✅ Cliqué cellule {sel}")
                    return True
            except:
                continue

        logger.error(f"❌ Impossible de cliquer colonne {bga_col}")
        return False

    except Exception as e:
        logger.error(f"Erreur clic: {e}")
        return False


def board_to_game(board: list[list[int]], my_player: int) -> Connect4:
    """Convertit la grille BGA en objet Connect4."""
    game = Connect4()

    # Reconstruire grid_str
    # Connect4 : row 0 = bas, BGA : row 1 = bas (à vérifier)
    grid = []
    for r in range(ROWS):
        for c in range(COLS):
            val = board[r][c]
            if val == 1:   grid.append('R')
            elif val == 2: grid.append('J')
            else:          grid.append('.')

    grid_str = ''.join(grid)
    game = Connect4.from_str(grid_str)

    # Détecter le joueur courant
    r_count = grid_str.count('R')
    j_count = grid_str.count('J')
    if r_count == j_count:
        game.current_player = RED
    else:
        game.current_player = YELLOW

    return game


async def play_game_loop(page: Page, depth: int = 4):
    """Boucle principale du bot."""
    logger.info("Bot actif — en attente de mon tour...")
    consecutive_errors = 0

    # Charger l'IA DB
    db_ai = None
    try:
        conn = database.get_connection()
        kb   = build_knowledge_base(conn)
        db_ai = DatabaseAI(kb)
        logger.info(f"✅ IA DB chargée : {len(kb)} états connus")
    except Exception as e:
        logger.warning(f"⚠ IA DB non disponible ({e}), fallback MinMax")
        from ia import DatabaseAI
        db_ai = DatabaseAI({})  # KB vide → fallback MinMax automatique

    while True:
        try:
            # Vérifier fin de partie
            game_over = await page.evaluate("""
            () => {
                const end = document.querySelector(
                    '#game_result, .game_result, [class*="endgame"]'
                );
                return !!end;
            }
            """)
            if game_over:
                logger.info("🏁 Partie terminée !")
                break

            # Vérifier si c'est mon tour
            my_turn = await is_my_turn(page)
            if not my_turn:
                await asyncio.sleep(1)
                continue

            logger.info("🎯 C'est mon tour !")

            # Lire la grille
            board, my_player = await read_board(page)
            game = board_to_game(board, my_player)

            if game.game_over:
                logger.info("Partie terminée selon la grille.")
                break

            # Calculer le meilleur coup
            logger.info(f"Calcul du meilleur coup (IA DB + ouverture)...")

            # Bibliothèque d'ouverture d'abord (instantané)
            col = get_opening_move(game)
            if col is None:
                # IA DB (hybride DB + MinMax)
                col = db_ai.get_best_move(game)

            if col is None:
                logger.error("Aucun coup calculé !")
                consecutive_errors += 1
                if consecutive_errors > 5:
                    break
                await asyncio.sleep(2)
                continue

            logger.info(f"🤖 Meilleur coup : colonne {col} (0-indexé)")
            consecutive_errors = 0

            # Jouer le coup
            success = await click_column(page, col)
            if success:
                await asyncio.sleep(2)  # Attendre animation BGA
            else:
                logger.warning("Coup non joué, réessai dans 2s...")
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Erreur boucle: {e}")
            consecutive_errors += 1
            if consecutive_errors > 10:
                logger.error("Trop d'erreurs, arrêt du bot.")
                break
            await asyncio.sleep(3)


async def inspect_mode(page: Page):
    """Mode inspection : affiche le DOM pour trouver les bons sélecteurs."""
    logger.info("=== MODE INSPECTION ===")
    result = await page.evaluate("""
    () => {
        const info = {
            title: document.querySelector('#pagemaintitletext')?.textContent?.trim(),
            url: window.location.href,
            cells: [],
            cols: []
        };

        // Chercher cellules
        ['[id*="cell"]', '[data-col]', '.square', '.cell'].forEach(sel => {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
                info.cells.push({selector: sel, count: els.length,
                    sample_id: els[0].id, sample_class: els[0].className});
            }
        });

        // Chercher colonnes cliquables
        ['[id*="col"]', '[class*="col"]', '.clickable'].forEach(sel => {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) {
                info.cols.push({selector: sel, count: els.length,
                    sample_id: els[0].id, sample_class: els[0].className});
            }
        });
        return info;
    }
    """)
    logger.info(f"URL: {result['url']}")
    logger.info(f"Titre: {result['title']}")
    logger.info(f"Cellules trouvées: {result['cells']}")
    logger.info(f"Colonnes trouvées: {result['cols']}")
    return result


async def main(email: str, password: str, table_id: str,
               depth: int, headless: bool, inspect: bool):

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless,
            args=['--no-sandbox']
        )
        context = await browser.new_context(
            viewport={'width': 1280, 'height': 900},
            locale='fr-FR'
        )
        page = await context.new_page()

        # Connexion
        logged = await login(page, email, password)
        if not logged:
            logger.error("Impossible de se connecter.")
            await browser.close()
            return

        # Aller sur la partie
        await goto_game(page, table_id)
        await asyncio.sleep(3)

        if inspect:
            # Mode inspection pour identifier les sélecteurs
            await inspect_mode(page)
            logger.info("Prenez une capture d'écran et partagez les sélecteurs.")
            input("Appuyez sur Entrée pour fermer...")
        else:
            # Lancer le bot
            await play_game_loop(page, depth)

        await browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Bot BGA Puissance 4')
    parser.add_argument('--email',    required=True,  help='Email BGA')
    parser.add_argument('--password', required=True,  help='Mot de passe BGA')
    parser.add_argument('--table',    default=None,   help='ID de la table BGA')
    parser.add_argument('--depth',    type=int, default=4, help='Profondeur MinMax')
    parser.add_argument('--headless', action='store_true', help='Navigateur invisible')
    parser.add_argument('--inspect',  action='store_true', help='Mode inspection DOM')
    args = parser.parse_args()

    asyncio.run(main(
        email=args.email,
        password=args.password,
        table_id=args.table,
        depth=args.depth,
        headless=args.headless,
        inspect=args.inspect
    ))
