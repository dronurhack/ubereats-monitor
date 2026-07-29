"""
scraper.py — Script principal de surveillance UberEats via Playwright (100% Gratuit)
Interroge Uber Eats directement avec un vrai navigateur Headless Chromium.
"""

import logging
import os
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

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
# SCRAPING VILLE VIA PLAYWRIGHT
# ─────────────────────────────────────────────
def scrape_city(context, city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = city["url"]
    log.info("[%s] Scraping -> %s", city_name, url[:80] + "...")

    page = context.new_page()

    try:
        # Masquer les indicateurs automation / webdriver
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
        http_code = response.status if response else 200

        # Attente pour l'exécution dynamique JS
        page.wait_for_timeout(4000)

        raw_html = page.content()
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
    finally:
        page.close()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> None:
    log.info("========================================")
    log.info("UberEats Monitor (Playwright) — Demarrage du scan")
    log.info("Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("========================================")

    conn = init_db()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )

        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, Gecko) Chrome/123.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
            viewport={"width": 1280, "height": 800},
        )

        for city in CITIES:
            scrape_city(context, city, conn)

        context.close()
        browser.close()

    conn.close()
    log.info("========================================")
    log.info("Scan termine")
    log.info("========================================")


if __name__ == "__main__":
    main()
