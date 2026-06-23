"""Session report generator.

Reads a session JSON log and produces either an HTML file or a PDF
(HTML printed to PDF via the stdlib webbrowser + OS print, or optional
weasyprint if installed).
"""
import json
import os
import webbrowser
from collections import Counter
from datetime import datetime


# ── Public API ────────────────────────────────────────────────────────────────

def generate(log_path: str, output_format: str = "html") -> str:
    """Generate a report from a session log file.

    Args:
        log_path: Path to the session JSON log.
        output_format: "html" or "pdf".

    Returns:
        Path to the generated report file.
    """
    with open(log_path) as f:
        data = json.load(f)

    html = _render_html(data)
    out_path = log_path.replace(".json", f".{output_format}")

    if output_format == "pdf":
        out_path = _to_pdf(html, out_path)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)

    return out_path


def open_report(path: str) -> None:
    """Open the report in the default browser."""
    webbrowser.open(f"file:///{os.path.abspath(path)}")


# ── PDF conversion ────────────────────────────────────────────────────────────

def _to_pdf(html: str, out_path: str) -> str:
    """Write PDF via weasyprint if available, otherwise fall back to HTML."""
    try:
        import weasyprint  # type: ignore
        weasyprint.HTML(string=html).write_pdf(out_path)
        return out_path
    except ImportError:
        # Fallback: save as HTML and open for browser print-to-PDF
        html_path = out_path.replace(".pdf", ".html")
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        return html_path


# ── Analysis helpers ──────────────────────────────────────────────────────────

def _event_summary(laps: list[dict]) -> dict[str, int]:
    """Count instinct event occurrences across all laps."""
    counts: Counter = Counter()
    for lap in laps:
        for ev in lap.get("instinct_events", []):
            counts[ev["kind"]] += 1
    return dict(counts.most_common())


def _lap_times(laps: list[dict]) -> list[float]:
    return [lap["lap_time_s"] for lap in laps if lap.get("lap_time_s")]


def _fmt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    return f"{int(m)}:{s:05.2f}"


def _improvement_tips(event_counts: dict[str, int],
                      avg_smoothness_brake: float,
                      avg_smoothness_throttle: float) -> list[str]:
    """Return ordered list of improvement recommendations."""
    tips: list[str] = []
    priority = [
        ("wheel_lock",            "Work on brake pressure — wheel lockups detected. Try releasing slightly earlier."),
        ("wheelspin",             "Ease throttle application at corner exit to reduce wheelspin."),
        ("throttle_snap",         "Apply throttle more progressively — snapping to full throttle is costing grip."),
        ("coasting",              "Eliminate coasting zones — you should be on brake or throttle at all times."),
        ("overlap",               "Avoid simultaneous brake and throttle unless intentionally left-foot braking."),
        ("steering_under_braking","Reduce steering angle at peak brake pressure — trail into the corner more gently."),
        ("trail_brake_poor",      "Improve trail braking — release the brake smoothly as you increase steering angle."),
        ("lateral_g_excess",      "Corner entry speed is too high — you are generating excessive lateral G."),
        ("fuel_warning",          "Monitor fuel consumption — you are burning above target rate."),
        ("consistency",           "Focus on consistency — your lap times have high variance."),
    ]
    for kind, tip in priority:
        if event_counts.get(kind, 0) > 0:
            tips.append(f"<strong>{event_counts[kind]}×</strong> {tip}")

    if avg_smoothness_brake < 0.6:
        tips.append("Brake inputs are rough — work on smooth, progressive brake application.")
    if avg_smoothness_throttle < 0.6:
        tips.append("Throttle inputs are rough — try to be smoother on the gas.")

    return tips


# ── HTML renderer ─────────────────────────────────────────────────────────────

