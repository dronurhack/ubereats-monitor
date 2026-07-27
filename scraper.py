"""
scraper.py — Script principal de surveillance UberEats
=======================================================
Ce script interroge UberEats pour chacune des villes configurées,
détecte si des livreurs sont disponibles, et enregistre le résultat
dans la base de données SQLite locale.

Usage local :
    SCRAPFLY_API_KEY=your_key python scraper.py

Usage GitHub Actions :
    Lancé automatiquement toutes les 10 minutes via scan.yml
"""

import base64
import json
import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone

# ── Imports optionnels (installés via requirements.txt) ──────────────────────
try:
    from scrapfly import ScrapeConfig, ScrapflyClient, ScrapeApiResponse
except ImportError:
    print("[ERREUR] Module 'scrapfly-sdk' non installé. Faites : pip install scrapfly-sdk")
    sys.exit(1)

from config import (
    CITIES,
    DB_PATH,
    SCRAPFLY_API_KEY,
    SCRAPFLY_OPTIONS,
    UNAVAILABILITY_SIGNALS,
    LOG_LEVEL,
)

# ─────────────────────────────────────────────
# CONFIGURATION DU LOGGER
# ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# BASE DE DONNÉES — Initialisation
# ─────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    """
    Crée (ou ouvre) la base SQLite et initialise la table 'scans'
    si elle n'existe pas encore.

    Schéma :
        id         — Identifiant unique auto-incrémenté
        city       — Nom de la ville
        scanned_at — Horodatage UTC ISO 8601 (ex: "2024-11-15T14:30:00+00:00")
        status     — "DISPONIBLE" ou "INDISPONIBLE"
        detection  — Phrase qui a déclenché la détection (ou NULL)
        url        — URL scrapée
        http_code  — Code HTTP retourné par Scrapfly
        error      — Message d'erreur éventuel (ou NULL)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            city        TEXT    NOT NULL,
            scanned_at  TEXT    NOT NULL,
            status      TEXT    NOT NULL CHECK(status IN ('DISPONIBLE', 'INDISPONIBLE', 'ERREUR')),
            detection   TEXT,
            url         TEXT,
            http_code   INTEGER,
            error       TEXT
        )
    """)
    # Index pour accélérer les requêtes par ville et par date
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_city_date ON scans(city, scanned_at)
    """)
    conn.commit()
    log.debug("Base de données initialisée : %s", DB_PATH)
    return conn


def save_result(
    conn: sqlite3.Connection,
    city: str,
    status: str,
    detection: str | None = None,
    url: str | None = None,
    http_code: int | None = None,
    error: str | None = None,
) -> None:
    """Insère un résultat de scan dans la BDD."""
    now_utc = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO scans (city, scanned_at, status, detection, url, http_code, error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (city, now_utc, status, detection, url, http_code, error),
    )
    conn.commit()
    log.info("[%s] Résultat sauvegardé : %s (détection: %s)", city, status, detection)


# ─────────────────────────────────────────────
# CONSTRUCTION DES URLS UBEREATS
# ─────────────────────────────────────────────
def build_ubereats_url(city: dict) -> str:
    """
    Construit l'URL UberEats pour une ville française donnée.

    UberEats encode la localisation dans le paramètre `pl` (base64 JSON).
    Format du JSON encodé :
        {"address": "Nom Ville", "location": {"latitude": X, "longitude": Y}}

    Exemple de résultat :
        https://www.ubereats.com/fr?pl=eyJhZGRyZXNzI...
    """
    location_payload = {
        "address": city["name"],
        "location": {
            "latitude": city["lat"],
            "longitude": city["lon"],
        },
    }
    encoded = base64.b64encode(json.dumps(location_payload).encode()).decode()
    url = f"https://www.ubereats.com/fr?pl={encoded}"
    log.debug("[%s] URL construite : %s", city["name"], url)
    return url


