"""
src/export/gantt_interactive.py

Generates a self-contained interactive HTML Gantt chart from a list of Tasks.
Uses Vis.js Timeline (loaded from CDN) — no extra Python dependencies.

Layout:
  - Rows  = unique task names  (e.g. "core_door", "ply_adjustable_shelf", …)
  - Bars  = individual tasks, colour-coded by milestone
  - Sidebar panel 1: Milestone filter (toggle visibility per milestone colour)
  - Sidebar panel 2: Task-type filter (part_model / part_list / release / drawing …)

Features:
  - Pan / zoom / fit-all / today
  - Hover tooltip with full task detail
  - Export to JSON and CSV from the browser
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import List, Optional, Dict, Any, Set

from src.core.models import Task
from src.config import DEBUG

# Distinct colours for up to 12 milestones; cycles beyond that
_MILESTONE_PALETTE = [
    "#4C8BF5", "#E8453C", "#F4B942", "#3DA65A",
    "#9B59B6", "#E67E22", "#1ABC9C", "#E91E8C",
    "#00BCD4", "#8BC34A", "#FF5722", "#607D8B",
]

# Colours for task types
_TYPE_PALETTE: Dict[str, str] = {
    "part_model": "#4C8BF5",
    "part_list":  "#F4B942",
    "release":    "#3DA65A",
    "drawing":    "#90A4AE",
}
_TYPE_FALLBACK = "#9B59B6"


def _hex_to_rgba(hex_color: str, alpha: float = 0.85) -> str:
    h = hex_color.lstrip('#')
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# [Req: RF-17, RF-17.4] — Entry point: title and project_start_date are configurable per-project
def export_interactive_gantt(
    tasks: List[Task],
    output_path: Path,
    title: str = "Chrono Tailoring — Interactive Gantt Chart",
    milestone_name_map: Optional[Dict[Any, str]] = None,
    total_resources: int = 1,
    project_requirements_path: Optional[Path] = None,
    holidays: Optional[Set[date]] = None,
    show_task_arrows: bool = False,
) -> None:
    """Serialises tasks to JSON and writes a self-contained Vis.js HTML Gantt.

    Rows  = unique task names (swim-lanes).
    Items = individual task instances, coloured by milestone.

    Args:
        tasks (List[Task]): Flat list of Task objects with init_date / end_date set.
        output_path (Path): Where to write the .html file.
        title (str, optional): Browser title / header text. Defaults to "Chrono Tailoring — Interactive Gantt Chart".
        milestone_name_map (Optional[Dict[Any, str]], optional): Mapping of milestone IDs to names. Defaults to None.
        total_resources (int, optional): The total number of parallel resources applied. Defaults to 1.
        project_requirements_path (Optional[Path], optional): Path to requirements for the info sidebar. Defaults to None.
        holidays (Optional[Set[date]], optional): Dates to format differently. Defaults to None.
        show_task_arrows (bool, optional): Auto-enable standard dependency arrows on load. Defaults to False.
    """
    if milestone_name_map is None:
        milestone_name_map = {}

    # ── 1. Milestone colours ─────────────────────────────────────────────────────
    milestone_ids: list = []
    for t in tasks:
        mid = getattr(t, 'milestone_id', None)
        if mid is not None and mid not in milestone_ids:
            milestone_ids.append(mid)
    milestone_ids.sort(key=str)

    # [Req: RF-17.3] — Milestone colour palette (12 colours, cyclic); no-milestone tasks get grey
    milestone_color: dict = {}
    for i, mid in enumerate(milestone_ids):
        milestone_color[mid] = _MILESTONE_PALETTE[i % len(_MILESTONE_PALETTE)]
    default_color = "#90A4AE"   # for tasks with no milestone

    # ── 2. Groups = unique task names ────────────────────────────────────────────
    # Format names to `BasePart - Description`
    def format_task_name(t: Task) -> str:
        base_part = str(t.part_number).split('.')[0]
        if t.name.startswith("Consolidated Drawing"):
            return f"{base_part} - Consolidated drawing"
        return f"{base_part} - {t.name}"

    # [Req: RF-17.2] — Swim-lanes = unique task names formatted as 'BasePart - Name', sorted alphabetically
    seen_names: list = []
    for t in tasks:
        if t.init_date is None or t.end_date is None:
            continue
        fname = format_task_name(t)
        if fname not in seen_names:
            seen_names.append(fname)
            
    # Keep insertion order (chronological by first appearance), then sort alpha
    seen_names.sort()

    groups: list = [{"id": name, "content": name} for name in seen_names]

    # ── 3. Items ─────────────────────────────────────────────────────────────────
    items: list = []
    
    # ── 3.1 Links for Critical Path and all other tasks───────────────────────────
    critical_links = []
    task_links = [] # all task links regardless of criticality

    for task in tasks:
        if task.init_date is None or task.end_date is None:
            continue

        mid = getattr(task, 'milestone_id', None)
        color = milestone_color.get(mid, default_color)
        bg = _hex_to_rgba(color, 0.85)
        border = color

        preds = ", ".join(str(p.id) for p in task.predecessors) or "—"
        succs = ", ".join(
            str(s.id) for s in getattr(task, 'successors_tasks', [])
        ) or "—"
        duration_h = round(task.duration_minutes / 60, 2)

        milestone_label = milestone_name_map.get(mid, f"Milestone {mid}") if mid is not None else "—"
        task_type_desc  = task.type.description

        tooltip = (
            f"<div class='tt'>"
            f"<b>#{task.id} — {task.name}</b>"
            f"<div class='tt-row'>Milestone: <span>{milestone_label}</span></div>"
            f"<div class='tt-row'>Type: <span>{task_type_desc}</span></div>"
            f"<div class='tt-row'>Part: <span>{task.part_number}</span></div>"
            f"<div class='tt-row'>Duration: <span>{duration_h} h</span></div>"
            f"<div class='tt-row'>Start: <span>{task.init_date.strftime('%Y-%m-%d %H:%M')}</span></div>"
            f"<div class='tt-row'>End: <span>{task.end_date.strftime('%Y-%m-%d %H:%M')}</span></div>"
            f"<div class='tt-row'>Predecessors: <span>{preds}</span></div>"
            f"<div class='tt-row'>Successors: <span>{succs}</span></div>"
            f"</div>"
        )

        fname = format_task_name(task)
        
        # [Req: RF-19.1] — Build critical path links (both endpoints is_critical=True)
        if getattr(task, 'is_critical', False):
            for succ in getattr(task, 'successors_tasks', []):
                if getattr(succ, 'is_critical', False):
                    critical_links.append({
                        "from": task.id,
                        "to": succ.id
                    })
        
        # [Req: RF-19.2] — All task links; non-critical ones rendered grey and togglable
        for succ in getattr(task, 'successors_tasks', []):
            task_links.append({
                "from": task.id,
                "to": succ.id
            })

        items.append({
            "id":      task.id,
            "group":   fname,          # row = formatted task name
            "content": f"#{task.id}",      # compact bar label
            "start":   task.init_date.strftime('%Y-%m-%dT%H:%M:%S'),
            "end":     task.end_date.strftime('%Y-%m-%dT%H:%M:%S'),
            "title":   tooltip,
            "style": (
                f"background-color:{bg};"
                f"border-color:{border};"
                f"color:#fff;"
                f"border-radius:4px;"
            ),
            # [Req: RF-22.3] — Metadata fields embedded per-item for browser-side export
            "_task_id":    task.id,
            "_name":       fname,
            "_milestone":  milestone_label,
            "_milestone_id": str(mid) if mid is not None else "",
            "_type":       task_type_desc,
            "_part":       task.part_number,
            "_duration_h": duration_h,
            "_start":      task.init_date.strftime('%Y-%m-%d %H:%M'),
            "_end":        task.end_date.strftime('%Y-%m-%d %H:%M'),
            "_preds":      preds,
            "_succs":      succs,
        })
        
    # Combine critical_links and task_links based on the flag
    # Use list() to avoid mutating the original critical_links reference
    all_links = list(critical_links)
    if show_task_arrows:
        all_links.extend([link for link in task_links if link not in critical_links])

    # [Req: RF-20, RF-20.1] — Add background items for weekends and holidays; styled via CSS .holiday-bg
    if tasks:
        p_start = min(t.init_date for t in tasks if t.init_date)
        p_end = max(t.end_date for t in tasks if t.end_date)
        
        current_date = p_start.date()
        end_date = p_end.date()
        h_set = holidays or set()
        
        bg_idx = 0
        while current_date <= end_date:
            if current_date.weekday() >= 5 or current_date in h_set:
                items.append({
                    "id": f"bg_{bg_idx}",
                    "start": current_date.strftime('%Y-%m-%dT00:00:00'),
                    "end": (current_date + timedelta(days=1)).strftime('%Y-%m-%dT00:00:00'),
                    "type": "background",
                    "className": "holiday-bg"
                })
                bg_idx += 1
            current_date += timedelta(days=1)

    # Build milestone meta list for sidebar (id → {name, color})
    milestone_meta = []
    for mid in milestone_ids:
        label = milestone_name_map.get(mid, f"Milestone {mid}")
        milestone_meta.append({
            "id":    str(mid),
            "label": label,
            "color": milestone_color[mid],
        })
    # Add "no milestone" entry if any task has no milestone
    if any(getattr(t, 'milestone_id', None) is None for t in tasks
           if t.init_date and t.end_date):
        milestone_meta.append({
            "id":    "__none__",
            "label": "No Milestone",
            "color": default_color,
        })

    # Collect unique task types
    task_types = []
    for t in tasks:
        td = t.type.description
        if td not in task_types:
            task_types.append(td)
    task_types.sort()

    # [Req: RF-21.1, RF-21.2, RF-21.3] — Sweep-line resource histogram: +1 at init_date, -1 at end_date; double-point for step chart
    events = []
    for task in tasks:
        if task.init_date and task.end_date and getattr(task, 'duration_minutes', 0) > 0:
            events.append((task.init_date, 1))   # [Req: RF-21.1] — +1 event
            events.append((task.end_date, -1))   # [Req: RF-21.1] — -1 event
    events.sort(key=lambda x: x[0])

    resource_data = []
    current_load = 0
    if events:
        start_buffer = events[0][0].replace(hour=0, minute=0, second=0)
        resource_data.append({"x": start_buffer.strftime('%Y-%m-%dT%H:%M:%S'), "y": 0})

    for time_val, delta in events:
        time_str = time_val.strftime('%Y-%m-%dT%H:%M:%S')
        # [Req: RF-21.3] — Emit previous Y then new Y at same X to force true step chart in Vis.js
        resource_data.append({"x": time_str, "y": current_load})
        current_load += delta
        resource_data.append({"x": time_str, "y": current_load})
        
    items_json          = json.dumps(items,          ensure_ascii=False)
    groups_json         = json.dumps(groups,         ensure_ascii=False)
    milestone_meta_json = json.dumps(milestone_meta, ensure_ascii=False)
    task_types_json     = json.dumps(task_types,     ensure_ascii=False)
    type_palette_json   = json.dumps(_TYPE_PALETTE,  ensure_ascii=False)
    resource_data_json  = json.dumps(resource_data,  ensure_ascii=False)
    critical_links_json = json.dumps(critical_links, ensure_ascii=False)
    all_links_json = json.dumps(all_links, ensure_ascii=False)

    # [Req: RF-23.1] — Project summary: dates and duration computed at generation time
    if tasks:
        p_start = min(t.init_date for t in tasks if t.init_date)
        p_end = max(t.end_date for t in tasks if t.end_date)
        p_dur_days = (p_end - p_start).days
        p_start_str = p_start.strftime('%d %b %Y')
        p_end_str = p_end.strftime('%d %b %Y')
    else:
        p_start_str, p_end_str, p_dur_days = "N/A", "N/A", 0
        
    # [Req: RF-23.2] — Raw project_config.json embedded verbatim for context
    req_text = ""
    if project_requirements_path and project_requirements_path.exists():
        req_text = project_requirements_path.read_text('utf-8')

    # ── 4. Render HTML ────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>{title}</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet"/>
  <link href="https://unpkg.com/vis-timeline@7.7.3/dist/vis-timeline-graph2d.min.css" rel="stylesheet"/>
  <script src="https://unpkg.com/vis-timeline@7.7.3/dist/vis-timeline-graph2d.min.js"></script>

  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg:        #0b0d14;
      --surface:   #11141f;
      --surface2:  #181c2e;
      --border:    #252a40;
      --accent:    #4C8BF5;
      --accent2:   #7c57ff;
      --text:      #dde1f0;
      --muted:     #6b728e;
      --radius:    10px;
    }}

    body {{
      font-family: 'Inter', 'Segoe UI', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
    }}

    /* ── Header ─────────────────────────────────────────────────────────────── */
    header {{
      padding: 0 20px;
      height: 54px;
      background: linear-gradient(90deg, #0f1626 0%, #0b0d14 60%);
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: 14px;
      flex-shrink: 0;
      box-shadow: 0 2px 20px rgba(0,0,0,0.4);
      z-index: 10;
    }}

    .logo-mark {{
      width: 30px; height: 30px;
      background: linear-gradient(135deg, var(--accent), var(--accent2));
      border-radius: 8px;
      display: flex; align-items: center; justify-content: center;
      font-size: 0.9rem; flex-shrink: 0;
    }}

    header h1 {{
      font-size: 0.9rem;
      font-weight: 600;
      color: #fff;
      letter-spacing: -0.01em;
      white-space: nowrap;
    }}

    .header-right {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-left: auto;
    }}

    .badge {{
      font-size: 0.7rem;
      font-weight: 500;
      color: var(--muted);
      background: var(--surface2);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 3px 10px;
      white-space: nowrap;
    }}

    /* ── Buttons ─────────────────────────────────────────────────────────────── */
    .toolbar {{ display: flex; gap: 5px; align-items: center; }}

    .btn {{
      background: var(--surface2);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 5px 12px;
      cursor: pointer;
      font-size: 0.75rem;
      font-family: inherit;
      font-weight: 500;
      display: flex; align-items: center; gap: 5px;
      transition: background 0.15s, border-color 0.15s, transform 0.1s;
      white-space: nowrap;
    }}
    .btn:hover {{ background: #232745; border-color: #3a4070; transform: translateY(-1px); }}
    .btn:active {{ transform: translateY(0); }}

    .btn-accent {{
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent2) 100%);
      border-color: transparent; color: #fff;
    }}
    .btn-accent:hover {{
      background: linear-gradient(135deg, #5f9cf6 0%, #9271ff 100%);
      border-color: transparent;
    }}
    .btn-export {{
      background: linear-gradient(135deg, #1a6b42 0%, #1a4b6b 100%);
      border-color: transparent; color: #a0ffcb;
    }}
    .btn-export:hover {{
      background: linear-gradient(135deg, #22855a 0%, #205d82 100%);
      border-color: transparent;
    }}

    .divider {{ width: 1px; height: 20px; background: var(--border); margin: 0 3px; }}

    /* ── Layout ──────────────────────────────────────────────────────────────── */
    .main {{ display: flex; flex: 1; overflow: hidden; }}

    /* ── Sidebar ─────────────────────────────────────────────────────────────── */
    .sidebar {{
      width: 220px;
      flex-shrink: 0;
      background: var(--surface);
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}

    .panel-header {{
      padding: 10px 12px 8px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    .panel-header h2 {{
      font-size: 0.63rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
    }}
    .panel-toggle-row {{
      display: flex;
      gap: 5px;
    }}
    .panel-toggle-row .btn {{
      font-size: 0.65rem;
      padding: 3px 8px;
    }}

    .sidebar-scroll {{
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 15px;
    }}
    .section-label {{
      font-size: 0.65rem;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 6px;
    }}
    .section-sep {{
      border: 0;
      border-top: 1px solid var(--border);
      margin: 0;
    }}
    
    /* ── Summary & Requirements ─────────────────────────────────────────────── */
    .summary-box {{
      background: #151828;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }}
    .summary-row {{
      display: flex;
      justify-content: space-between;
      margin-bottom: 4px;
      font-size: 0.75rem;
    }}
    .summary-row:last-child {{ margin-bottom: 0; }}
    .summary-key {{ color: var(--muted); font-weight: 500; }}
    .summary-val {{ color: var(--text); font-weight: 600; text-align: right; }}
    
    .req-box {{
      background: #0d0f1a;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      font-family: monospace;
      font-size: 0.65rem;
      color: #929ebd;
      white-space: pre-wrap;
      overflow-x: auto;
      margin-top: 2px;
    }}

    .legend-item {{
      font-size: 0.6rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--muted);
      padding: 4px 4px 6px;
    }}

    .filter-item {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 5px 6px;
      border-radius: 7px;
      cursor: pointer;
      font-size: 0.76rem;
      user-select: none;
      transition: background 0.12s;
    }}
    .filter-item:hover {{ background: var(--surface2); }}
    .filter-item input {{
      cursor: pointer;
      accent-color: var(--accent);
      width: 13px; height: 13px;
      flex-shrink: 0;
    }}
    .filter-dot {{
      width: 9px; height: 9px;
      border-radius: 3px;
      flex-shrink: 0;
    }}
    .filter-label {{
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }}

    /* ── Timeline ────────────────────────────────────────────────────────────── */
    .main-content {{
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      background: #0d0f1a;
      position: relative;
    }}
    #gantt {{ flex: 1; overflow: hidden; }}
    #resourceGraph {{ height: 160px; border-top: 1px solid var(--border); background: var(--bg); flex-shrink: 0; }}
    
    #criticalSvg {{
      position: absolute;
      top: 0; left: 0;
      width: 100%; height: 100%;
      pointer-events: none;
      z-index: 10;
    }}
    .cp-path {{
      stroke: #E8453C;
      stroke-width: 2.5px;
      fill: none;
      filter: drop-shadow(0 0 3px rgba(232, 69, 60, 0.6));
    }}

    /* ── Vis.js overrides ────────────────────────────────────────────────────── */
    .vis-timeline {{ border: none; }}
    .vis-panel.vis-center {{ background: #0d0f1a; }}
    .vis-panel.vis-left   {{ background: var(--surface); }}
    .vis-time-axis .vis-text {{ color: var(--muted); font-size: 0.7rem; font-family: inherit; }}
    .vis-time-axis .vis-grid.vis-minor {{ border-color: #161826; }}
    .vis-time-axis .vis-grid.vis-major {{ border-color: var(--border); }}
    .vis-label {{
      color: var(--text) !important;
      font-size: 0.72rem;
      font-weight: 500;
      font-family: inherit;
      padding: 0 8px;
    }}
    .vis-item {{ font-size: 0.68rem; font-family: inherit; }}
    .vis-item.vis-selected {{
      border-color: #fff !important;
      box-shadow: 0 0 0 2px rgba(255,255,255,0.2);
    }}
    .vis-current-time {{ background-color: var(--accent) !important; width: 2px; opacity: 0.7; }}

    /* ── Tooltip ─────────────────────────────────────────────────────────────── */
    .vis-tooltip {{
      background: #121626 !important;
      border: 1px solid #2e3555 !important;
      border-radius: 10px !important;
      padding: 12px 16px !important;
      font-size: 0.74rem !important;
      line-height: 1.75 !important;
      color: var(--text) !important;
      min-width: 240px !important;
      max-width: 320px !important;
      box-shadow: 0 12px 40px rgba(0,0,0,0.7) !important;
      font-family: inherit !important;
      z-index: 99999 !important;
    }}
    .tt b {{ color: #fff; font-size: 0.8rem; display: block; margin-bottom: 6px; }}
    .tt .tt-row {{ color: var(--muted); font-size: 0.72rem; }}
    .tt .tt-row span {{ color: var(--text); }}

    /* ── Scrollbar ───────────────────────────────────────────────────────────── */
    ::-webkit-scrollbar {{ width: 4px; height: 4px; }}
    ::-webkit-scrollbar-track {{ background: transparent; }}
    ::-webkit-scrollbar-thumb {{ background: #2a2f4a; border-radius: 3px; }}

    /* ── Toast ───────────────────────────────────────────────────────────────── */
    #toast {{
      position: fixed; bottom: 20px; right: 20px;
      background: rgba(20,24,40,0.95);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 9px 16px;
      font-size: 0.78rem;
      color: #a0ffcb;
      box-shadow: 0 8px 24px rgba(0,0,0,0.5);
      opacity: 0; transform: translateY(6px);
      transition: opacity 0.2s, transform 0.2s;
      pointer-events: none; z-index: 999;
    }}
    #toast.show {{ opacity: 1; transform: translateY(0); }}
  </style>
</head>
<body>

<header>
  <div class="logo-mark">📅</div>
  <h1>{title}</h1>
  <div class="header-right">
    <div class="toolbar">
      <button class="btn btn-accent" onclick="fitAll()">⊞ Fit All</button>
      <button class="btn" onclick="zoomIn()">＋ Zoom In</button>
      <button class="btn" onclick="zoomOut()">－ Zoom Out</button>
      <button class="btn" onclick="goToday()">◎ Today</button>
      <button class="btn" onclick="toggleSort()">↕ Sort Rows</button>
      <div class="divider"></div>
      <button class="btn btn-export" onclick="exportJSON()">⬇ JSON</button>
      <button class="btn btn-export" onclick="exportCSV()">⬇ CSV</button>
    </div>
    <div class="badge" id="taskCount"></div>
  </div>
</header>

<div class="main">
  <aside class="sidebar">

    <!-- Milestone filter -->
    <div class="panel-header">
      <h2>Milestones</h2>
      <div class="panel-toggle-row">
        <button class="btn" onclick="toggleGroup('milestone', true)">✓</button>
        <button class="btn" onclick="toggleGroup('milestone', false)">✕</button>
      </div>
    </div>

    <!-- Task-type filter -->
    <div class="panel-header" style="border-top: 1px solid var(--border);">
      <h2>Task Types</h2>
      <div class="panel-toggle-row">
        <button class="btn" onclick="toggleGroup('type', true)">✓</button>
        <button class="btn" onclick="toggleGroup('type', false)">✕</button>
      </div>
    </div>

    <div class="sidebar-scroll">
      <div>
          <div class="section-label">Project Summary</div>
          <div class="summary-box">
            <div class="summary-row"><span class="summary-key">Start</span><span class="summary-val">{p_start_str}</span></div>
            <div class="summary-row"><span class="summary-key">End</span><span class="summary-val">{p_end_str}</span></div>
            <div class="summary-row"><span class="summary-key">Duration</span><span class="summary-val">{p_dur_days} days</span></div>
            <div class="summary-row"><span class="summary-key">Resources</span><span class="summary-val">{total_resources}</span></div>
          </div>
      </div>
      
      <hr class="section-sep"/>

      <div>
          <div class="section-label">Milestones</div>
          <div id="legendMilestone"></div>
      </div>

      <hr class="section-sep"/>

      <div>
          <div class="section-label">Task Types</div>
          <div id="legendType"></div>
      </div>
      
      <hr class="section-sep"/>

      <div>
          <div class="section-label">Dependencies</div>
          <div class="filter-item">
            <input type="checkbox" id="toggleTaskArrows" checked onchange="onToggleTaskArrows(this)"/>
            <span class="filter-label">Show Task Arrows</span>
          </div>
      </div>
      
      <hr class="section-sep"/>
      
      <div>
          <div class="section-label">Requirements</div>
          <div class="req-box">{req_text}</div>
      </div>
    </div>
  </aside>

  <div class="main-content">
    <div id="gantt"></div>
    <div id="resourceGraph"></div>
    <svg id="criticalSvg">
      <defs>
        <marker id="arrowhead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <polygon points="0 0, 6 3, 0 6" fill="#E8453C" />
        </marker>
        <marker id="arrowhead-task" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto">
          <polygon points="0 0, 6 3, 0 6" fill="#6b728e" />
        </marker>
      </defs>
    </svg>
  </div>
</div>

<div id="toast"></div>

<script>
  // ── Injected data ────────────────────────────────────────────────────────────
  const ALL_ITEMS      = {items_json};
  const ALL_GROUPS     = {groups_json};
  const MILESTONE_META = {milestone_meta_json};   // [{{id, label, color}}, …]
  const TASK_TYPES     = {task_types_json};        // ['part_model', 'part_list', …]
  const TYPE_PALETTE   = {type_palette_json};

  const RESOURCE_DATA  = {resource_data_json};
  const TOTAL_RESOURCES = {total_resources};
  const CRITICAL_LINKS = {critical_links_json}; // Original critical path links
  const ALL_TASK_LINKS = {all_links_json};

  // ── Active filter state ───────────────────────────────────────────────────────
  const hiddenMilestones = new Set();   // milestone_id strings that are OFF
  const hiddenTypes      = new Set();   // type strings that are OFF
  let showAllTaskArrows = true; // State for toggling all task arrows

  // ── Vis.js setup ─────────────────────────────────────────────────────────────
  const dataset = new vis.DataSet(ALL_ITEMS);
  const groups  = new vis.DataSet(ALL_GROUPS);

  document.getElementById('taskCount').textContent =
    `${{ALL_ITEMS.length}} tasks · ${{ALL_GROUPS.length}} rows`;

  const timelineOptions = {{
      height:       '100%',
      orientation:  {{ axis: 'top' }},
      stack:        true,
      stackSubgroups: true,
      moveable:     true,
      zoomable:     true,
      selectable:   true,
      multiselect:  false,
      tooltip:      {{ followMouse: true, overflowMethod: 'flip' }},
      zoomMin: 1000 * 60 * 60,
      zoomMax: 1000 * 60 * 60 * 24 * 365 * 2,
      margin: {{ item: {{ horizontal: 2, vertical: 4 }}, axis: 6 }},
      format: {{
        minorLabels: {{
          minute: 'HH:mm', hour: 'HH:mm',
          day: 'D MMM', week: 'D MMM', month: 'MMM YYYY'
        }},
        majorLabels: {{
          hour: 'ddd D MMM', day: 'MMMM YYYY',
          week: 'MMMM YYYY', month: 'YYYY'
        }}
      }},
  }};

  const timeline = new vis.Timeline(
    document.getElementById('gantt'),
    dataset,
    groups,
    timelineOptions
  );

  const resDataset = new vis.DataSet(RESOURCE_DATA);
  const resOptions = {{
      height: '100%',
      drawPoints: false,
      interpolation: {{ parametrization: 'step' }},
      shaded: {{ orientation: 'bottom' }},
      dataAxis: {{
        visible: true,
        left: {{
            title: {{ text: `Active Tasks (limit: ${{TOTAL_RESOURCES}})` }},
            format: function (value) {{ return Math.round(value); }}
        }}
      }},
      zoomMin: timelineOptions.zoomMin,
      zoomMax: timelineOptions.zoomMax,
  }};
  
  const resourceGraph = new vis.Graph2d(
      document.getElementById('resourceGraph'),
      resDataset,
      resOptions
  );

  // Sync range changes between timeline and graph
  timeline.on('rangechange', function (properties) {{
      if (properties.byUser) {{
          resourceGraph.setOptions({{ start: properties.start, end: properties.end }});
      }}
  }});
  resourceGraph.on('rangechange', function (properties) {{
      if (properties.byUser) {{
          timeline.setOptions({{ start: properties.start, end: properties.end }});
      }}
  }});

  // ── Toolbar ───────────────────────────────────────────────────────────────────
  function fitAll()  {{ timeline.fit(); }}
  function zoomIn()  {{ timeline.zoomIn(0.5); }}
  function zoomOut() {{ timeline.zoomOut(0.5); }}
  function goToday() {{ timeline.moveTo(new Date()); }}
  
  let sortAlpha = false;
  function toggleSort() {{
    sortAlpha = !sortAlpha;
    let gArray = Object.values(groups.get());
    if (sortAlpha) {{
        gArray.sort((a,b) => a.content.localeCompare(b.content));
    }} else {{
        // Recover original chronological order from ALL_GROUPS
        let orderMap = new Map();
        ALL_GROUPS.forEach((g, idx) => orderMap.set(g.id, idx));
        gArray.sort((a,b) => (orderMap.get(a.id) || 0) - (orderMap.get(b.id) || 0));
    }}
    // Apply order
    groups.clear();
    groups.add(gArray);
    drawDependencyArrows();
  }}

  // ── Re-apply all active filters and refresh dataset ───────────────────────────
  function applyFilters() {{
    const visible = ALL_ITEMS.filter(item => {{
      const milestoneOk = !hiddenMilestones.has(item._milestone_id || '__none__');
      const typeOk      = !hiddenTypes.has(item._type);
      return milestoneOk && typeOk;
    }});
    dataset.clear();
    dataset.add(visible);

    // Hide/show row labels for rows that have no visible items
    const visibleNames = new Set(visible.map(i => i.group));
    ALL_GROUPS.forEach(g => {{
      groups.update({{ id: g.id, visible: visibleNames.has(g.id) }});
    }});
    
    setTimeout(drawDependencyArrows, 50);
  }}

  // ── Sidebar: Milestones ───────────────────────────────────────────────────────
  const legendMilestone = document.getElementById('legendMilestone');
  MILESTONE_META.forEach(m => {{
    const label = document.createElement('label');
    label.className = 'filter-item';
    label.title = m.label;
    label.innerHTML = `
      <input type="checkbox" checked data-milestone="${{m.id}}" onchange="onMilestoneFilter(this)"/>
      <span class="filter-dot" style="background:${{m.color}}"></span>
      <span class="filter-label">${{m.label}}</span>
    `;
    legendMilestone.appendChild(label);
  }});

  function onMilestoneFilter(cb) {{
    if (cb.checked) hiddenMilestones.delete(cb.dataset.milestone);
    else            hiddenMilestones.add(cb.dataset.milestone);
    applyFilters();
  }}

  // ── Sidebar: Task Types ───────────────────────────────────────────────────────
  const legendType = document.getElementById('legendType');
  TASK_TYPES.forEach(tp => {{
    const color = TYPE_PALETTE[tp] || '#9B59B6';
    const label = document.createElement('label');
    label.className = 'filter-item';
    label.innerHTML = `
      <input type="checkbox" checked data-type="${{tp}}" onchange="onTypeFilter(this)"/>
      <span class="filter-dot" style="background:${{color}};border-radius:50%"></span>
      <span class="filter-label">${{tp}}</span>
    `;
    legendType.appendChild(label);
  }});

  function onTypeFilter(cb) {{
    if (cb.checked) hiddenTypes.delete(cb.dataset.type);
    else            hiddenTypes.add(cb.dataset.type);
    applyFilters();
  }}

  // ── Toggle-all helpers ────────────────────────────────────────────────────────
  function toggleGroup(kind, checked) {{
    const selector = kind === 'milestone'
      ? '#legendMilestone input'
      : '#legendType input';
    document.querySelectorAll(selector).forEach(cb => {{
      cb.checked = checked;
      if (kind === 'milestone') {{
        if (checked) hiddenMilestones.delete(cb.dataset.milestone);
        else         hiddenMilestones.add(cb.dataset.milestone);
      }} else {{
        if (checked) hiddenTypes.delete(cb.dataset.type);
        else         hiddenTypes.add(cb.dataset.type);
      }}
    }});
    applyFilters();
  }}
  
  function onToggleTaskArrows(cb) {{
    showAllTaskArrows = cb.checked;
    drawDependencyArrows();
  }}

  // ── Draw SVG Arrows for Critical Path ──────────────────────────────────────────
  const CRITICAL_LINKS = {critical_links_json}; // Assuming critical_links is still passed for identification
  const svgOverlay = document.getElementById('criticalSvg');
  
  function drawDependencyArrows() {{
      // clear existing paths (keep defs)
      const paths = svgOverlay.querySelectorAll('path');
      paths.forEach(p => p.remove());

      if (ALL_TASK_LINKS.length === 0 && CRITICAL_LINKS.length === 0) return;

      const ganttRect = document.getElementById('gantt').getBoundingClientRect();
      const panelOuter = document.querySelector('.vis-panel.vis-center');
      if (!panelOuter) return;
      const panelRect = panelOuter.getBoundingClientRect();

      // We need offset relative to our absolute SVG container
      const offsetX = panelRect.left - ganttRect.left;
      const offsetY = panelRect.top - ganttRect.top;

      ALL_TASK_LINKS.forEach(link => {{
          const isCritical = CRITICAL_LINKS.some(cl => cl.from === link.from && cl.to === link.to);

          if (!showAllTaskArrows && !isCritical) return; // Skip if not showing all and not critical

          const itemFrom = timeline.itemSet.items[link.from];
          const itemTo = timeline.itemSet.items[link.to];

          if (itemFrom && itemTo && itemFrom.displayed && itemTo.displayed) {{
               // Extract DOM element boxes inside the vis-panel
               const bFrom = itemFrom.dom.box.getBoundingClientRect();
               const bTo = itemTo.dom.box.getBoundingClientRect();

               // Calculate relative coordinates in our SVG space
               const x1 = (bFrom.right - panelRect.left) + offsetX;
               const y1 = (bFrom.top + bFrom.height/2 - panelRect.top) + offsetY;
               const x2 = (bTo.left - panelRect.left) + offsetX;
               const y2 = (bTo.top + bTo.height/2 - panelRect.top) + offsetY;

               const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
               path.setAttribute('class', isCritical ? 'cp-path' : 'task-path');
               path.setAttribute('marker-end', isCritical ? 'url(#arrowhead)' : 'url(#arrowhead-task)');

               // Check if successor is on a different row, if so use an S-curve, otherwise straight line
               if (Math.abs(y1 - y2) < 5) {{
                   path.setAttribute('d', `M ${{x1}} ${{y1}} L ${{x2}} ${{y2}}`);
               }} else {{
                   const cpX = (x1 + x2) / 2;
                   path.setAttribute('d', `M ${{x1}} ${{y1}} C ${{cpX}} ${{y1}}, ${{cpX}} ${{y2}}, ${{x2}} ${{y2}}`);
               }}
               svgOverlay.appendChild(path);
          }}
      }});
  }}

  timeline.on('changed', drawDependencyArrows);
  timeline.on('scroll', drawDependencyArrows);

  // ── Export ───────────────────────────────────────────────────────────────────
  function showToast(msg) {{
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 2500);
  }}

  function exportJSON() {{
    const rows = ALL_ITEMS.map(item => ({{
      id: item._task_id, name: item._name,
      milestone: item._milestone, type: item._type,
      part: item._part, duration_h: item._duration_h,
      start: item._start, end: item._end,
      predecessors: item._preds, successors: item._succs,
    }}));
    _download(new Blob([JSON.stringify(rows, null, 2)], {{type: 'application/json'}}), 'gantt_tasks.json');
    showToast('✓ JSON exported');
  }}

  function exportCSV() {{
    const cols = ['id','name','milestone','type','part','duration_h','start','end','predecessors','successors'];
    const esc  = v => `"${{String(v ?? '').replace(/"/g,'""')}}"`;
    const rows = [cols.join(',')];
    ALL_ITEMS.forEach(item => rows.push([
      item._task_id, item._name, item._milestone, item._type,
      item._part,    item._duration_h, item._start, item._end,
      item._preds,   item._succs,
    ].map(esc).join(',')));
    _download(new Blob([rows.join('\\n')], {{type: 'text/csv'}}), 'gantt_tasks.csv');
    showToast('✓ CSV exported');
  }}

  function _download(blob, filename) {{
    const url = URL.createObjectURL(blob);
    const a = Object.assign(document.createElement('a'), {{href:url, download:filename}});
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
  }}

  setTimeout(() => {{
    timeline.fit();
    drawDependencyArrows(); // Draw arrows after initial fit
  }}, 150);
</script>
</body>
</html>
"""

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding='utf-8')
    if DEBUG:
        print(f"Interactive Gantt saved to: {output_path}")