def _render_html(data: dict) -> str:
    laps            = data.get("laps", [])
    times           = _lap_times(laps)
    event_counts    = _event_summary(laps)
    best_time       = min(times) if times else None
    avg_time        = sum(times) / len(times) if times else None
    avg_sb          = sum(l.get("smoothness_brake", 0) for l in laps) / max(len(laps), 1)
    avg_st          = sum(l.get("smoothness_throttle", 0) for l in laps) / max(len(laps), 1)
    tips            = _improvement_tips(event_counts, avg_sb, avg_st)
    generated_at    = datetime.now().strftime("%Y-%m-%d %H:%M")

    lap_rows = ""
    for lap in laps:
        t     = lap.get("lap_time_s")
        delta = lap.get("delta_s")
        pb    = "⭐" if lap.get("personal_best") else ""
        delta_str = (f'<span style="color:{"green" if delta and delta < 0 else "red"}">'
                     f'{delta:+.3f}s</span>') if delta is not None else "—"
        events_str = ", ".join(
            f'{e["kind"]} ({e.get("detail","")})'
            for e in lap.get("instinct_events", [])
        ) or "—"
        lap_rows += f"""
        <tr>
          <td>{lap.get("lap")}</td>
          <td>{_fmt_time(t) if t else "—"} {pb}</td>
          <td>{delta_str}</td>
          <td>{round(lap.get("smoothness_brake", 0) * 100)}%</td>
          <td>{round(lap.get("smoothness_throttle", 0) * 100)}%</td>
          <td style="font-size:0.85em;color:#888">{events_str}</td>
        </tr>"""

    tips_html = "".join(f"<li>{t}</li>" for t in tips) if tips else "<li>No major issues detected. Keep it up!</li>"

    event_badges = "".join(
        f'<span class="badge">{k}: {v}</span>'
        for k, v in event_counts.items()
    ) or '<span class="badge">None</span>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>pyracing-coach — Session Report</title>
<style>
  body {{ font-family: Arial, sans-serif; background: #1a1a2e; color: #e0e0e0; margin: 0; padding: 24px; }}
  h1   {{ color: #4fc3f7; margin-bottom: 4px; }}
  h2   {{ color: #81d4fa; border-bottom: 1px solid #333; padding-bottom: 6px; margin-top: 32px; }}
  .meta {{ color: #888; font-size: 0.9em; margin-bottom: 24px; }}
  .stats {{ display: flex; gap: 24px; flex-wrap: wrap; margin-bottom: 24px; }}
  .stat  {{ background: #16213e; border-radius: 8px; padding: 16px 24px; min-width: 120px; }}
  .stat .val {{ font-size: 1.8em; font-weight: bold; color: #4fc3f7; }}
  .stat .lbl {{ font-size: 0.8em; color: #888; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #333; }}
  th {{ color: #81d4fa; font-size: 0.85em; text-transform: uppercase; }}
  tr:hover {{ background: #16213e; }}
  .badge {{ display: inline-block; background: #0f3460; border-radius: 12px;
            padding: 2px 10px; margin: 2px; font-size: 0.8em; color: #81d4fa; }}
  ul {{ line-height: 2; padding-left: 20px; }}
  li {{ margin-bottom: 4px; }}
</style>
</head>
<body>
<h1>Session Report</h1>
<div class="meta">
  {data.get("car","?")} &nbsp;·&nbsp; {data.get("track","?")} &nbsp;·&nbsp;
  {data.get("session_start","?")} &nbsp;·&nbsp; Generated {generated_at}
</div>

<div class="stats">
  <div class="stat"><div class="val">{len(laps)}</div><div class="lbl">Laps</div></div>
  <div class="stat"><div class="val">{_fmt_time(best_time) if best_time else "—"}</div><div class="lbl">Best Lap</div></div>
  <div class="stat"><div class="val">{_fmt_time(avg_time) if avg_time else "—"}</div><div class="lbl">Avg Lap</div></div>
  <div class="stat"><div class="val">{round(avg_sb*100)}%</div><div class="lbl">Brake Smoothness</div></div>
  <div class="stat"><div class="val">{round(avg_st*100)}%</div><div class="lbl">Throttle Smoothness</div></div>
</div>

<h2>Instinct Events</h2>
<div>{event_badges}</div>

<h2>What to Improve</h2>
<ul>{tips_html}</ul>

<h2>Lap Detail</h2>
<table>
  <thead>
    <tr><th>Lap</th><th>Time</th><th>Delta</th><th>Brake Smooth</th><th>Throttle Smooth</th><th>Events</th></tr>
  </thead>
  <tbody>{lap_rows}</tbody>
</table>
</body>
</html>"""
