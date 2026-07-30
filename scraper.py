"""
scraper.py — Script principal de surveillance UberEats
Interroge Scrapfly pour chaque ville et détecte les messages d'indisponibilité de livreurs.
"""

import logging
import os
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser

from scrapfly import ScrapflyClient, ScrapeConfig, ScrapeApiResponse

from config import (
    CITIES,
    DB_PATH,
    LOG_LEVEL,
    SCRAPFLY_API_KEY,
    SCRAPFLY_OPTIONS,
    UNAVAILABILITY_SIGNALS,
)

# ─────────────────────────────────────────────
# CONFIGURATION DU LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────────
# UTILITAIRES DE TEXTE & HTML
# ─────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """
    Nettoie et normalise le texte :
    - Supprime les accents
    - Normalise apostrophes et minuscules
    """
    text = text.replace("&agrave;", "a").replace("&eacute;", "e")
    text = text.replace("&egrave;", "e").replace("&ecirc;", "e")
    text = text.replace("&ocirc;", "o").replace("&ucirc;", "u")
    text = text.replace("&ccedil;", "c").replace("&nbsp;", " ")
    text = text.replace("’", "'").replace("`", "'")
    text = text.replace("\u2019", "'").replace("\u0060", "'")
    
    nfkd = unicodedata.normalize("NFKD", text)
    text = "".join([c for c in nfkd if not unicodedata.combining(c)])

    return text.lower()


class VisibleTextExtractor(HTMLParser):
    """Extrait uniquement le texte visible d'une page HTML."""
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


def extract_visible_text(html_content: str) -> str:
    extractor = VisibleTextExtractor()
    try:
        extractor.feed(html_content)
    except Exception:
        pass
    return extractor.get_text()


def extract_script_json_text(html_content: str) -> str:
    import re
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html_content, re.DOTALL | re.IGNORECASE)
    return " ".join(scripts)


def detect_unavailability(html_content: str, city_name: str) -> tuple[bool, str | None]:
    """Cherche les signaux d'indisponibilité de livreurs dans le HTML."""
    visible_text = extract_visible_text(html_content)
    normalized_visible = normalize_text(visible_text)

    for signal in UNAVAILABILITY_SIGNALS:
        if normalize_text(signal) in normalized_visible:
            return True, signal

    script_text = extract_script_json_text(html_content)
    normalized_scripts = normalize_text(script_text)

    for signal in UNAVAILABILITY_SIGNALS:
        if normalize_text(signal) in normalized_scripts:
            return True, signal

    normalized_raw = normalize_text(html_content)
    for signal in UNAVAILABILITY_SIGNALS:
        if normalize_text(signal) in normalized_raw:
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
    if "url" not in columns:
        try:
            conn.execute("ALTER TABLE scans ADD COLUMN url TEXT")
        except Exception:
            pass
    if "http_code" not in columns:
        try:
            conn.execute("ALTER TABLE scans ADD COLUMN http_code INTEGER")
        except Exception:
            pass

    conn.execute("CREATE INDEX IF NOT EXISTS idx_city_date ON scans(city, scanned_at)")
    conn.commit()
    return conn


def save_result(
    conn: sqlite3.Connection,
    city: str,
    status: str,
    url: str | None = None,
    detection: str | None = None,
    error: str | None = None,
    http_code: int | None = None,
) -> None:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO scans (city, scanned_at, status, detection, url, http_code, error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (city, now_utc, status, detection, url, http_code, error),
    )
    conn.commit()


# ─────────────────────────────────────────────
# EXÉCUTION DU SCRAPING
# ─────────────────────────────────────────────
def scrape_city(client: ScrapflyClient, city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = city["url"]
    
    log.info("[%s] Scraping -> %s", city_name, url[:75] + "...")

    try:
        result: ScrapeApiResponse = client.scrape(
            ScrapeConfig(
                url=url,
                asp=SCRAPFLY_OPTIONS["asp"],
                render_js=SCRAPFLY_OPTIONS["render_js"],
                rendering_wait=SCRAPFLY_OPTIONS.get("rendering_wait", 3000),
                proxy_pool=SCRAPFLY_OPTIONS["proxy_pool"],
                country=SCRAPFLY_OPTIONS["country"],
                headers={
                    "Accept-Language": "fr-FR,fr;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
        )

        http_code = result.context.get("status_code", 0)
        raw_html = result.content or ""

        is_unavailable, detection_phrase = detect_unavailability(raw_html, city_name)

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


def main():
    if not SCRAPFLY_API_KEY:
        log.error("Clé API Scrapfly manquante !")
        sys.exit(1)

    log.info("═══════════════════════════════════════════")
    log.info("  UberEats Monitor — Démarrage du scan")
    log.info("  Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("═══════════════════════════════════════════")

    conn = init_db()
    client = ScrapflyClient(key=SCRAPFLY_API_KEY)

    for city in CITIES:
        scrape_city(client, city, conn)

    conn.close()
    log.info("═══════════════════════════════════════════")
    log.info("  Scan terminé ✓")
    log.info("═══════════════════════════════════════════")


if __name__ == "__main__":
    main()