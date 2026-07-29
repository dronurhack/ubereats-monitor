"""
scraper.py — Script principal de surveillance UberEats via curl_cffi + Proxies Gratuits Optims
Utilise la rotation de proxies HTTPS et d'empreintes TLS Chrome pour contourner Cloudflare.
"""

import logging
import os
import random
import re
import sqlite3
import sys
import time
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
# LISTE DES PROXIES GRATUITS & ROTATION
# ─────────────────────────────────────────────
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all.txt",
]


def fetch_free_proxies() -> list[str]:
    """Récupère une liste dynamique de proxies publics HTTP/HTTPS gratuits."""
    proxies = []
    log.info("Recuperation des proxies gratuits...")
    session = requests.Session()
    for source in PROXY_SOURCES:
        try:
            r = session.get(source, timeout=4)
            if r.status_code == 200:
                lines = r.text.splitlines()
                for line in lines:
                    line = line.strip()
                    if line and ":" in line and not line.startswith("#"):
                        proxies.append(f"http://{line}")
        except Exception:
            continue
    log.info("%d proxies gratuits charges.", len(proxies))
    random.shuffle(proxies)
    return proxies


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
# SCRAPING VILLE AVEC ROTATION PROXY ULTRA-RAPIDE
# ─────────────────────────────────────────────
def scrape_city(city: dict, proxies: list[str], conn: sqlite3.Connection) -> None:
    city_name = city["name"]
    url = city["url"]
    log.info("[%s] Scraping -> %s", city_name, url[:80] + "...")

    max_attempts = 30
    http_code = 0
    raw_html = ""
    last_error = None

    for attempt in range(max_attempts):
        proxy = None if attempt == 0 else (proxies[attempt % len(proxies)] if proxies else None)
        proxy_str = proxy if proxy else "DIRECT"

        try:
            session = requests.Session()
            response = session.get(
                url,
                impersonate="chrome120",
                proxies={"http": proxy, "https": proxy} if proxy else None,
                timeout=2.5,  # Ultra-fast timeout pour zapper les mauvais proxies en < 2.5s
                headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8",
                    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
                    "Sec-Ch-Ua-Mobile": "?0",
                    "Sec-Ch-Ua-Platform": '"Windows"',
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Upgrade-Insecure-Requests": "1",
                }
            )

            http_code = response.status_code
            raw_html = response.text or ""

            if http_code == 200 and len(raw_html) > 5000:
                log.info("[%s] Succes via %s (HTTP 200 - %d octets)", city_name, proxy_str, len(raw_html))
                break
            else:
                log.warning("[%s] Echec via %s (HTTP %s - %d octets)", city_name, proxy_str, http_code, len(raw_html))

        except Exception as e:
            last_error = str(e)

    if http_code == 200 and len(raw_html) > 5000:
        is_unavailable, detection_phrase = detect_unavailability(raw_html, city_name)
        status = "INDISPONIBLE" if is_unavailable else "DISPONIBLE"
        save_result(
            conn,
            city=city_name,
            status=status,
            detection=detection_phrase if is_unavailable else None,
            http_code=200,
        )
    else:
        log.error("[%s] Requete non aboutie apres %d essais.", city_name, max_attempts)
        save_result(
            conn,
            city=city_name,
            status="ERREUR",
            http_code=http_code or 403,
            error=last_error or "Cloudflare 403 / IP Blocked",
        )


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> None:
    log.info("========================================")
    log.info("UberEats Monitor (Rotation Proxies Gratuits) — Demarrage")
    log.info("Heure UTC : %s", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
    log.info("========================================")

    conn = init_db()
    proxies = fetch_free_proxies()

    for city in CITIES:
        scrape_city(city, proxies, conn)

    conn.close()
    log.info("========================================")
    log.info("Scan termine")
    log.info("========================================")


if __name__ == "__main__":
    main()