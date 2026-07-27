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
    "timeout": 30000,         # Timeout 30s
    "wait_for_selector": "main",  # Attendre le contenu principal
}

# ─────────────────────────────────────────────
# DÉTECTION DU MESSAGE "PAS DE LIVREURS"
# Liste de phrases à chercher dans le HTML rendu (insensible à la casse)
# ─────────────────────────────────────────────
UNAVAILABILITY_SIGNALS = [
    "pas de livreurs",
    "no couriers",
    "aucun livreur",
    "indisponible dans votre zone",
    "not available in your area",
    "livraison non disponible",
    "delivery not available",
    "aucun restaurant",
    "no restaurants",
    "isn't available",
    "n'est pas disponible",
]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOG_LEVEL = "INFO"  # DEBUG pour plus de verbosité
