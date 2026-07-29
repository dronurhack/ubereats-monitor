"""
scraper.py — Script principal de surveillance UberEats via curl_cffi (100% Gratuit & Anti-Bot Bypass)
Imite la signature TLS/JA3 exacte d'un vrai navigateur Chrome pour contourner Cloudflare.
"""

import logging
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

from curl_cffi import requests

from config import CITIES, DB_PATH, LOG_LEVEL, UNAVAILABILITY_SIGNALS

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
# SCRAPING VILLE VIA CURL_CFFI (TLS IMPERSONATE)
# ─────────────────────────────────────────────
def scrape_city(session: requests.Session, city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = city["url"]
    log.info("[%s] Scraping -> %s", city_name, url[:80] + "...")

    try:
        # Requete HTTP avec impersonation TLS Chrome 120
        response = session.get(
            url,
            impersonate="chrome120",
            timeout=20,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
                "Cache-Control": "max-age=0",
                "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Site": "none",
                "Sec-Fetch-User": "?1",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        http_code = response.status_code
        raw_html = response.text or ""
        log.info("[%s] HTTP %s - Taille HTML : %d octets", city_name, http_code, len(raw_html))

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
            http_code=http_code,
        )

    except Exception as e:
        log.error("[%s] ERREUR scraping : %s", city_name, e)
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
    log.info("UberEats Monitor (curl_cffi TLS Impersonate) — Demarrage du scan")
    log.info("Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("========================================")

    conn = init_db()

    session = requests.Session()

    for city in CITIES:
        scrape_city(session, city, conn)

    conn.close()
    log.info("========================================")
    log.info("Scan termine")
    log.info("========================================")


if __name__ == "__main__":
    main()