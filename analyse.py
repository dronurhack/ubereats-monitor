"""
analyse.py — Analyse des données de surveillance UberEats
==========================================================
Ce script lit l'historique de la base SQLite et génère un rapport
des créneaux horaires les plus fréquents de pénurie de livreurs,
par ville et par jour de semaine.

Usage :
    python analyse.py
    python analyse.py --ville Lesneven
    python analyse.py --jours 14    (analyser les 14 derniers jours)
    python analyse.py --export csv  (exporter en CSV en plus du rapport)
"""

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import DB_PATH, CITIES

# ── Noms des jours en français ────────────────────────────────────────────────
JOURS_FR = {
    0: "Lundi",
    1: "Mardi",
    2: "Mercredi",
    3: "Jeudi",
    4: "Vendredi",
    5: "Samedi",
    6: "Dimanche",
}


def load_data(
    db_path: str,
    city_filter: str | None = None,
    jours: int | None = None,
) -> list[dict]:
    """
    Charge les données de scan depuis la BDD SQLite.

    Args:
        db_path:     Chemin vers la base SQLite
        city_filter: Si renseigné, filtre sur ce nom de ville uniquement
        jours:       Si renseigné, ne charge que les N derniers jours

    Returns:
        Liste de dicts avec les clés : city, scanned_at, status
    """
    if not Path(db_path).exists():
        print(f"[ERREUR] Base de données introuvable : {db_path}")
        print("         Lancez d'abord scraper.py pour collecter des données.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = "SELECT city, scanned_at, status FROM scans WHERE status != 'ERREUR'"
    params = []

    if city_filter:
        query += " AND city = ?"
        params.append(city_filter)

    if jours:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=jours)).isoformat()
        query += " AND scanned_at >= ?"
        params.append(cutoff)

    query += " ORDER BY scanned_at ASC"
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return rows


def compute_stats(rows: list[dict]) -> dict:
    """
    Calcule les statistiques de pénurie par ville, jour, et heure.

    Retourne un dict structuré :
    {
        "Lesneven": {
            (2, 12): {"total": 10, "indisponibles": 7, "pct": 70.0},
            (5, 19): {"total": 8,  "indisponibles": 8, "pct": 100.0},
            ...
        },
        ...
    }
    Les clés du sous-dict sont des tuples (jour_semaine 0-6, heure 0-23).
    """
    # Compteurs : [indisponibles, total]
    counters: dict[str, dict[tuple, list]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))

    for row in rows:
        city = row["city"]
        dt_str = row["scanned_at"]
        status = row["status"]

        # Parser l'horodatage (format ISO 8601 avec timezone)
        try:
            # Compatible Python 3.7+ avec timezone offset
            dt = datetime.fromisoformat(dt_str)
            # Convertir en heure locale France (UTC+1 hiver, UTC+2 été)
            # Pour simplifier on utilise UTC+2 (heure d'été bretonne)
            dt_local = dt.astimezone(timezone(timedelta(hours=2)))
        except ValueError:
            continue

        jour = dt_local.weekday()   # 0=Lundi ... 6=Dimanche
        heure = dt_local.hour

        key = (jour, heure)
        counters[city][key][1] += 1  # total

        if status == "INDISPONIBLE":
            counters[city][key][0] += 1  # indisponible

    # Convertir en pourcentages
    stats = {}
    for city, slots in counters.items():
        stats[city] = {}
        for (jour, heure), (indisponibles, total) in slots.items():
            pct = round(100 * indisponibles / total, 1) if total > 0 else 0.0
            stats[city][(jour, heure)] = {
                "total": total,
                "indisponibles": indisponibles,
                "pct": pct,
            }

    return stats


