"""
config.py — Configuration centralisée du projet UberEats Monitor
Modifie ce fichier pour ajuster les villes, les URLs et autres paramètres.
"""

import os

# ─────────────────────────────────────────────
# VILLES CIBLES (Finistère)
# Coordonnées GPS utilisées pour construire les URLs UberEats
# ─────────────────────────────────────────────
CITIES = [
    {
        "name": "Lesneven",
        "slug": "lesneven",
        "lat": 48.5717,
        "lon": -4.3261,
    },
    {
        "name": "Landivisiau",
        "slug": "landivisiau",
        "lat": 48.5146,
        "lon": -4.0672,
    },
    {
        "name": "Saint-Pol-de-Léon",
        "slug": "saint-pol-de-leon",
        "lat": 48.6855,
        "lon": -3.9847,
    },
]

# ─────────────────────────────────────────────
# CLÉS API (lues depuis les variables d'environnement GitHub Secrets)
# Ne jamais hardcoder de clé directement ici !
# ─────────────────────────────────────────────
SCRAPFLY_API_KEY = os.environ.get("SCRAPFLY_API_KEY", "")

# ─────────────────────────────────────────────
# BASE DE DONNÉES
# ─────────────────────────────────────────────
DB_PATH = "data/history.db"

# ─────────────────────────────────────────────
# SCRAPFLY — Options de scraping
# ─────────────────────────────────────────────
SCRAPFLY_OPTIONS = {
    "asp": True,              # Bypass anti-bot (Cloudflare, DataDome…)
    "render_js": True,        # Rendu JavaScript côté cloud (headless browser)
    "proxy_pool": "public_residential_pool",  # Proxies résidentiels
    "country": "FR",          # Géolocalisation France
    "wait_for_selector": "main",  # Attendre le contenu principal
}

# ─────────────────────────────────────────────
# DÉTECTION DU MESSAGE "PAS DE LIVREURS"
# Signaux stricts : UNIQUEMENT les phrases de pénurie globale de livreurs
# (on évite "n'est pas disponible" qui correspond aux restaurants fermés)
# ─────────────────────────────────────────────
UNAVAILABILITY_SIGNALS = [
    "aucun coursier",
    "aucun livreur",
    "pas de coursier",
    "pas de livreur",
    "no couriers nearby",
    "no couriers available",
    "livreurs indisponibles",
    "coursiers indisponibles",
]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOG_LEVEL = "INFO"  # DEBUG pour plus de verbosité
