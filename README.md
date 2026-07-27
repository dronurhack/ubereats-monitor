# 🚴 UberEats Monitor — Surveillance de la disponibilité des livreurs

Outil de surveillance automatique qui détecte, toutes les 10 minutes,
si UberEats affiche un message d'indisponibilité de livreurs dans
**Lesneven**, **Landivisiau** et **Saint-Pol-de-Léon** (Finistère).

> **Objectif** : Repérer les créneaux horaires où la demande dépasse l'offre
> de livreurs, pour optimiser tes horaires de travail Uber Eats.

---

## 📁 Structure du projet

```
ubereats-monitor/
├── .github/
│   └── workflows/
│       ├── scan.yml          ← Cron toutes les 10 min (scraping)
│       └── keepalive.yml     ← Ping hebdomadaire anti-désactivation
├── data/
│   ├── .gitkeep             ← Placeholder (la BDD sera créée ici)
│   └── history.db           ← Base SQLite (auto-commitée par GitHub Actions)
├── config.py                ← Villes, paramètres, signaux de détection
├── scraper.py               ← Script principal de scraping UberEats
├── analyse.py               ← Analyse des créneaux de pénurie
├── requirements.txt         ← Dépendances Python
├── .gitignore
└── README.md
```

---

## 🗄️ Schéma de la base de données

Table `scans` dans `data/history.db` (SQLite) :

| Colonne      | Type    | Description                                         |
|-------------|---------|-----------------------------------------------------|
| `id`         | INTEGER | Identifiant auto-incrémenté                         |
| `city`       | TEXT    | Nom de la ville (ex: "Lesneven")                    |
| `scanned_at` | TEXT    | Horodatage UTC ISO 8601 (ex: "2024-11-15T14:30:00") |
| `status`     | TEXT    | `DISPONIBLE`, `INDISPONIBLE` ou `ERREUR`            |
| `detection`  | TEXT    | Phrase qui a déclenché la détection (ou NULL)       |
| `url`        | TEXT    | URL scrapée                                         |
| `http_code`  | INTEGER | Code HTTP retourné                                  |
| `error`      | TEXT    | Message d'erreur si applicable (ou NULL)            |

---

## ⚙️ Configuration initiale — Guide étape par étape

### Étape 1 — Créer un compte Scrapfly

1. Va sur [https://scrapfly.io](https://scrapfly.io) et crée un compte gratuit
2. Le plan **Free** offre **1 000 requêtes/mois** (suffisant pour tester)
3. Pour une collecte continue, le plan **Starter** (~$26/mois) donne **250 000 req/mois**
4. Dans ton dashboard Scrapfly → **API Key** → copie ta clé (format : `scp-...`)

### Étape 2 — Créer le dépôt GitHub

1. Va sur [https://github.com](https://github.com) → **New repository**
2. Nom : `ubereats-monitor` (ou ce que tu veux)
3. **Public** (obligatoire pour GitHub Actions gratuit illimité)
4. Cocher **Add a README file** → Créer

### Étape 3 — Uploader les fichiers du projet

Option A — Via l'interface web GitHub :
1. Clique **Add file** → **Upload files**
2. Glisse-dépose tous les fichiers du dossier `ubereats-monitor/`
3. Respecte bien l'arborescence (`.github/workflows/` en particulier)

Option B — Via Git en ligne de commande :
```bash
cd ubereats-monitor
git init
git remote add origin https://github.com/TON_PSEUDO/ubereats-monitor.git
git add .
git commit -m "🚀 Initial commit"
git push -u origin main
```

### Étape 4 — Configurer le secret SCRAPFLY_API_KEY

1. Sur GitHub, va dans ton repo → **Settings** → **Secrets and variables** → **Actions**
2. Clique **New repository secret**
3. Nom : `SCRAPFLY_API_KEY`
4. Valeur : ta clé Scrapfly (ex: `scp-live-abc123...`)
5. Clique **Add secret**

### Étape 5 — Activer GitHub Actions

1. Va dans l'onglet **Actions** de ton repo
2. Si GitHub affiche un avertissement, clique **I understand my workflows, go ahead and enable them**
3. Le workflow `scan.yml` se déclenchera automatiquement dans les 10 prochaines minutes

### Étape 6 — Vérifier que tout fonctionne

1. Onglet **Actions** → clique sur le workflow **UberEats Monitor — Scan toutes les 10 min**
2. Clique sur **Run workflow** → **Run workflow** (déclenchement manuel pour tester)
3. Surveille les logs en temps réel : tu dois voir les 3 villes scannées
4. Vérifie que le fichier `data/history.db` apparaît dans le repo après le run

---

## 📊 Lancer l'analyse (après quelques jours de données)

```bash
# Installation locale des dépendances
pip install -r requirements.txt

# Rapport complet
python analyse.py

# Filtrer sur une ville
python analyse.py --ville Lesneven

# Analyser les 7 derniers jours
python analyse.py --jours 7

# Exporter en CSV (pour Excel)
python analyse.py --export csv
```

---

## 💰 Estimation des coûts Scrapfly

| Plan         | Prix/mois | Requêtes incluses | Durée de collecte |
|-------------|-----------|-------------------|-------------------|
| **Free**     | 0 €       | 1 000             | ~2,3 jours        |
| **Starter**  | ~26 €     | 250 000           | ~580 jours ✅     |
| **Business** | ~100 €    | 3 000 000         | Indéfini          |

**Calcul détaillé :**
- Fréquence : toutes les 10 min = **6 scans/heure** × **3 villes** = **18 req/heure**
- Par jour : 18 × 24 = **432 requêtes/jour**
- Par mois (30j) : 432 × 30 = **~12 960 requêtes/mois**

> ⚠️ Le rendu JavaScript (`render_js=True`) + ASP (`asp=True`) consomme
> **5 crédits Scrapfly par requête** au lieu de 1.
> Donc en réalité : 12 960 × 5 = **~65 000 crédits/mois**.
> → Le plan **Starter (~26€/mois)** est recommandé pour une collecte continue.

**Pour réduire les coûts :**
- Limiter la collecte aux heures pertinentes (ex: 10h–23h)
- Modifier le cron dans `scan.yml` : `0 10-23 * * *` au lieu de `*/10 * * * *`
- Cela divise par ~1.6 la consommation (économie ~35%)

---

## 🔧 Personnalisation

### Modifier les villes cibles
Édite le fichier `config.py` → section `CITIES`.
Chaque ville nécessite un nom, un slug et des coordonnées GPS (trouvables sur Google Maps).

### Ajouter des signaux de détection
Édite `config.py` → section `UNAVAILABILITY_SIGNALS`.
Si tu observes de nouveaux messages d'UberEats, ajoute-les à la liste.

### Changer la fréquence de scan
Édite `.github/workflows/scan.yml` → ligne `cron`.
Syntaxe cron : `*/10 * * * *` = toutes les 10 min, `*/30 * * * *` = toutes les 30 min.

---

## 🐛 Dépannage

| Problème | Solution |
|---------|---------|
| `SCRAPFLY_API_KEY not set` | Vérifie le secret dans GitHub Settings → Secrets |
| `Scrapfly error 403` | La clé API est invalide ou le quota est dépassé |
| `data/history.db` ne grossit pas | Vérifie les logs Actions pour des erreurs Python |
| Cron désactivé après 60 jours | Le fichier `keepalive.yml` gère ça automatiquement |
| Beaucoup de résultats `ERREUR` | UberEats a changé sa structure — mettre à jour les signaux |