def print_report(stats: dict, top_n: int = 10) -> None:
    """Affiche le rapport dans le terminal avec un formatage lisible."""

    print("\n" + "═" * 60)
    print("  RAPPORT UberEats Monitor — Créneaux de pénurie de livreurs")
    print("═" * 60)

    if not stats:
        print("  Aucune donnée disponible.")
        return

    for city, slots in sorted(stats.items()):
        print(f"\n📍 {city}")
        print("-" * 50)

        if not slots:
            print("  Pas de données pour cette ville.")
            continue

        # Trier par pourcentage décroissant
        sorted_slots = sorted(slots.items(), key=lambda x: x[1]["pct"], reverse=True)

        # Afficher uniquement les créneaux avec au moins 2 scans
        significant = [(k, v) for k, v in sorted_slots if v["total"] >= 2]

        if not significant:
            print("  Pas assez de données (minimum 2 scans par créneau requis).")
            continue

        print(f"  {'Jour':<12} {'Heure':<8} {'Scans':<8} {'Indisponibles':<16} {'Pénurie %'}")
        print(f"  {'-'*12} {'-'*8} {'-'*8} {'-'*16} {'-'*10}")

        for (jour, heure), data in significant[:top_n]:
            bar = "█" * int(data["pct"] / 10)  # Barre visuelle sur 10 caractères
            print(
                f"  {JOURS_FR[jour]:<12} {heure:02d}h-{(heure+1)%24:02d}h  "
                f"{data['total']:<8} {data['indisponibles']:<16} "
                f"{data['pct']:>5.1f}% {bar}"
            )

        # Résumé : créneaux "critiques" (>= 50% de pénurie)
        critiques = [(k, v) for k, v in significant if v["pct"] >= 50.0]
        if critiques:
            print(f"\n  ⚡ {len(critiques)} créneau(x) critique(s) (≥50% pénurie) :")
            for (jour, heure), data in sorted(critiques, key=lambda x: x[1]["pct"], reverse=True)[:5]:
                print(f"     → {JOURS_FR[jour]} {heure:02d}h : {data['pct']}% de pénurie")

    print("\n" + "═" * 60 + "\n")


def export_csv(stats: dict, output_path: str = "data/rapport_penurie.csv") -> None:
    """Exporte les statistiques en CSV pour analyse externe (Excel, etc.)."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(["Ville", "Jour", "Heure_debut", "Heure_fin",
                         "Scans_total", "Indisponibles", "Penurie_pct"])

        for city, slots in sorted(stats.items()):
            for (jour, heure), data in sorted(slots.items(), key=lambda x: x[1]["pct"], reverse=True):
                writer.writerow([
                    city,
                    JOURS_FR[jour],
                    f"{heure:02d}:00",
                    f"{(heure+1)%24:02d}:00",
                    data["total"],
                    data["indisponibles"],
                    str(data["pct"]).replace(".", ","),  # Format français
                ])

    print(f"✅ CSV exporté : {output_path}")


def print_global_summary(rows: list[dict]) -> None:
    """Affiche un résumé global de la collecte."""
    if not rows:
        print("Aucune donnée collectée.")
        return

    total = len(rows)
    indisponibles = sum(1 for r in rows if r["status"] == "INDISPONIBLE")
    villes = len(set(r["city"] for r in rows))

    dates = [r["scanned_at"] for r in rows]
    first_scan = min(dates)[:19]
    last_scan = max(dates)[:19]

    print(f"\n📊 Résumé global de la collecte")
    print(f"   Période       : {first_scan} → {last_scan} UTC")
    print(f"   Villes suivies : {villes}")
    print(f"   Scans total   : {total}")
    print(f"   Indisponibles : {indisponibles} ({100*indisponibles//total}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Analyse les créneaux de pénurie de livreurs UberEats"
    )
    parser.add_argument(
        "--ville",
        type=str,
        default=None,
        help="Filtrer sur une ville spécifique (ex: Lesneven)"
    )
    parser.add_argument(
        "--jours",
        type=int,
        default=None,
        help="Analyser uniquement les N derniers jours (ex: 7)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=10,
        help="Nombre de créneaux à afficher par ville (défaut: 10)"
    )
    parser.add_argument(
        "--export",
        choices=["csv"],
        default=None,
        help="Exporter les résultats (ex: --export csv)"
    )
    args = parser.parse_args()

    print(f"📂 Chargement de : {DB_PATH}")
    rows = load_data(DB_PATH, city_filter=args.ville, jours=args.jours)
    print(f"   {len(rows)} entrées chargées.")

    print_global_summary(rows)

    stats = compute_stats(rows)
    print_report(stats, top_n=args.top)

    if args.export == "csv":
        export_csv(stats)


if __name__ == "__main__":
    main()
