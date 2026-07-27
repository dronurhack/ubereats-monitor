"""
scraper.py — Script principal de surveillance UberEats
Interroge Scrapfly pour chaque ville et detecte les messages d'indisponibilite de livreurs.
Lance ce script via GitHub Actions (voir .github/workflows/scan.yml).
"""

import logging
import os
import re
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

# Configuration du logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# Mode debug : mettre DEBUG_MODE=1 dans GitHub Actions pour sauvegarder le HTML
debug_mode = os.environ.get("DEBUG_MODE", "0") == "1"


# ─────────────────────────────────────────────
# NORMALISATION DU TEXTE
# ─────────────────────────────────────────────
def normalize_text(text: str) -> str:
    """
    Nettoie le texte pour une comparaison robuste :
    - Remplace les entites HTML (agrave, eacute...)
    - Supprime tous les accents (a -> a, e -> e, o -> o)
    - Normalise les apostrophes
    - Convertit en minuscules
    """
    # Entites HTML courantes
    replacements = {
        "&agrave;": "a", "&eacute;": "e", "&egrave;": "e",
        "&ecirc;": "e", "&ocirc;": "o", "&ucirc;": "u",
        "&ccedil;": "c", "&nbsp;": " ", "&rsquo;": "'",
        "&lsquo;": "'", "&apos;": "'",
    }
    for entity, replacement in replacements.items():
        text = text.replace(entity, replacement)

    # Apostrophes unicode diverses -> apostrophe simple
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u0060", "'").replace("\u00b4", "'")

    # Normalisation NFKD : decompose les caracteres accentues
    nfkd = unicodedata.normalize("NFKD", text)
    # Supprime les marques diacritiques (accents)
    text = "".join([c for c in nfkd if not unicodedata.combining(c)])

    return text.lower()


# ─────────────────────────────────────────────
# EXTRACTION DU TEXTE VISIBLE
# ─────────────────────────────────────────────
class VisibleTextExtractor(HTMLParser):
    """Extrait uniquement le texte visible (ignore script, style, head)."""

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


def extract_script_text(html_content: str) -> str:
    """Extrait le contenu des balises <script> (donnees JSON embarquees)."""
    scripts = re.findall(
        r"<script[^>]*>(.*?)</script>",
        html_content,
        re.DOTALL | re.IGNORECASE
    )
    return " ".join(scripts)


# Les URLs sont directement definies dans config.py (city["url"])
# Pas besoin de constructeur — on utilise les URLs exactes fournies par l'utilisateur.


# ─────────────────────────────────────────────
# DETECTION DU MESSAGE D'INDISPONIBILITE
# ─────────────────────────────────────────────
def detect_unavailability(html_content: str, city_name: str):
    """
    Cherche les signaux d'indisponibilite dans le HTML.
    Retourne (True, signal_trouve) ou (False, None).
    Cherche dans : texte visible → contenu scripts → HTML brut.
    """
    # 1. Texte visible (balises affichees a l'ecran)
    visible_text = extract_visible_text(html_content)
    normalized_visible = normalize_text(visible_text)

    if debug_mode:
        log.debug("[%s] TEXTE VISIBLE (500 premiers chars) : %s",
                  city_name, normalized_visible[:500])

    for signal in UNAVAILABILITY_SIGNALS:
        normalized_signal = normalize_text(signal)
        if normalized_signal in normalized_visible:
            log.debug("[%s] Signal dans texte visible : '%s'", city_name, signal)
            return True, signal

    # 2. Contenu des balises <script> (donnees JSON/SSR)
    script_text = extract_script_text(html_content)
    normalized_scripts = normalize_text(script_text)

    for signal in UNAVAILABILITY_SIGNALS:
        normalized_signal = normalize_text(signal)
        if normalized_signal in normalized_scripts:
            log.debug("[%s] Signal dans scripts : '%s'", city_name, signal)
            return True, signal

    # 3. HTML brut complet (dernier recours)
    normalized_raw = normalize_text(html_content)
    for signal in UNAVAILABILITY_SIGNALS:
        normalized_signal = normalize_text(signal)
        if normalized_signal in normalized_raw:
            log.debug("[%s] Signal dans HTML brut : '%s'", city_name, signal)
            return True, signal

    return False, None


# ─────────────────────────────────────────────
# BASE DE DONNEES SQLite
# ─────────────────────────────────────────────
def init_db() -> sqlite3.Connection:
    """Cree ou ouvre la base SQLite et initialise la table 'scans'."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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
    conn.execute("CREATE INDEX IF NOT EXISTS idx_city_date ON scans(city, scanned_at)")
    conn.commit()
    log.info("Base de donnees initialisee : %s", DB_PATH)
    return conn


def save_result(
    conn: sqlite3.Connection,
    city: str,
    status: str,
    url=None,
    detection=None,
    error=None,
    http_code=None,
) -> None:
    """Enregistre un resultat de scan dans la base de donnees."""
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn.execute(
        """
        INSERT INTO scans (city, scanned_at, status, detection, url, http_code, error)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (city, now_utc, status, detection, url, http_code, error),
    )
    conn.commit()
    log.info("[%s] Sauvegarde : %s (detection=%s)", city, status, detection)


# ─────────────────────────────────────────────
# SCRAPING D'UNE VILLE
# ─────────────────────────────────────────────
def scrape_city(client: ScrapflyClient, city: dict, conn: sqlite3.Connection) -> None:
    """Lance le scraping UberEats pour une ville et enregistre le resultat."""
    city_name = city["name"]
    url = city["url"]  # URL exacte definie dans config.py
    log.info("[%s] Scraping -> %s", city_name, url[:90] + "...")

    try:
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

        http_code = result.context.get("status_code", 0)
        raw_html = result.content or ""
        log.info("[%s] HTTP %s - Taille HTML : %d octets", city_name, http_code, len(raw_html))

        # Sauvegarde debug si demande
        if debug_mode:
            debug_path = "data/debug_" + city["slug"] + ".txt"
            os.makedirs("data", exist_ok=True)
            with open(debug_path, "w", encoding="utf-8") as f:
                visible = extract_visible_text(raw_html)
                f.write("=== TEXTE VISIBLE ===\n")
                f.write(visible[:8000])
                f.write("\n\n=== HTML BRUT (premiers 5000 chars) ===\n")
                f.write(raw_html[:5000])
            log.info("[%s] Debug sauvegarde dans %s", city_name, debug_path)

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
            detection=detection_phrase,
            url=url,
            http_code=http_code,
        )

    except Exception as exc:
        error_msg = str(exc)
        log.error("[%s] ERREUR scraping : %s", city_name, error_msg)
        save_result(conn, city=city_name, status="ERREUR", error=error_msg, url=url)


# ─────────────────────────────────────────────
# POINT D'ENTREE PRINCIPAL
# ─────────────────────────────────────────────
def main():
    if not SCRAPFLY_API_KEY:
        log.error("Cle API Scrapfly manquante ! Definissez SCRAPFLY_API_KEY.")
        sys.exit(1)

    log.info("==========================================")
    log.info("  UberEats Monitor - Demarrage du scan")
    log.info("  Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("  Villes : %s", ", ".join(c["name"] for c in CITIES))
    log.info("  Mode debug : %s", "OUI" if debug_mode else "NON")
    log.info("==========================================")

    conn = init_db()
    client = ScrapflyClient(key=SCRAPFLY_API_KEY)

    for city in CITIES:
        scrape_city(client, city, conn)

    conn.close()
    log.info("==========================================")
    log.info("  Scan termine")
    log.info("==========================================")


if __name__ == "__main__":
    main()
