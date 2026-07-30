"""
config.py — Configuration centrale du projet UberEats Monitor
"""

import os

# ─────────────────────────────────────────────
# VILLES À SURVEILLER (URLs directes McDonald's par ville)
# ─────────────────────────────────────────────
CITIES = [
    {
        "name": "Lesneven",
        "url": "https://www.ubereats.com/fr/store/mcdonalds-lesneven/YZYMWgwoV3W8lqE3tnmRBA?diningMode=DELIVERY&surfaceName=",
    },
    {
        "name": "Landivisiau",
        "url": "https://www.ubereats.com/fr/store/mcdonalds-landivisiau/_eOW8FZIV4iFEbal8hnYqA?diningMode=DELIVERY&surfaceName=",
    },
    {
        "name": "Saint-Pol-de-Léon",
        "url": "https://www.ubereats.com/fr/store/mcdonalds-saint-pol-de-leon/EWQNkPHFUviyXnOHOFDWnA?diningMode=DELIVERY&surfaceName=",
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
