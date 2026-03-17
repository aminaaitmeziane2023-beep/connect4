# 🚀 GUIDE DE DÉPLOIEMENT SUR RENDER
## Puissance 4 — Grille 9×9 avec IA

---

## SOMMAIRE
1. [Prérequis](#1-prérequis)
2. [Préparer le projet GitHub](#2-préparer-le-projet-github)
3. [Créer la base PostgreSQL sur Render](#3-créer-la-base-postgresql-sur-render)
4. [Importer vos données MySQL](#4-importer-vos-données-mysql)
5. [Créer le Web Service sur Render](#5-créer-le-web-service-sur-render)
6. [Variables d'environnement](#6-variables-denvironnement)
7. [Vérification et débogage](#7-vérification-et-débogage)
8. [Structure du projet](#8-structure-du-projet)

---

## 1. Prérequis

- Un compte **Render** (vous en avez déjà un ✅)
- **Git** installé sur votre machine
- **Python 3.11+** installé localement
- Votre fichier `connect4_db.sql` (dump MySQL)
- **psql** ou **pgAdmin** pour importer les données

---

## 2. Préparer le projet GitHub

### 2a. Créer un dépôt GitHub

1. Allez sur [github.com](https://github.com) → New repository
2. Nommez-le `connect4` (ou autre)
3. Mettez-le en **Public** (plus simple pour Render gratuit)
4. Ne cochez PAS "Initialize with README"

### 2b. Pousser le code

```bash
# Dans le dossier du projet
cd connect4

# Initialiser git
git init
git add .
git commit -m "Initial commit - Puissance 4 9x9"

# Lier à GitHub (remplacez VOTRE_USER)
git remote add origin https://github.com/VOTRE_USER/connect4.git
git branch -M main
git push -u origin main
```

### 2c. Créer un fichier .gitignore

```bash
cat > .gitignore << 'EOF'
__pycache__/
*.pyc
.env
*.egg-info/
dist/
build/
.DS_Store
venv/
EOF
git add .gitignore
git commit -m "Add .gitignore"
git push
```

---

## 3. Créer la base PostgreSQL sur Render

### 3a. Nouvelle base de données

1. Connectez-vous à [dashboard.render.com](https://dashboard.render.com)
2. Cliquez **"New +"** → **"PostgreSQL"**
3. Remplissez :
   - **Name** : `connect4-db`
   - **Region** : choisissez la plus proche (ex: Frankfurt pour l'Europe)
   - **PostgreSQL Version** : 16
   - **Plan** : Free (suffisant pour commencer)
4. Cliquez **"Create Database"**

### 3b. Récupérer les credentials

Après création (quelques secondes), vous voyez la page de votre DB.
Copiez ces informations :

| Champ | Où trouver |
|-------|-----------|
| **Internal Database URL** | Section "Connections" |
| **External Database URL** | Section "Connections" |
| **Host** | Section "Connections" |
| **Port** | Section "Connections" |
| **Database** | Section "Connections" |
| **Username** | Section "Connections" |
| **Password** | Section "Connections" (cliquez l'œil) |

> ⚠️ L'**Internal URL** est pour votre Web Service Render.
> L'**External URL** est pour se connecter depuis votre PC local.

---

## 4. Importer vos données MySQL

### 4a. Convertir le dump MySQL → PostgreSQL

```bash
# Sur votre machine locale
python convert_sql.py connect4_db.sql > connect4_pg.sql
```

> ⚠️ Le fichier converti peut avoir des erreurs sur les contraintes complexes.
> Vérifiez les premières lignes du fichier converti.

### 4b. Option A : Via psql (ligne de commande)

```bash
# Installez psql si nécessaire :
# Ubuntu/Debian: sudo apt install postgresql-client
# Mac: brew install libpq

# Connexion avec l'External URL de Render :
# Format: postgresql://USER:PASSWORD@HOST:PORT/DATABASE

psql "postgresql://USER:PASSWORD@HOST:PORT/DATABASE?sslmode=require" -f connect4_pg.sql
```

### 4c. Option B : Via pgAdmin (interface graphique)

1. Téléchargez [pgAdmin](https://www.pgadmin.org/download/)
2. **Add New Server** :
   - Name: `Render Connect4`
   - Host: votre HOST Render
   - Port: votre PORT Render
   - Database: votre DATABASE Render
   - Username: votre USERNAME Render
   - Password: votre PASSWORD Render
   - SSL Mode: `require`
3. Connectez-vous
4. Clic droit sur votre DB → **Query Tool**
5. Ouvrez `connect4_pg.sql` et exécutez

### 4d. Option C : Importer directement avec Python

Créez un script `import_local.py` :

```python
import psycopg2

# Remplacez par votre External URL Render
DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DATABASE"

conn = psycopg2.connect(DATABASE_URL, sslmode="require")
conn.autocommit = True
cur = conn.cursor()

with open('connect4_pg.sql', 'r', encoding='utf-8') as f:
    sql = f.read()

# Exécuter statement par statement
statements = sql.split(';')
for i, stmt in enumerate(statements):
    stmt = stmt.strip()
    if stmt:
        try:
            cur.execute(stmt)
            if i % 100 == 0:
                print(f"Statement {i}/{len(statements)}...")
        except Exception as e:
            print(f"Erreur statement {i}: {e}")

cur.close()
conn.close()
print("Import terminé !")
```

```bash
pip install psycopg2-binary
python import_local.py
```

### 4e. Vérifier l'import

```bash
psql "postgresql://..." -c "SELECT COUNT(*) FROM states;"
# Doit retourner ~20000+ lignes
```

---

## 5. Créer le Web Service sur Render

### 5a. Nouveau service

1. Dashboard Render → **"New +"** → **"Web Service"**
2. **Connect your GitHub account** (si pas déjà fait)
3. Choisissez votre repo `connect4`
4. Cliquez **"Connect"**

### 5b. Configuration du service

| Champ | Valeur |
|-------|--------|
| **Name** | `connect4` (ou votre choix) |
| **Region** | Même que votre DB ! |
| **Branch** | `main` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 120` |
| **Plan** | `Free` |

---

## 6. Variables d'environnement

Dans la section **"Environment"** de votre Web Service, ajoutez :

| Clé | Valeur |
|-----|--------|
| `DATABASE_URL` | Coller l'**Internal Database URL** de Render |
| `SECRET_KEY` | Une chaîne aléatoire (ex: `MonSuperSecret2024ABC`) |
| `PYTHON_VERSION` | `3.11.9` |

> 💡 L'Internal URL ressemble à :
> `postgresql://user:password@dpg-XXXXX-a/connect4_db`

### Lier la DB directement (méthode recommandée)

1. Dans votre Web Service → section **"Environment"**
2. Cliquez **"Add Environment Variable"**
3. Cliquez **"Add from Database"** → sélectionnez `connect4-db`
4. Render ajoute automatiquement `DATABASE_URL` avec la bonne valeur

---

## 7. Déploiement et vérification

### 7a. Déployer

1. Cliquez **"Create Web Service"**
2. Render commence le build (2-3 minutes)
3. Observez les logs en temps réel dans **"Logs"**

### 7b. Logs attendus au démarrage

```
[INFO] Connexion PostgreSQL établie.
[INFO] Tables initialisées.
[INFO] Base de connaissances: XXXX états uniques depuis YYYY parties.
[INFO] IA chargée.
[INFO] Starting gunicorn 22.0.0
[INFO] Listening at: http://0.0.0.0:PORT
```

### 7c. Votre URL

Render génère une URL du type :
`https://connect4-XXXX.onrender.com`

> ⚠️ **Note Free Plan** : Le service "dort" après 15 min d'inactivité.
> Le premier accès après une pause prend ~30 secondes.

### 7d. Débogage fréquent

| Problème | Solution |
|---------|----------|
| `DATABASE_URL non définie` | Vérifiez les variables d'environnement |
| `psycopg2.OperationalError` | Vérifiez que SSL est activé dans la connexion |
| `ModuleNotFoundError` | Vérifiez requirements.txt |
| L'IA DB retourne des coups aléatoires | La DB n'a pas été importée, vérifiez les tables |
| Timeout au démarrage | Normal sur Free (30s), attendez |

---

## 8. Structure du projet

```
connect4/
├── app.py              # Serveur Flask principal
├── game.py             # Logique Puissance 4 (grille 9×9)
├── minmax.py           # IA MinMax avec alpha-bêta (profondeur 0-6)
├── ia.py               # IA par apprentissage (base de données)
├── random_ai.py        # IA aléatoire
├── db.py               # Connexion et persistance PostgreSQL
├── convert_sql.py      # Convertisseur MySQL → PostgreSQL
├── requirements.txt    # Dépendances Python
├── Procfile            # Commande de démarrage Render
├── runtime.txt         # Version Python
├── templates/
│   └── index.html      # Interface de jeu (HTML/CSS/JS)
└── DEPLOY_GUIDE.md     # Ce fichier
```

---

## 9. Fonctionnement du jeu

### Modes de jeu

| Mode | Description |
|------|-------------|
| **1 Joueur** | Vous contre l'IA. Choisissez votre couleur et le type d'IA |
| **2 Joueurs** | Deux humains sur le même écran |
| **0 Joueur** | L'IA joue contre elle-même (démonstration) |

### Types d'IA

| IA | Description |
|----|-------------|
| **Aléatoire** | Choisit une colonne au hasard |
| **MinMax** | Algorithme MinMax avec élagage alpha-bêta, profondeur 0 à 6 |
| **IA (BD)** | Apprend des parties historiques, choisit le coup avec le meilleur taux de victoire |

### Règles

- Grille **9 colonnes × 9 rangées**
- Les pièces tombent en bas de chaque colonne
- **4 pièces à la suite** (horizontale, verticale, ou diagonale) = victoire
- Grille pleine sans vainqueur = match nul

---

## 10. Mise à jour du site

À chaque modification de code :

```bash
git add .
git commit -m "Description du changement"
git push
```

Render détecte automatiquement le push et redéploie ! (environ 2 min)

---

## 11. Exemple de site de référence

Le site de référence que vous avez mentionné :
👉 [https://puissance4-gkg8.onrender.com/](https://puissance4-gkg8.onrender.com/)

Votre site sera accessible à une URL similaire.

---

*Guide créé pour le projet Puissance 4 · Grille 9×9 · Render Deployment*
