#!/usr/bin/env python3
"""Bandwise IELTS progress dashboard generator.

Scans the Bandwise archive (Markdown files with YAML frontmatter produced by
the IELTS-prep Claude Code skills) and renders a single self-contained
``dashboard.html`` with inline SVG charts. No third-party dependencies are
used: only the Python 3 standard library. The output HTML embeds all styling
and chart geometry inline so it opens offline by double-click.

Data root resolution order:
  1. ``--root <path>`` CLI argument
  2. ``IELTS_COACH_HOME`` environment variable
  3. ``~/ielts-coach`` default

Usage:
  python3 dashboard.py [--root PATH] [--out PATH]
"""

from __future__ import annotations

import argparse
import html
import os
import sys
from datetime import datetime

# --- Tunable constants -----------------------------------------------------

# Target band per skill used to draw the reference line on the radar chart.
TARGET_SCORES = {"L": 8.0, "R": 8.0, "W": 7.0, "S": 7.0}

# Color palette.
COL_OPUS = "#2563eb"
COL_GPT5 = "#db2777"
COL_TARGET = "#94a3b8"
COL_ACTUAL = "#16a34a"
COL_BAR = "#7c3aed"
COL_GRID = "#e2e8f0"
COL_AXIS = "#64748b"
COL_LISTEN = "#0891b2"


# ---------------------------------------------------------------------------
# Minimal YAML frontmatter parser
# ---------------------------------------------------------------------------

def _coerce_scalar(token):
    """Convert a raw scalar string into a Python value."""
    token = token.strip()
    if token == "" or token == "~":
        return None
    low = token.lower()
    if low == "null":
        return None
    if low == "true":
        return True
    if low == "false":
        return False
    # Strip matching quotes.
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        return token[1:-1]
    # Numbers.
    try:
        if any(c in token for c in (".", "e", "E")) and token not in ("-", "+"):
            return float(token)
        return int(token)
    except ValueError:
        pass
    try:
        return float(token)
    except ValueError:
        return token


