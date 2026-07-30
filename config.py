"""
config.py — Configuration centrale du projet UberEats Monitor
"""

import os

# ─────────────────────────────────────────────
# VILLES À SURVEILLER (URLs directes McDonald's + coordonnées GPS)
# ─────────────────────────────────────────────
CITIES = [
    {
        "name": "Lesneven",
        "store_url": "https://www.ubereats.com/fr/store/mcdonalds-lesneven/YZYMWgwoV3W8lqE3tnmRBA",
        "lat": 48.5714,
        "lon": -4.3222,
    },
    {
        "name": "Landivisiau",
        "store_url": "https://www.ubereats.com/fr/store/mcdonalds-landivisiau/_eOW8FZIV4iFEbal8hnYqA",
        "lat": 48.5090,
        "lon": -4.0724,
    },
    {
        "name": "Saint-Pol-de-Léon",
        "store_url": "https://www.ubereats.com/fr/store/mcdonalds-saint-pol-de-leon/EWQNkPHFUviyXnOHOFDWnA",
        "lat": 48.6845,
        "lon": -3.9861,
    },
]

# ─────────────────────────────────────────────
# BASE DE DONNÉES ET LOGS
# ─────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/history.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ─────────────────────────────────────────────
# PHRASES STRICTES — uniquement pénurie de coursiers/livreurs
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
