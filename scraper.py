"""
scraper.py — Surveillance UberEats via Playwright (100% Gratuit, Illimité, sans API payante)
Détecte "Aucun coursier à proximité" sur les pages McDonald's de chaque ville.
Force la bonne adresse de livraison via le paramètre pl= dans l'URL.
"""

import base64
import json
import logging
import os
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

from config import (
    CITIES,
    DB_PATH,
    LOG_LEVEL,
    UNAVAILABILITY_SIGNALS,
)

# ─────────────────────────────────────────────
# CONFIGURATION LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# CONSTRUCTION URL AVEC LOCALISATION FORCÉE
# ─────────────────────────────────────────────
def build_store_url(city: dict) -> str:
    """
    Construit l'URL du store McDonald's avec le paramètre pl= qui force
    l'adresse de livraison dans la bonne ville.
    """
    location_payload = {
        "addressLine1": city["name"],
        "addressLine2": "France",
        "city": city["name"],
        "country": "FR",
        "countryIso2": "FR",
        "latitude": city["lat"],
        "longitude": city["lon"],
    }
    pl_encoded = base64.urlsafe_b64encode(
        json.dumps(location_payload, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")

    return f"{city['store_url']}?diningMode=DELIVERY&pl={pl_encoded}"


# ─────────────────────────────────────────────
# UTILITAIRES DE TEXTE
# ─────────────────────────────────────────────
def normalize_text(text: str) -> str:
    text = text.replace("&agrave;", "a").replace("&eacute;", "e")
    text = text.replace("&egrave;", "e").replace("&ecirc;", "e")
    text = text.replace("&ocirc;", "o").replace("&ucirc;", "u")
    text = text.replace("&ccedil;", "c").replace("&nbsp;", " ")
    text = text.replace("\u2019", "'").replace("\u0060", "'")
    text = text.replace("\u2018", "'")
    text = text.replace("'", "'").replace("`", "'")
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return text.lower()


def detect_unavailability(visible_text: str) -> tuple[bool, str | None]:
    """
    Cherche les signaux d'indisponibilité dans le texte visible capturé par Playwright.
    """
    normalized = normalize_text(visible_text)

    for signal in UNAVAILABILITY_SIGNALS:
        norm_signal = normalize_text(signal)
        if norm_signal in normalized:
            return True, signal

    return False, None


# ─────────────────────────────────────────────
# BASE DE DONNÉES
# ─────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
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
    cursor = conn.execute("PRAGMA table_info(scans)")
    columns = [row[1] for row in cursor.fetchall()]
    for col, col_type in [("url", "TEXT"), ("http_code", "INTEGER"), ("error", "TEXT")]:
        if col not in columns:
            try:
                conn.execute(f"ALTER TABLE scans ADD COLUMN {col} {col_type}")
            except Exception:
                pass
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city_date ON scans(city, scanned_at)")
    conn.commit()
    return conn


def save_result(conn, city, status, url=None, detection=None, error=None, http_code=None):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        "INSERT INTO scans (city, scanned_at, status, detection, url, http_code, error) VALUES (?,?,?,?,?,?,?)",
        (city, now_utc, status, detection, url, http_code, error),
    )
    conn.commit()


# ─────────────────────────────────────────────
# SCRAPING PLAYWRIGHT (Navigateur Chromium réel)
# ─────────────────────────────────────────────
def scrape_city(page, city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = build_store_url(city)
    log.info("[%s] Navigation Playwright → %s", city_name, url[:100])

    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        http_code = response.status if response else 200

        # Attente d'un court délai pour laisser les composants JS réactifs charger
        page.wait_for_timeout(3000)

        visible_text = page.inner_text("body")
        normalized = normalize_text(visible_text)
        log.info("[%s] TEXTE VISIBLE (extrait): %s", city_name, normalized[:300])

        is_unavail, phrase = detect_unavailability(visible_text)

        if is_unavail:
            status = "INDISPONIBLE"
            log.warning("[%s] ⚠️  INDISPONIBLE — Détecté: '%s'", city_name, phrase)
        else:
            status = "DISPONIBLE"
            log.info("[%s] ✅  DISPONIBLE", city_name)

        save_result(conn, city_name, status, url=url, detection=phrase, http_code=http_code)

    except Exception as exc:
        log.error("[%s] ❌ Erreur Playwright: %s", city_name, str(exc))
        save_result(conn, city_name, "ERREUR", url=url, error=str(exc))


def main():
    log.info("═══════════════════════════════════════════")
    log.info("  UberEats Monitor — Démarrage du scan (Playwright)")
    log.info("  Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("  Navigateur : Chromium Headless (0€ / Illimité)")
    log.info("═══════════════════════════════════════════")

    conn = init_db()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            locale="fr-FR",
            timezone_id="Europe/Paris",
        )
        page = context.new_page()

        for city in CITIES:
            scrape_city(page, city, conn)

        browser.close()

    conn.close()
    log.info("═══════════════════════════════════════════")
    log.info("  Scan terminé ✓")
    log.info("═══════════════════════════════════════════")


if __name__ == "__main__":
    main()