def _parse_inline(text):
    """Parse an inline ``{...}`` dict or ``[...]`` list (best effort)."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        body = text[1:-1].strip()
        result = {}
        for part in _split_top_level(body):
            if ":" not in part:
                continue
            k, v = part.split(":", 1)
            result[k.strip()] = _parse_value(v.strip())
        return result
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        if not body:
            return []
        return [_parse_value(p.strip()) for p in _split_top_level(body)]
    return _coerce_scalar(text)


def _split_top_level(body):
    """Split on commas that are not inside nested brackets/braces/quotes."""
    parts = []
    depth = 0
    quote = None
    buf = []
    for ch in body:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            continue
        if ch in "{[":
            depth += 1
            buf.append(ch)
            continue
        if ch in "}]":
            depth -= 1
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p.strip() != ""]


def _parse_value(text):
    """Parse a value that may be inline structured or a plain scalar."""
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return _parse_inline(text)
    return _coerce_scalar(text)


def _indent_of(line):
    return len(line) - len(line.lstrip(" "))


def _parse_block(lines, idx, base_indent):
    """Recursively parse a block of YAML lines starting at ``idx``.

    Returns (value, next_idx). ``value`` is a dict or list depending on the
    first meaningful line at ``base_indent``.
    """
    result_map = {}
    result_list = []
    is_list = None

    while idx < len(lines):
        raw = lines[idx]
        stripped = raw.strip()

        # Blank lines and comments are skipped.
        if stripped == "" or stripped.startswith("#"):
            idx += 1
            continue

        indent = _indent_of(raw)
        if indent < base_indent:
            break

        if indent > base_indent:
            # Should have been consumed by a child parse; skip defensively.
            idx += 1
            continue

        # List item.
        if stripped.startswith("- "):
            is_list = True
            item_text = stripped[2:].strip()
            if item_text.startswith("{") or item_text.startswith("["):
                result_list.append(_parse_inline(item_text))
                idx += 1
            elif item_text == "" or item_text.endswith(":"):
                # Nested block item.
                value, idx = _parse_block(lines, idx + 1, base_indent + 2)
                result_list.append(value)
            else:
                result_list.append(_parse_value(item_text))
                idx += 1
            continue
        if stripped == "-":
            is_list = True
            value, idx = _parse_block(lines, idx + 1, base_indent + 2)
            result_list.append(value)
            continue

        # Mapping line.
        if ":" not in stripped:
            idx += 1
            continue
        key, _, rest = stripped.partition(":")
        key = key.strip()
        rest = rest.strip()
        is_list = False if is_list is None else is_list

        if rest in ("|", ">", "|-", ">-", "|+", ">+"):
            # Multi-line scalar block: skip its body, store as None.
            idx += 1
            while idx < len(lines):
                nxt = lines[idx]
                if nxt.strip() == "":
                    idx += 1
                    continue
                if _indent_of(nxt) > base_indent:
                    idx += 1
                    continue
                break
            result_map[key] = None
            continue

        if rest == "":
            # Could be a nested map, nested list, or empty value.
            # Look ahead at the next meaningful line.
            look = idx + 1
            while look < len(lines) and (
                lines[look].strip() == "" or lines[look].strip().startswith("#")
            ):
                look += 1
            if look < len(lines) and _indent_of(lines[look]) > base_indent:
                value, idx = _parse_block(lines, look, _indent_of(lines[look]))
                result_map[key] = value
            else:
                result_map[key] = None
                idx += 1
            continue

        # Inline value.
        result_map[key] = _parse_value(rest)
        idx += 1

    if is_list:
        return result_list, idx
    return result_map, idx


def parse_frontmatter(text):
    """Extract and parse the YAML frontmatter block from a file's text."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}
    block = lines[1:end]
    value, _ = _parse_block(block, 0, 0)
    return value if isinstance(value, dict) else {}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _read_md_dir(path):
    """Return list of parsed frontmatter dicts for all .md files in path."""
    records = []
    if not os.path.isdir(path):
        return records
    for name in sorted(os.listdir(path)):
        if not name.endswith(".md"):
            continue
        fpath = os.path.join(path, name)
        if not os.path.isfile(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        fm = parse_frontmatter(text)
        if fm:
            fm["_file"] = name
            records.append(fm)
    return records


def load_data(root):
    return {
        "writing": _read_md_dir(os.path.join(root, "writing")),
        "listening": _read_md_dir(os.path.join(root, "listening")),
        "mock": _read_md_dir(os.path.join(root, "mock")),
    }


# ---------------------------------------------------------------------------
# Small helpers for safe access
# ---------------------------------------------------------------------------

def _as_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _get(d, *keys):
    cur = d
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _esc(value):
    return html.escape(str(value))


# ---------------------------------------------------------------------------
# SVG chart builders
# ---------------------------------------------------------------------------

def _no_data():
    return '<p class="nodata">暂无数据</p>'


def line_chart(series, width=520, height=240, ylabel="", y_min=None, y_max=None):
    """Render a multi-line chart.

    series: list of dicts {label, color, points: [(x_label, y_value), ...]}
    Only points with numeric y are plotted.
    """
    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 40
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # Collect all x labels (preserve order from the first non-empty series'
    # x sequence) and all y values.
    x_labels = []
    all_y = []
    for s in series:
        for xl, yv in s["points"]:
            if xl not in x_labels:
                x_labels.append(xl)
            if yv is not None:
                all_y.append(yv)
    if not all_y or not x_labels:
        return _no_data()

    lo = y_min if y_min is not None else min(all_y)
    hi = y_max if y_max is not None else max(all_y)
    if hi == lo:
        hi = lo + 1.0
        lo = lo - 1.0
    # Add a little headroom.
    span = hi - lo
    lo -= span * 0.08
    hi += span * 0.08

    n = len(x_labels)
    if n == 1:
        x_at = {x_labels[0]: pad_l + plot_w / 2.0}
    else:
        x_at = {
            xl: pad_l + (i / (n - 1)) * plot_w for i, xl in enumerate(x_labels)
        }

    def y_at(v):
        return pad_t + plot_h - ((v - lo) / (hi - lo)) * plot_h

    parts = ['<svg viewBox="0 0 %d %d" class="chart" role="img">' % (width, height)]

    # Grid lines + y ticks.
    ticks = 4
    for t in range(ticks + 1):
        val = lo + (hi - lo) * t / ticks
        yy = y_at(val)
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
            'stroke-width="1"/>' % (pad_l, yy, width - pad_r, yy, COL_GRID)
        )
        parts.append(
            '<text x="%.1f" y="%.1f" class="ytick">%.1f</text>'
            % (pad_l - 6, yy + 3, val)
        )

    # X labels (show first, middle, last to avoid clutter).
    show_idx = {0, n - 1, n // 2}
    for i, xl in enumerate(x_labels):
        if i in show_idx:
            xx = x_at[xl]
            parts.append(
                '<text x="%.1f" y="%.1f" class="xtick">%s</text>'
                % (xx, height - pad_b + 18, _esc(xl))
            )

    # Plot each series.
    for s in series:
        pts = [(x_at[xl], y_at(yv)) for xl, yv in s["points"] if yv is not None and xl in x_at]
        if not pts:
            continue
        if len(pts) >= 2:
            d = "M " + " L ".join("%.1f %.1f" % p for p in pts)
            parts.append(
                '<path d="%s" fill="none" stroke="%s" stroke-width="2.5"/>'
                % (d, s["color"])
            )
        for px, py in pts:
            parts.append(
                '<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>'
                % (px, py, s["color"])
            )

    parts.append("</svg>")

    # Legend.
    legend = ['<div class="legend">']
    for s in series:
        if any(yv is not None for _, yv in s["points"]):
            legend.append(
                '<span class="lg"><i style="background:%s"></i>%s</span>'
                % (s["color"], _esc(s["label"]))
            )
    legend.append("</div>")

    label_html = (
        '<div class="ylabel">%s</div>' % _esc(ylabel) if ylabel else ""
    )
    return label_html + "".join(parts) + "".join(legend)


def radar_chart(scores, target, size=320):
    """Render a 4-axis radar (L, R, W, S) actual vs target."""
    axes = ["L", "R", "W", "S"]
    actual = [_as_float(scores.get(a)) for a in axes]
    if not any(v is not None for v in actual):
        return _no_data()

    cx = cy = size / 2.0
    radius = size / 2.0 - 46
    max_band = 9.0
    import math

    # Axis angles: top, right, bottom, left.
    angles = [-math.pi / 2 + i * (2 * math.pi / len(axes)) for i in range(len(axes))]

    def point(value, angle):
        r = (value / max_band) * radius
        return (cx + r * math.cos(angle), cy + r * math.sin(angle))

    parts = ['<svg viewBox="0 0 %d %d" class="chart radar" role="img">' % (size, size)]

    # Concentric grid rings at bands 3,5,7,9.
    for band in (3, 5, 7, 9):
        ring = [point(band, a) for a in angles]
        d = "M " + " L ".join("%.1f %.1f" % p for p in ring) + " Z"
        parts.append(
            '<path d="%s" fill="none" stroke="%s" stroke-width="1"/>'
            % (d, COL_GRID)
        )

    # Spokes + axis labels.
    for a, name in zip(angles, axes):
        ex, ey = point(max_band, a)
        parts.append(
            '<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
            'stroke-width="1"/>' % (cx, cy, ex, ey, COL_GRID)
        )
        lx, ly = point(max_band + 0.9, a)
        parts.append(
            '<text x="%.1f" y="%.1f" class="raxis">%s</text>' % (lx, ly + 4, name)
        )

    # Target polygon.
    tgt_pts = [point(_as_float(target.get(a)) or 0.0, ang) for a, ang in zip(axes, angles)]
    d_t = "M " + " L ".join("%.1f %.1f" % p for p in tgt_pts) + " Z"
    parts.append(
        '<path d="%s" fill="none" stroke="%s" stroke-width="2" '
        'stroke-dasharray="5 4"/>' % (d_t, COL_TARGET)
    )

    # Actual polygon (use 0 for missing axes so the shape closes).
    act_pts = [point(v if v is not None else 0.0, ang) for v, ang in zip(actual, angles)]
    d_a = "M " + " L ".join("%.1f %.1f" % p for p in act_pts) + " Z"
    parts.append(
        '<path d="%s" fill="%s" fill-opacity="0.18" stroke="%s" '
        'stroke-width="2.5"/>' % (d_a, COL_ACTUAL, COL_ACTUAL)
    )
    for (px, py), v in zip(act_pts, actual):
        if v is not None:
            parts.append('<circle cx="%.1f" cy="%.1f" r="3" fill="%s"/>' % (px, py, COL_ACTUAL))

    parts.append("</svg>")

    legend = (
        '<div class="legend">'
        '<span class="lg"><i style="background:%s"></i>最近模考</span>'
        '<span class="lg"><i style="background:%s"></i>目标</span></div>'
        % (COL_ACTUAL, COL_TARGET)
    )
    return "".join(parts) + legend


def hbar_chart(pairs, width=520, bar_h=24, gap=10):
    """Render a horizontal bar chart from [(label, count), ...] (pre-sorted)."""
    if not pairs:
        return _no_data()
    pad_l, pad_r, pad_t = 150, 40, 8
    n = len(pairs)
    height = pad_t + n * (bar_h + gap) + 8
    plot_w = width - pad_l - pad_r
    max_v = max(c for _, c in pairs) or 1

    parts = ['<svg viewBox="0 0 %d %d" class="chart" role="img">' % (width, height)]
    for i, (label, count) in enumerate(pairs):
        y = pad_t + i * (bar_h + gap)
        bw = (count / max_v) * plot_w
        parts.append(
            '<text x="%d" y="%.1f" class="blabel">%s</text>'
            % (pad_l - 8, y + bar_h * 0.7, _esc(label))
        )
        parts.append(
            '<rect x="%d" y="%.1f" width="%.1f" height="%d" rx="3" fill="%s"/>'
            % (pad_l, y, bw, bar_h, COL_BAR)
        )
        parts.append(
            '<text x="%.1f" y="%.1f" class="bval">%d</text>'
            % (pad_l + bw + 6, y + bar_h * 0.7, count)
        )
    parts.append("</svg>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Section assembly
# ---------------------------------------------------------------------------

def build_writing_trend(writing):
    opus_pts = []
    gpt5_pts = []
    rows = []
    for rec in writing:
        date = rec.get("date") or rec.get("_file", "")
        opus = _as_float(_get(rec, "ai_scores", "opus", "overall"))
        gpt5 = _as_float(_get(rec, "ai_scores", "gpt5", "overall"))
        rows.append((str(date), opus, gpt5))
    rows.sort(key=lambda r: r[0])
    for date, opus, gpt5 in rows:
        opus_pts.append((date, opus))
        gpt5_pts.append((date, gpt5))
    series = [{"label": "Opus 总分", "color": COL_OPUS, "points": opus_pts}]
    if any(g is not None for _, g in gpt5_pts):
        series.append({"label": "GPT-5 总分", "color": COL_GPT5, "points": gpt5_pts})
    return line_chart(series, ylabel="分数", y_min=4.0, y_max=9.0)


def build_radar(mock):
    if not mock:
        return _no_data()
    rows = sorted(mock, key=lambda r: str(r.get("date") or r.get("_file", "")))
    latest = rows[-1]
    scores = _get(latest, "scores") or {}
    if not isinstance(scores, dict):
        return _no_data()
    return radar_chart(scores, TARGET_SCORES)


def build_error_bars(writing, listening):
    counts = {}
    for rec in list(writing) + list(listening):
        errs = rec.get("errors")
        if not isinstance(errs, list):
            continue
        for e in errs:
            if not isinstance(e, dict):
                continue
            tag = e.get("tag")
            if tag is None:
                continue
            inc = e.get("count")
            inc = inc if isinstance(inc, int) and inc > 0 else 1
            counts[str(tag)] = counts.get(str(tag), 0) + inc
    if not counts:
        return _no_data()
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]
    return hbar_chart(top)


def build_listening_trend(listening):
    rows = []
    for rec in listening:
        date = str(rec.get("date") or rec.get("_file", ""))
        total = rec.get("total_questions")
        correct = rec.get("correct_count")
        pct = None
        if isinstance(total, (int, float)) and total and isinstance(correct, (int, float)):
            pct = round(100.0 * correct / total, 1)
        rows.append((date, pct))
    rows.sort(key=lambda r: r[0])
    series = [{"label": "正确率 %", "color": COL_LISTEN, "points": rows}]
    return line_chart(series, ylabel="%", y_min=0.0, y_max=100.0)


def build_summary(data):
    writing = data["writing"]
    listening = data["listening"]
    mock = data["mock"]

    latest_band = "—"
    if mock:
        rows = sorted(mock, key=lambda r: str(r.get("date") or r.get("_file", "")))
        band = _as_float(_get(rows[-1], "scores", "overall"))
        if band is not None:
            latest_band = "%.1f" % band

    open_verif = 0
    for rec in list(writing) + list(listening):
        ov = rec.get("open_verifications")
        if isinstance(ov, list):
            open_verif += len(ov)

    cards = [
        ("写作篇数", len(writing)),
        ("听力套数", len(listening)),
        ("模考次数", len(mock)),
        ("最近模考总分", latest_band),
        ("待核验项", open_verif),
    ]
    items = []
    for label, value in cards:
        items.append(
            '<div class="card"><div class="cval">%s</div>'
            '<div class="clabel">%s</div></div>' % (_esc(value), _esc(label))
        )
    return '<div class="cards">%s</div>' % "".join(items)


# ---------------------------------------------------------------------------
# HTML page
# ---------------------------------------------------------------------------

STYLE = """
:root { --bg:#f1f5f9; --panel:#ffffff; --ink:#0f172a; --muted:#64748b; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei","Hiragino Sans GB",Roboto,Helvetica,Arial,sans-serif;
  line-height:1.45; }
.wrap { max-width:1100px; margin:0 auto; padding:28px 20px 60px; }
header h1 { font-size:26px; margin:0 0 4px; letter-spacing:-0.01em; }
header .ts { color:var(--muted); font-size:13px; margin:0 0 24px; }
.cards { display:flex; flex-wrap:wrap; gap:14px; margin-bottom:28px; }
.card { flex:1 1 160px; background:var(--panel); border:1px solid #e2e8f0;
  border-radius:12px; padding:16px 18px; box-shadow:0 1px 2px rgba(15,23,42,.04); }
.card .cval { font-size:30px; font-weight:700; color:#1e293b; }
.card .clabel { color:var(--muted); font-size:13px; margin-top:2px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr));
  gap:20px; }
.panel { background:var(--panel); border:1px solid #e2e8f0; border-radius:14px;
  padding:18px 20px; box-shadow:0 1px 2px rgba(15,23,42,.04); }
.panel h2 { font-size:16px; margin:0 0 12px; color:#1e293b; }
.chart { width:100%; height:auto; display:block; }
.radar { max-width:340px; margin:0 auto; }
.ytick,.xtick { fill:#64748b; font-size:11px; }
.xtick { text-anchor:middle; }
.ytick { text-anchor:end; }
.raxis { fill:#334155; font-size:13px; font-weight:600; text-anchor:middle; }
.blabel { fill:#334155; font-size:12px; text-anchor:end; }
.bval { fill:#475569; font-size:12px; }
.ylabel { color:var(--muted); font-size:12px; margin-bottom:4px; }
.legend { display:flex; flex-wrap:wrap; gap:16px; margin-top:8px; }
.lg { font-size:12px; color:var(--muted); display:inline-flex; align-items:center; }
.lg i { width:12px; height:12px; border-radius:3px; display:inline-block;
  margin-right:6px; }
.nodata { color:var(--muted); font-style:italic; font-size:14px;
  padding:24px 0; text-align:center; }
footer { color:var(--muted); font-size:12px; margin-top:30px; text-align:center; }
"""


def render_html(data, root):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = build_summary(data)
    writing_trend = build_writing_trend(data["writing"])
    radar = build_radar(data["mock"])
    error_bars = build_error_bars(data["writing"], data["listening"])
    listen_trend = build_listening_trend(data["listening"])

    panels = [
        ("写作分数趋势", writing_trend),
        ("四科雷达（最近模考 vs 目标）", radar),
        ("高频错误标签", error_bars),
        ("听力正确率趋势", listen_trend),
    ]
    panel_html = "".join(
        '<section class="panel"><h2>%s</h2>%s</section>' % (_esc(title), body)
        for title, body in panels
    )

    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bandwise · 雅思备考进度面板</title>
<style>%s</style>
</head>
<body>
<div class="wrap">
<header>
<h1>Bandwise · 雅思备考进度面板</h1>
<p class="ts">生成时间 %s · 数据目录：%s</p>
</header>
%s
<div class="grid">%s</div>
<footer>由 Bandwise 面板生成器生成 · 完全离线 · 零依赖</footer>
</div>
</body>
</html>
""" % (STYLE, _esc(ts), _esc(root), summary, panel_html)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def resolve_root(cli_root):
    if cli_root:
        return os.path.abspath(os.path.expanduser(cli_root))
    env = os.environ.get("IELTS_COACH_HOME")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.abspath(os.path.expanduser("~/ielts-coach"))


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="dashboard.py",
        description="生成 Bandwise 雅思备考进度面板 "
        "（dashboard.html，内嵌 SVG 图表）。",
    )
    parser.add_argument(
        "--root",
        help="数据根目录。未设置时回退到 $IELTS_COACH_HOME，"
        "再回退到 ~/ielts-coach。",
    )
    parser.add_argument(
        "--out",
        help="输出 HTML 路径（默认 <root>/dashboard.html）。",
    )
    args = parser.parse_args(argv)

    root = resolve_root(args.root)
    out = args.out
    if out:
        out = os.path.abspath(os.path.expanduser(out))
    else:
        out = os.path.join(root, "dashboard.html")

    data = load_data(root)
    page = render_html(data, root)

    out_dir = os.path.dirname(out) or "."
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(page)
    except OSError as exc:
        print("错误：无法写入 %s：%s" % (out, exc), file=sys.stderr)
        return 1

    total = sum(len(v) for v in data.values())
    print(
        "已生成 %s（写作=%d，听力=%d，模考=%d；共 %d 个文件）"
        % (out, len(data["writing"]), len(data["listening"]), len(data["mock"]), total)
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
