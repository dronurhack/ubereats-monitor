"""
config.py — Configuration centrale du projet UberEats Monitor
"""

import os

# ─────────────────────────────────────────────
# VILLES À SURVEILLER (URLs directes par ville)
# ─────────────────────────────────────────────
CITIES = [
    {
        "name": "Lesneven",
        "url": "https://www.ubereats.com/fr/store/mcdonalds-lesneven/YZYMWgwoV3W8lqE3tnmRBA?diningMode=DELIVERY&surfaceName=",
        "slug": "lesneven",
        "lat": 48.5714,
        "lon": -4.3222,
    },
    {
        "name": "Landivisiau",
        "url": "https://www.ubereats.com/fr/store/mcdonalds-landivisiau/_eOW8FZIV4iFEbal8hnYqA?diningMode=DELIVERY&surfaceName=",
        "slug": "landivisiau",
        "lat": 48.5090,
        "lon": -4.0724,
    },
    {
        "name": "Saint-Pol-de-Léon",
        "url": "https://www.ubereats.com/fr/store/mcdonalds-saint-pol-de-leon/EWQNkPHFUviyXnOHOFDWnA?diningMode=DELIVERY&surfaceName=",
        "slug": "saint-pol-de-leon",
        "lat": 48.6845,
        "lon": -3.9861,
    },
]

# ─────────────────────────────────────────────
# BASE DE DONNÉES ET LOGS
# ─────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/history.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
SCRAPFLY_API_KEY = os.getenv("SCRAPFLY_API_KEY", "scp-live-c36a7d2bd6be41dbaf8e0659d66742f8")

SCRAPFLY_OPTIONS = {
    "asp": True,
    "render_js": True,
    "proxy_pool": "public_residential_pool",
    "country": "FR",
    "wait_for_selector": "main",
}

# ─────────────────────────────────────────────
# PHRASES STRICTES ET SANS FAUX POSITIFS DE PÉNURIE DE LIVREURS
# ─────────────────────────────────────────────
UNAVAILABILITY_SIGNALS = [
    "aucun coursier a proximite",
    "aucun coursier à proximité",
    "aucun coursier",
    "pas de coursier",
    "pas de livreurs a proximite",
    "pas de livreurs à proximité",
    "aucun livreur",
    "no couriers nearby",
]
