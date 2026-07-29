"""
config.py — Configuration centrale du projet UberEats Monitor
"""

import os

# ─────────────────────────────────────────────
# VILLES À SURVEILLER (URLs exactes Uber Eats)
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
# BASE DE DONNÉES ET LOGS
# ─────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/history.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# ─────────────────────────────────────────────
# PHRASES / MOTS-CLÉS DE DÉTECTION D'INDISPONIBILITÉ
# ─────────────────────────────────────────────
UNAVAILABILITY_SIGNALS = [
    "aucun coursier a proximite",
    "aucun coursier à proximité",
    "aucun coursier disponible",
    "indisponible pour le moment",
    "plus de livreurs",
    "pas de livreurs",
    "service indisponible",
    "indisponible",
]
