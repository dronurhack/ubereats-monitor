"""
scraper.py — Script principal de surveillance UberEats via ScraperAPI
Utilise l'API ScraperAPI pour le rendu JS et le bypass anti-bot Cloudflare.
"""

import logging
import os
import sqlite3
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from config import CITIES, DB_PATH, LOG_LEVEL, UNAVAILABILITY_SIGNALS

SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "033ddfe5d867ec0be6ee2dbbd19a4906")

# Configuration du logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ubereats-scraper")


# ─────────────────────────────────────────────
# BASE DE DONNÉES SQLITE
# ─────────────────────────────────────────────
def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                scanned_at   TEXT    NOT NULL,
                city         TEXT    NOT NULL,
                status       TEXT    NOT NULL,
                detection    TEXT,
                http_code    INTEGER DEFAULT 200,
                error        TEXT
            )
        """)
    log.info("Base de donnees initialisee : %s", db_path)
    return conn


def save_result(
    conn: sqlite3.Connection,
    city: str,
    status: str,
    detection: str = None,
    http_code: int = 200,
    error: str = None,
) -> None:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    with conn:
        conn.execute(
            """
            INSERT INTO scans (scanned_at, city, status, detection, http_code, error)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (now_utc, city, status, detection, http_code, error),
        )


# ─────────────────────────────────────────────
# NORMALISATION ET DÉTECTION
# ─────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """Passe en minuscule, supprime les accents, normalise les apostrophes."""
    if not text:
        return ""
    text = text.lower()
    text = text.replace("’", "'").replace("`", "'").replace("´", "'")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def detect_unavailability(raw_html: str, city_name: str) -> tuple[bool, str]:
    """Détecte les signaux d'indisponibilité dans le contenu HTML."""
    html_clean = normalize_text(raw_html)

    for signal in UNAVAILABILITY_SIGNALS:
        sig_clean = normalize_text(signal)
        if sig_clean in html_clean:
            log.info("[%s] Signal detecte : '%s'", city_name, signal)
            return True, signal

    return False, ""


# ─────────────────────────────────────────────
# SCRAPING VILLE VIA SCRAPERAPI (avec attente de rendu JS)
# ─────────────────────────────────────────────
def scrape_city(city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = city["url"]
    log.info("[%s] Scraping via ScraperAPI -> %s", city_name, url[:60] + "...")

    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": url,
        "render": "true",
        "country_code": "fr",
        "render_wait": "5000",  # Attendre 5 secondes que le JS insere les cartes McDo/Restos
    }
    endpoint = f"http://api.scraperapi.com?{urlencode(params)}"

    try:
        response = requests.get(endpoint, timeout=70)
        http_code = response.status_code
        raw_html = response.text or ""
        log.info("[%s] HTTP %s - Taille HTML : %d octets", city_name, http_code, len(raw_html))

        if http_code == 200 and len(raw_html) > 5000:
            is_unavailable, detection_phrase = detect_unavailability(raw_html, city_name)

            if is_unavailable:
                status = "INDISPONIBLE"
                log.warning("[%s] -- INDISPONIBLE -- Detecte via : '%s'", city_name, detection_phrase)
            else:
                status = "DISPONIBLE"
                log.info("[%s] ++ DISPONIBLE ++", city_name)

            save_result(
                conn,
                city=city_name,
                status=status,
                detection=detection_phrase if is_unavailable else None,
                http_code=200,
            )
        else:
            log.error("[%s] Erreur ou reponse trop courte (HTTP %s - %d octets)", city_name, http_code, len(raw_html))
            save_result(
                conn,
                city=city_name,
                status="ERREUR",
                http_code=http_code,
                error=f"HTML invalide ou HTTP {http_code}",
            )

    except Exception as e:
        log.error("[%s] ERREUR connexion ScraperAPI : %s", city_name, e)
        save_result(
            conn,
            city=city_name,
            status="ERREUR",
            http_code=0,
            error=str(e),
        )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> None:
    log.info("========================================")
    log.info("UberEats Monitor (ScraperAPI) — Demarrage du scan")
    log.info("Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("========================================")

    conn = init_db()

    for city in CITIES:
        scrape_city(city, conn)

    conn.close()
    log.info("========================================")
    log.info("Scan termine")
    log.info("========================================")


if __name__ == "__main__":
    main()