# ─────────────────────────────────────────────
# DÉTECTION DU MESSAGE D'INDISPONIBILITÉ
# ─────────────────────────────────────────────
def detect_unavailability(html_content: str) -> tuple[bool, str | None]:
    """
    Analyse le HTML rendu d'UberEats et cherche des signaux
    indiquant l'absence de livreurs ou de restaurants disponibles.

    Retourne :
        (True, phrase_détectée) si livreurs indisponibles
        (False, None)           si livreurs disponibles
    """
    content_lower = html_content.lower()

    for signal in UNAVAILABILITY_SIGNALS:
        if signal.lower() in content_lower:
            log.debug("Signal détecté : '%s'", signal)
            return True, signal

    # Détection complémentaire : page vide de restaurants
    # UberEats affiche généralement un compteur "X restaurants"
    restaurant_count_match = re.search(
        r'(\d+)\s*(restaurant|établissement|store)', content_lower
    )
    if restaurant_count_match:
        count = int(restaurant_count_match.group(1))
        if count == 0:
            return True, "0 restaurants trouvés"

    return False, None


# ─────────────────────────────────────────────
# SCRAPING D'UNE VILLE
# ─────────────────────────────────────────────
def scrape_city(client: ScrapflyClient, city: dict, conn: sqlite3.Connection) -> None:
    """
    Lance le scraping UberEats pour une ville et enregistre le résultat.

    En cas d'erreur réseau ou API, enregistre le statut 'ERREUR' sans planter.
    """
    city_name = city["name"]
    url = build_ubereats_url(city)

    log.info("[%s] Scraping en cours → %s", city_name, url[:80] + "...")

    try:
        # ── Appel Scrapfly ───────────────────────────────────────────────────
        result: ScrapeApiResponse = client.scrape(
            ScrapeConfig(
                url=url,
                asp=SCRAPFLY_OPTIONS["asp"],
                render_js=SCRAPFLY_OPTIONS["render_js"],
                proxy_pool=SCRAPFLY_OPTIONS["proxy_pool"],
                country=SCRAPFLY_OPTIONS["country"],
                wait_for_selector=SCRAPFLY_OPTIONS.get("wait_for_selector"),
                # Simuler un vrai navigateur
                headers={
                    "Accept-Language": "fr-FR,fr;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
        )

        http_code = result.context.get("status_code", 0)
        html = result.content or ""

        log.info("[%s] Réponse HTTP %s — Taille HTML : %d octets", city_name, http_code, len(html))

        # ── Analyse du contenu ───────────────────────────────────────────────
        is_unavailable, detection_phrase = detect_unavailability(html)

        if is_unavailable:
            status = "INDISPONIBLE"
            log.warning("[%s] ⚠️  INDISPONIBLE — Détecté via : '%s'", city_name, detection_phrase)
        else:
            status = "DISPONIBLE"
            log.info("[%s] ✅  DISPONIBLE", city_name)

        save_result(
            conn,
            city=city_name,
            status=status,
            detection=detection_phrase,
            url=url,
            http_code=http_code,
        )

    except Exception as exc:
        error_msg = str(exc)
        log.error("[%s] ❌  Erreur scraping : %s", city_name, error_msg)
        save_result(
            conn,
            city=city_name,
            status="ERREUR",
            error=error_msg,
            url=url,
        )


# ─────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ─────────────────────────────────────────────
def main():
    # ── Vérification de la clé API ───────────────────────────────────────────
    if not SCRAPFLY_API_KEY:
        log.error(
            "Clé API Scrapfly manquante ! "
            "Définissez la variable d'environnement SCRAPFLY_API_KEY."
        )
        sys.exit(1)

    log.info("═══════════════════════════════════════════")
    log.info("  UberEats Monitor — Démarrage du scan")
    log.info("  Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("═══════════════════════════════════════════")

    # ── Initialisation BDD ───────────────────────────────────────────────────
    conn = init_db()

    # ── Initialisation client Scrapfly ───────────────────────────────────────
    client = ScrapflyClient(key=SCRAPFLY_API_KEY)

    # ── Scraping de chaque ville ─────────────────────────────────────────────
    for city in CITIES:
        scrape_city(client, city, conn)

    conn.close()
    log.info("═══════════════════════════════════════════")
    log.info("  Scan terminé ✓")
    log.info("═══════════════════════════════════════════")


if __name__ == "__main__":
    main()
