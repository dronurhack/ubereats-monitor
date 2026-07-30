"""
scraper.py — Surveillance UberEats via ScraperAPI (render JS)
Détecte "Aucun coursier à proximité" sur les pages McDonald's de chaque ville.
"""

import logging
import os
import sqlite3
import sys
import time
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser

import requests

from config import (
    CITIES,
    DB_PATH,
    LOG_LEVEL,
    UNAVAILABILITY_SIGNALS,
)

# ─────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────
SCRAPERAPI_KEY = os.getenv("SCRAPERAPI_KEY", "033ddfe5d867ec0be6ee2dbbd19a4906")

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


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


class VisibleTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.result = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "head"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.result.append(stripped)

    def get_text(self) -> str:
        return " ".join(self.result)


def extract_visible_text(html: str) -> str:
    ext = VisibleTextExtractor()
    try:
        ext.feed(html)
    except Exception:
        pass
    return ext.get_text()


def detect_unavailability(html: str) -> tuple[bool, str | None]:
    """
    Cherche les signaux d'indisponibilité UNIQUEMENT dans le texte visible.
    On ne cherche PAS dans le HTML brut pour éviter les faux positifs
    provenant du JSON React embarqué dans les balises <script>.
    """
    visible_text = extract_visible_text(html)
    normalized = normalize_text(visible_text)

    for signal in UNAVAILABILITY_SIGNALS:
        norm_signal = normalize_text(signal)
        if norm_signal in normalized:
            return True, signal

    return False, None


# ─────────────────────────────────────────────
# SCRAPERAPI — Requête HTTP simple
# ─────────────────────────────────────────────
def scrape_url(target_url: str) -> tuple[int, str]:
    """
    Appelle ScraperAPI avec rendu JavaScript activé.
    Retourne (http_status, html_content).
    """
    params = {
        "api_key": SCRAPERAPI_KEY,
        "url": target_url,
        "render": "true",
        "country_code": "fr",
        "wait_for_selector": "main",
        "device_type": "desktop",
    }
    resp = requests.get(
        "https://api.scraperapi.com",
        params=params,
        timeout=60,
    )
    return resp.status_code, resp.text


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
# SCRAPING PRINCIPAL
# ─────────────────────────────────────────────
def scrape_city(city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = city["url"]
    log.info("[%s] Scraping → %s", city_name, url[:80])

    try:
        http_code, html = scrape_url(url)
        html_len = len(html)
        log.info("[%s] HTTP %s — %d octets reçus", city_name, http_code, html_len)

        # Debug : afficher le texte visible pour vérifier ce que ScraperAPI voit
        visible = extract_visible_text(html)
        normalized = normalize_text(visible)
        log.info("[%s] TEXTE VISIBLE (extrait): ...%s...", city_name, normalized[:300])

        is_unavail, phrase = detect_unavailability(html)

        if is_unavail:
            status = "INDISPONIBLE"
            log.warning("[%s] ⚠️  INDISPONIBLE — Détecté: '%s'", city_name, phrase)
        else:
            status = "DISPONIBLE"
            log.info("[%s] ✅  DISPONIBLE", city_name)

        save_result(conn, city_name, status, url=url, detection=phrase, http_code=http_code)

    except Exception as exc:
        log.error("[%s] ❌ Erreur: %s", city_name, str(exc))
        save_result(conn, city_name, "ERREUR", url=url, error=str(exc))


def main():
    if not SCRAPERAPI_KEY:
        log.error("Clé SCRAPERAPI_KEY manquante !")
        sys.exit(1)

    log.info("═══════════════════════════════════════════")
    log.info("  UberEats Monitor — Démarrage du scan")
    log.info("  Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("  API : ScraperAPI (render JS activé)")
    log.info("═══════════════════════════════════════════")

    conn = init_db()

    for city in CITIES:
        scrape_city(city, conn)
        time.sleep(2)

    conn.close()
    log.info("═══════════════════════════════════════════")
    log.info("  Scan terminé ✓")
    log.info("═══════════════════════════════════════════")


if __name__ == "__main__":
    main()