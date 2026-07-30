"""
scraper.py — Script principal de surveillance UberEats
Interroge Scrapfly pour chaque ville et détecte les messages d'indisponibilité de livreurs.
Lance ce script via GitHub Actions (voir .github/workflows/scan.yml).
"""

import base64
import json
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

# Mode debug optionnel
debug_mode = os.environ.get("DEBUG_MODE", "0") == "1"


# ─────────────────────────────────────────────
# UTILITAIRES DE TEXTE & HTML
# ─────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """
    Nettoie et normalise le texte pour une comparaison sans échec :
    - Supprime les accents (à → a, é → e...)
    - Remplace les apostrophes spéciales par apostrophe simple
    - Convertit en minuscules
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


# ─────────────────────────────────────────────
# URL & DÉTECTION
# ─────────────────────────────────────────────
def build_ubereats_url(city: dict) -> str:
    """Construit l'URL UberEats pour la ville donnée avec localisation encodée."""
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
    return f"https://www.ubereats.com/fr/city/{city['slug']}?pl={pl_encoded}"


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
    # Migration automatique si l'ancienne table n'a pas la colonne 'url'
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
def scrape_single_url(client: ScrapflyClient, url: str) -> tuple[int, str]:
    """Scrape une URL unique via Scrapfly et retourne (http_code, html_content)."""
    result: ScrapeApiResponse = client.scrape(
        ScrapeConfig(
            url=url,
            asp=SCRAPFLY_OPTIONS["asp"],
            render_js=SCRAPFLY_OPTIONS["render_js"],
            proxy_pool=SCRAPFLY_OPTIONS["proxy_pool"],
            country=SCRAPFLY_OPTIONS["country"],
            wait_for_selector=SCRAPFLY_OPTIONS.get("wait_for_selector"),
            headers={
                "Accept-Language": "fr-FR,fr;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
    )
    return result.context.get("status_code", 0), result.content or ""


def scrape_city(client: ScrapflyClient, city: dict, conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    store_url = city.get("url")
    city_url = build_ubereats_url(city)

    # On privilégie l'URL directe du magasin principal s'il existe, sinon l'URL de ville
    urls_to_check = [u for u in [store_url, city_url] if u]
    
    log.info("[%s] Verification sur %d URL(s)...", city_name, len(urls_to_check))

    is_unavailable = False
    detection_phrase = None
    last_http_code = 200
    used_url = urls_to_check[0]

    try:
        for url in urls_to_check:
            log.info("[%s] Scraping -> %s", city_name, url[:70] + "...")
            http_code, raw_html = scrape_single_url(client, url)
            last_http_code = http_code
            used_url = url

            unavail, phrase = detect_unavailability(raw_html, city_name)
            if unavail:
                is_unavailable = True
                detection_phrase = phrase
                log.warning("[%s] Signal detecte sur %s: '%s'", city_name, url[:60], phrase)
                break

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
            url=used_url,
            http_code=last_http_code,
        )

    except Exception as exc:
        error_msg = str(exc)
        log.error("[%s] ❌  Erreur scraping : %s", city_name, error_msg)
        save_result(
            conn,
            city=city_name,
            status="ERREUR",
            error=error_msg,
            url=used_url,
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