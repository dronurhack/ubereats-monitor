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
        "url": (
            "https://www.ubereats.com/fr/feed?diningMode=DELIVERY"
            "&pl=JTdCJTIyYWRkcmVzcyUyMiUzQSUyMkxlc25ldmVuJTIyJTJDJTIycmVmZXJlbmNlJTIyJTNBJTIyQ2hJSmg1"
            "OVBKYU9yRmtnUmdHbmxOczJsREFRJTIyJTJDJTIycmVmZXJlbmNlVHlwZSUyMiUzQSUyMmdvb2dsZV9wbGFjZXMl"
            "MjIlMkMlMjJsYXRpdHVkZSUyMiUzQTQ4LjU3MjA4JTJDJTIybG9uZ2l0dWRlJTIyJTNBLTQuMzIyMjklN0Q%3D"
        ),
    },
    {
        "name": "Landivisiau",
        "url": (
            "https://www.ubereats.com/fr/feed?diningMode=DELIVERY"
            "&pl=JTdCJTIyYWRkcmVzcyUyMiUzQSUyMkxhbmRpdmlzaWF1JTIyJTJDJTIycmVmZXJlbmNlJTIyJTNBJTIyQ2hJS"
            "lI1TnJCRzVRRVVnUlhlVmN3SXBfX1pJJTIyJTJDJTIycmVmZXJlbmNlVHlwZSUyMiUzQSUyMmdvb2dsZV9wbGFjZX"
            "MlMjIlMkMlMjJsYXRpdHVkZSUyMiUzQTQ4LjUxMDEzMSUyQyUyMmxvbmdpdHVkZSUyMiUzQS00LjA3MzI2NSU3RA%3D%3D"
        ),
    },
    {
        "name": "Saint-Pol-de-Léon",
        "url": (
            "https://www.ubereats.com/fr/feed?diningMode=DELIVERY"
            "&pl=JTdCJTIyYWRkcmVzcyUyMiUzQSUyMlNhaW50LVBvbC1kZS1MJUMzJUE5b24lMjIlMkMlMjJyZWZlcmVuY2UlMj"
            "IlM0ElMjJDaElKYl9WRW9pRGlFMGdSd0dIbE5zMmxEQVElMjIlMkMlMjJyZWZlcmVuY2VUeXBlJTIyJTNBJTIyZ29v"
            "Z2xlX3BsYWNlcyUyMiUyQyUyMmxhdGl0dWRlJTIyJTNBNDguNjg1MTEzJTJDJTIybG9uZ2l0dWRlJTIyJTNBLTMuOT"
            "g2NTMyOTk5OTk5OTk5NyU3RA%3D%3D"
        ),
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
# Le script nettoie les accents et apostrophes avant comparaison !
# ─────────────────────────────────────────────
UNAVAILABILITY_SIGNALS = [
    "aucun coursier",
    "pas de coursier",
    "aucun livreur",
    "pas de livreur",
    "coursier a proximite",
    "livreur a proximite",
    "coursiers a proximite",
    "livreurs a proximite",
    "no couriers",
    "non disponible dans votre zone",
    "indisponible dans votre zone",
    "pas de coursiers",
    "pas de livreurs",
]

# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
LOG_LEVEL = "INFO"  # DEBUG pour plus de verbosité
