"""
dashboard.py — Generateur de dashboard HTML interactif pour UberEats Monitor
Injecte TOUS les scans SQLite dans docs/index.html avec filtres dynamiques (Date, Jour, Ville, Statut).
"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from config import CITIES, DB_PATH

DOCS_DIR = "docs"
OUTPUT_FILE = os.path.join(DOCS_DIR, "index.html")

DAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
CITY_COLORS = {
    "Lesneven":          {"main": "#6366f1", "light": "#818cf8"},
    "Landivisiau":       {"main": "#f59e0b", "light": "#fbbf24"},
    "Saint-Pol-de-Léon": {"main": "#10b981", "light": "#34d399"},
}


def get_db_conn():
    if not os.path.exists(DB_PATH):
        return None
    return sqlite3.connect(DB_PATH)


def fetch_all_scans_detailed(conn):
    """Récupère TOUS les scans sans limite pour le tableau interactif."""
    cur = conn.execute("""
        SELECT city, scanned_at, status, detection, http_code, error
        FROM scans
        ORDER BY id DESC
    """)
    return cur.fetchall()


def to_local_datetime(utc_str):
    """Convertit UTC string -> datetime Paris (UTC+2)."""
    if not utc_str:
        return None
    clean = utc_str.replace("Z", "").strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            dt = datetime.strptime(clean, fmt).replace(tzinfo=timezone.utc)
            return dt + timedelta(hours=2)
        except ValueError:
            continue
    return None


def compute_heatmap(rows, city_name):
    totals = defaultdict(int)
    indispos = defaultdict(int)

    for city, scanned_at, status, *_ in rows:
        if city != city_name or status not in ('DISPONIBLE', 'INDISPONIBLE'):
            continue
        dt = to_local_datetime(scanned_at)
        if dt is None:
            continue
        key = (dt.weekday(), dt.hour)
        totals[key] += 1
        if status == "INDISPONIBLE":
            indispos[key] += 1

    matrix = []
    for day in range(7):
        row = []
        for hour in range(24):
            key = (day, hour)
            if totals[key] == 0:
                row.append(None)
            else:
                row.append(round(indispos[key] / totals[key], 3))
        matrix.append(row)
    return matrix


def compute_stats(rows, city_name):
    city_rows = [s for c, _, s, *_ in rows if c == city_name and s in ('DISPONIBLE', 'INDISPONIBLE')]
    if not city_rows:
        return {"total": 0, "dispo": 0, "indispo": 0, "pct_indispo": 0}
    total = len(city_rows)
    indispo = sum(1 for s in city_rows if s == "INDISPONIBLE")
    dispo = total - indispo
    return {
        "total": total,
        "dispo": dispo,
        "indispo": indispo,
        "pct_indispo": round(indispo / total * 100, 1) if total else 0,
    }


def compute_best_hours(rows, city_name):
    totals = defaultdict(int)
    indispos = defaultdict(int)

    for city, scanned_at, status, *_ in rows:
        if city != city_name or status not in ('DISPONIBLE', 'INDISPONIBLE'):
            continue
        dt = to_local_datetime(scanned_at)
        if dt is None:
            continue
        key = (dt.weekday(), dt.hour)
        totals[key] += 1
        if status == "INDISPONIBLE":
            indispos[key] += 1

    results = []
    for key, total in totals.items():
        if total >= 1:
            rate = indispos[key] / total
            results.append((key[0], key[1], rate, total))

    results.sort(key=lambda x: -x[2])
    return results[:5]


def generate_html(all_rows, city_names, generated_at):
    heatmaps = {}
    stats_all = {}
    best_hours_all = {}

    for city in city_names:
        heatmaps[city] = compute_heatmap(all_rows, city)
        stats_all[city] = compute_stats(all_rows, city)
        best_hours_all[city] = compute_best_hours(all_rows, city)

    # Préparation des données JSON complètes pour le JS du frontend
    scans_data = []
    dates_set = set()
    for city, scanned_at, status, detection, http_code, error in all_rows:
        dt = to_local_datetime(scanned_at)
        date_str = dt.strftime("%Y-%m-%d") if dt else ""
        time_str = dt.strftime("%d/%m/%Y à %H:%M:%S") if dt else scanned_at
        day_fr = DAYS_FR[dt.weekday()] if dt else ""
        if date_str:
            dates_set.add(date_str)

        scans_data.append({
            "city": city,
            "date": date_str,
            "day": day_fr,
            "time": time_str,
            "status": status,
            "detection": detection or "",
            "http_code": http_code or 200,
            "error": error or "",
        })

    sorted_dates = sorted(list(dates_set), reverse=True)
    colors_json = {
        city: CITY_COLORS.get(city, {"main": "#6366f1", "light": "#818cf8"})
        for city in city_names
    }

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UberEats Monitor — Finistère</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
:root {{
  --bg: #0a0f1e;
  --surface: #111827;
  --surface2: #1f2937;
  --surface3: #374151;
  --text: #f9fafb;
  --text2: #9ca3af;
  --text3: #6b7280;
  --border: #1f2937;
  --radius: 16px;
  --radius-sm: 10px;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
  font-family: 'Inter', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  line-height: 1.5;
}}

header {{
  background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 50%, #0c1a0f 100%);
  border-bottom: 1px solid #1e3a5f;
  padding: 24px 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}}
.logo {{ display: flex; align-items: center; gap: 14px; }}
.logo-icon {{
  width: 48px; height: 48px;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border-radius: 14px;
  display: flex; align-items: center; justify-content: center;
  font-size: 24px;
  box-shadow: 0 0 20px rgba(99,102,241,0.4);
}}
.logo h1 {{
  font-size: 1.4rem;
  font-weight: 800;
  background: linear-gradient(90deg, #a5b4fc, #34d399);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}}
.logo p {{ color: var(--text2); font-size: 0.8rem; }}
.header-meta {{ text-align: right; color: var(--text2); font-size: 0.8rem; }}
.header-meta strong {{ display: block; color: var(--text); font-size: 0.9rem; }}

main {{ max-width: 1400px; margin: 0 auto; padding: 32px 24px; }}

.section-title {{
  font-size: 1.1rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  gap: 10px;
}}
.section-title::after {{
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border);
}}

.tabs {{ display: flex; gap: 8px; margin-bottom: 28px; flex-wrap: wrap; }}
.tab-btn {{
  padding: 10px 22px;
  border-radius: 50px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text2);
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  font-family: 'Inter', sans-serif;
  transition: all 0.2s;
}}
.tab-btn.active, .tab-btn:hover {{ color: var(--text); border-color: currentColor; }}

.stat-grid {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}}
.stat-card {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  text-align: center;
}}
.stat-card .value {{ font-size: 2rem; font-weight: 800; line-height: 1.1; }}
.stat-card .label {{ font-size: 0.75rem; color: var(--text2); margin-top: 6px; text-transform: uppercase; letter-spacing: 0.05em; }}
.stat-dispo .value {{ color: #34d399; }}
.stat-indispo .value {{ color: #f87171; }}

.best-slots {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 28px;
}}
.slot-list {{ display: flex; flex-direction: column; gap: 10px; }}
.slot-item {{ display: flex; align-items: center; gap: 14px; }}
.slot-badge {{
  background: var(--surface2);
  border-radius: var(--radius-sm);
  padding: 8px 14px;
  font-weight: 700;
  font-size: 0.95rem;
  white-space: nowrap;
  min-width: 140px;
  text-align: center;
}}
.slot-bar-wrap {{ flex: 1; background: var(--surface2); border-radius: 99px; height: 12px; overflow: hidden; }}
.slot-bar {{ height: 100%; border-radius: 99px; background: linear-gradient(90deg, #f87171, #ef4444); }}
.slot-pct {{ font-size: 0.85rem; font-weight: 600; color: #f87171; min-width: 50px; text-align: right; }}

.heatmap-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 24px;
  margin-bottom: 28px;
  overflow-x: auto;
}}
.heatmap-title {{ font-size: 0.85rem; font-weight: 600; color: var(--text2); margin-bottom: 16px; }}
.heatmap-table {{ border-collapse: separate; border-spacing: 3px; width: 100%; }}
.heatmap-table th {{ font-size: 0.7rem; font-weight: 500; color: var(--text3); text-align: center; padding: 4px 2px; }}
.heatmap-table td {{ width: 32px; height: 28px; border-radius: 6px; text-align: center; font-size: 0.65rem; font-weight: 500; }}
.hm-day {{ font-size: 0.72rem; font-weight: 600; color: var(--text2); white-space: nowrap; padding-right: 10px; text-align: right; }}
.hm-null {{ background: var(--surface2); color: var(--text3); }}

/* FILTRES & HISTORIQUE COMPLET */
.filter-bar {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 20px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}}
.filter-group {{ display: flex; flex-direction: column; gap: 6px; }}
.filter-group label {{ font-size: 0.75rem; color: var(--text2); font-weight: 600; text-transform: uppercase; }}
.filter-input {{
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 14px;
  border-radius: var(--radius-sm);
  font-family: inherit;
  font-size: 0.85rem;
  outline: none;
}}
.filter-input:focus {{ border-color: #6366f1; }}

.recent-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  margin-bottom: 28px;
}}
.recent-table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
.recent-table th {{
  background: var(--surface2);
  padding: 12px 16px;
  text-align: left;
  font-weight: 600;
  font-size: 0.75rem;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}}
.recent-table td {{ padding: 12px 16px; border-top: 1px solid var(--border); }}
.badge {{ display: inline-block; padding: 3px 10px; border-radius: 99px; font-size: 0.72rem; font-weight: 700; }}
.badge-dispo {{ background: rgba(16,185,129,0.15); color: #34d399; }}
.badge-indispo {{ background: rgba(239,68,68,0.15); color: #f87171; }}
.badge-block {{ background: rgba(245,158,11,0.15); color: #fbbf24; }}
.badge-err {{ background: rgba(107,114,128,0.15); color: #9ca3af; }}

.pagination {{
  display: flex; justify-content: space-between; align-items: center;
  padding: 16px 20px; background: var(--surface2); font-size: 0.85rem; color: var(--text2);
}}
.page-btn {{
  background: var(--surface3); border: none; color: var(--text); padding: 6px 14px;
  border-radius: 6px; cursor: pointer; font-size: 0.8rem; font-weight: 600;
}}
.page-btn:disabled {{ opacity: 0.4; cursor: not-allowed; }}

.city-panel {{ display: none; }}
.city-panel.active {{ display: block; }}

footer {{
  text-align: center; padding: 28px; color: var(--text3); font-size: 0.78rem;
  border-top: 1px solid var(--border); margin-top: 16px;
}}
</style>
</head>
<body>

<header>
  <div class="logo">
    <div class="logo-icon">🛵</div>
    <div>
      <h1>UberEats Monitor</h1>
      <p>Surveillance de pénurie de livreurs — Finistère</p>
    </div>
  </div>
  <div class="header-meta">
    <strong>Dernière mise à jour : {generated_at}</strong>
    Scans archivés dans la base SQLite
  </div>
</header>

<main>

<div class="tabs" id="cityTabs">
"""

    for i, city in enumerate(city_names):
        color = CITY_COLORS.get(city, {}).get("main", "#6366f1")
        active = "active" if i == 0 else ""
        html += f'<button class="tab-btn {active}" onclick="showCity(\'{city}\')" id="tab-{i}" style="{"color:"+color+";border-color:"+color if active else ""}">{city}</button>\n'

    html += "</div>\n"

    for i, city in enumerate(city_names):
        color = CITY_COLORS.get(city, {}).get("main", "#6366f1")
        stats = stats_all[city]
        best = best_hours_all[city]
        heatmap = heatmaps[city]
        active = "active" if i == 0 else ""

        html += f'<div class="city-panel {active}" id="panel-{i}" data-city="{city}">\n'

        html += '<div class="stat-grid">\n'
        html += f'<div class="stat-card"><div class="value" style="color:{color}">{stats["total"]}</div><div class="label">Scans total</div></div>\n'
        html += f'<div class="stat-card stat-dispo"><div class="value">{stats["dispo"]}</div><div class="label">✅ Disponible</div></div>\n'
        html += f'<div class="stat-card stat-indispo"><div class="value">{stats["indispo"]}</div><div class="label">🚨 Indisponible</div></div>\n'
        html += f'<div class="stat-card"><div class="value" style="color:#f87171">{stats["pct_indispo"]}%</div><div class="label">Taux pénurie</div></div>\n'
        html += '</div>\n'

        html += '<div class="section-title">🎯 Créneaux de pénurie les plus fréquents</div>\n'
        html += '<div class="best-slots"><div class="slot-list">\n'
        if best:
            for day_i, hour, rate, total in best:
                pct = round(rate * 100)
                html += f'''<div class="slot-item">
  <div class="slot-badge" style="color:{color}">{DAYS_FR[day_i]} {hour:02d}h–{hour+1:02d}h</div>
  <div class="slot-bar-wrap"><div class="slot-bar" style="width:{pct}%"></div></div>
  <div class="slot-pct">{pct}%</div>
</div>\n'''
        else:
            html += '<div class="no-data">Pas encore assez de données de pénurie enregistrées.</div>\n'
        html += '</div></div>\n'

        html += '<div class="section-title">🔥 Carte de chaleur — Taux de pénurie par heure</div>\n'
        html += '<div class="heatmap-wrap">\n'
        html += '<div class="heatmap-title">Taux d\'indisponibilité par jour et par heure (Heure de Paris)</div>\n'
        html += '<table class="heatmap-table"><thead><tr><th></th>'
        for h in range(24):
            html += f'<th>{h:02d}</th>'
        html += '</tr></thead><tbody>\n'

        for day_i, day_name in enumerate(DAYS_FR):
            html += f'<tr><td class="hm-day">{day_name}</td>'
            for hour in range(24):
                val = heatmap[day_i][hour]
                if val is None:
                    html += '<td class="hm-null" title="Aucune donnée">·</td>'
                else:
                    r = int(val * 248 + (1-val) * 16)
                    g = int(val * 113 + (1-val) * 185)
                    b = int(val * 113 + (1-val) * 129)
                    pct_disp = round(val * 100)
                    html += (
                        f'<td style="background:rgb({r},{g},{b});color:rgba(255,255,255,0.8)" '
                        f'title="{day_name} {hour:02d}h : {pct_disp}% pénurie">{pct_disp}</td>'
                    )
            html += '</tr>\n'

        html += '</tbody></table>\n'
        html += '</div>\n'
        html += '</div>\n'

    # SECTION HISTORIQUE INTERACTIF DE TOUS LES SCANS
    html += '<div class="section-title">📊 Historique Complet des Scans & Recherche</div>\n'

    html += '<div class="filter-bar">\n'
    html += '<div class="filter-group"><label>📅 Date</label><select id="filterDate" class="filter-input" onchange="applyFilters()"><option value="">Toutes les dates</option>'
    for d in sorted_dates:
        html += f'<option value="{d}">{d}</option>'
    html += '</select></div>\n'

    html += '<div class="filter-group"><label>📆 Jour</label><select id="filterDay" class="filter-input" onchange="applyFilters()"><option value="">Tous les jours</option>'
    for day in DAYS_FR:
        html += f'<option value="{day}">{day}</option>'
    html += '</select></div>\n'

    html += '<div class="filter-group"><label>🏙️ Ville</label><select id="filterCity" class="filter-input" onchange="applyFilters()"><option value="">Toutes les villes</option>'
    for city in city_names:
        html += f'<option value="{city}">{city}</option>'
    html += '</select></div>\n'

    html += '<div class="filter-group"><label>🚨 Statut</label><select id="filterStatus" class="filter-input" onchange="applyFilters()"><option value="">Tous les statuts</option>'
    html += '<option value="DISPONIBLE">✅ Disponible</option><option value="INDISPONIBLE">🚨 Indisponible</option><option value="ERREUR">❌ Erreur / 403</option>'
    html += '</select></div>\n'

    html += '<div class="filter-group" style="flex:1"><label>🔍 Recherche</label><input type="text" id="filterSearch" class="filter-input" placeholder="Rechercher par mot-clé..." oninput="applyFilters()"></div>\n'
    html += '</div>\n'

    html += '<div class="recent-wrap">\n'
    html += '<table class="recent-table"><thead><tr>'
    html += '<th>Heure (Paris)</th><th>Ville</th><th>Statut</th><th>Code HTTP</th><th>Détail / Détection</th>'
    html += '</tr></thead><tbody id="scansTbody">\n'
    html += '</tbody></table>\n'
    html += '<div class="pagination">\n'
    html += '<div>Affichage <span id="pageInfo">0-0 sur 0</span> scans</div>\n'
    html += '<div>\n'
    html += '<button class="page-btn" id="prevBtn" onclick="changePage(-1)">← Précédent</button>\n'
    html += '<button class="page-btn" id="nextBtn" onclick="changePage(1)" style="margin-left:8px">Suivant →</button>\n'
    html += '</div>\n'
    html += '</div>\n'
    html += '</div>\n'

    html += f"""
</main>

<footer>
  UberEats Monitor · Auto-généré le {generated_at} (Heure de Paris) · Base complète SQLite ({len(scans_data)} enregistrements)
</footer>

<script>
const ALL_SCANS = {json.dumps(scans_data)};
const CITIES = {json.dumps(city_names)};
const COLORS = {json.dumps(colors_json)};

let currentPage = 1;
const pageSize = 50;
let filteredScans = [...ALL_SCANS];

function showCity(cityName) {{
  const panels = document.querySelectorAll('.city-panel');
  const tabs = document.querySelectorAll('.tab-btn');
  panels.forEach((p, i) => {{
    const isActive = p.dataset.city === cityName;
    p.classList.toggle('active', isActive);
    const tab = tabs[i];
    const color = COLORS[p.dataset.city]?.main || '#6366f1';
    if (isActive) {{
      tab.classList.add('active');
      tab.style.color = color;
      tab.style.borderColor = color;
      tab.style.background = color + '18';
    }} else {{
      tab.classList.remove('active');
      tab.style.color = '';
      tab.style.borderColor = '';
      tab.style.background = '';
    }}
  }});
}}

function applyFilters() {{
  const dateVal = document.getElementById('filterDate').value;
  const dayVal = document.getElementById('filterDay').value;
  const cityVal = document.getElementById('filterCity').value;
  const statusVal = document.getElementById('filterStatus').value;
  const searchVal = document.getElementById('filterSearch').value.toLowerCase();

  filteredScans = ALL_SCANS.filter(s => {{
    if (dateVal && s.date !== dateVal) return false;
    if (dayVal && s.day !== dayVal) return false;
    if (cityVal && s.city !== cityVal) return false;
    if (statusVal && s.status !== statusVal) return false;
    if (searchVal) {{
      const lineText = (s.time + ' ' + s.city + ' ' + s.status + ' ' + s.detection + ' ' + s.error).toLowerCase();
      if (!lineText.includes(searchVal)) return false;
    }}
    return true;
  }});

  currentPage = 1;
  renderTable();
}}

function renderTable() {{
  const tbody = document.getElementById('scansTbody');
  tbody.innerHTML = '';

  const total = filteredScans.length;
  const start = (currentPage - 1) * pageSize;
  const end = Math.min(start + pageSize, total);
  const pageItems = filteredScans.slice(start, end);

  if (total === 0) {{
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:24px;color:var(--text3)">Aucun scan trouvé pour ces filtres.</td></tr>';
    document.getElementById('pageInfo').innerText = '0 sur 0';
    document.getElementById('prevBtn').disabled = true;
    document.getElementById('nextBtn').disabled = true;
    return;
  }}

  pageItems.forEach(r => {{
    let badge = '';
    if (r.http_code === 403) {{
      badge = '<span class="badge badge-block">⚠️ Anti-Bot (403)</span>';
    }} else if (r.status === 'DISPONIBLE') {{
      badge = '<span class="badge badge-dispo">✅ Disponible</span>';
    }} else if (r.status === 'INDISPONIBLE') {{
      badge = '<span class="badge badge-indispo">🚨 Indisponible</span>';
    }} else {{
      badge = '<span class="badge badge-err">❌ Erreur</span>';
    }}

    const cityColor = COLORS[r.city]?.main || '#9ca3af';
    const detail = r.detection ? r.detection : (r.error ? r.error.substring(0, 60) : '—');

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="color:var(--text2)">${{r.time}}</td>
      <td><strong style="color:${{cityColor}}">${{r.city}}</strong></td>
      <td>${{badge}}</td>
      <td style="color:var(--text3)">HTTP ${{r.http_code}}</td>
      <td style="color:var(--text3);font-size:0.8rem">${{detail}}</td>
    `;
    tbody.appendChild(tr);
  }});

  document.getElementById('pageInfo').innerText = `${{start + 1}}-${{end}} sur ${{total}}`;
  document.getElementById('prevBtn').disabled = currentPage === 1;
  document.getElementById('nextBtn').disabled = end >= total;
}}

function changePage(delta) {{
  currentPage += delta;
  renderTable();
}}

showCity(CITIES[0]);
applyFilters();
</script>
</body>
</html>
"""
    return html


def main():
    os.makedirs(DOCS_DIR, exist_ok=True)

    conn = get_db_conn()
    if conn is None:
        print("Base de données introuvable, dashboard vide créé.")
        return

    all_rows = fetch_all_scans_detailed(conn)
    conn.close()

    city_names = [c["name"] for c in CITIES]
    now_paris = datetime.now(timezone.utc) + timedelta(hours=2)
    generated_at = now_paris.strftime("%d/%m/%Y à %H:%M:%S")

    html = generate_html(all_rows, city_names, generated_at)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard généré : {OUTPUT_FILE} ({len(all_rows)} scans au total)")


if __name__ == "__main__":
    main()
