"""The one navigation bar every page on the site carries.

Until this existed, `index.html` was the only page with a link on it: anyone who opened
`frame_count_study.html` from the dissertation text or from a mail could not get back to the
index, and had no way of learning that six object pages and two more studies existed at all.

Every generated page pulls NAV_CSS into its <style> and nav_html("<page-id>") into the top of
its .page container; site/index.html is hand-written and carries the same markup inline, so
if you edit the structure here, mirror it there (the CSS lives in each page's own <style>,
the palette variables are already identical across all of them).
"""

from __future__ import annotations

# Page id -> (href, label). Order is the order in the bar.
STUDIES = [
    ("capture_comparison", "capture_comparison.html", "capture strategy"),
    ("frame_count_study", "frame_count_study.html", "frame count"),
    ("performance_study", "performance_study.html", "compute cost"),
]

# Object pages, largest/hardest first - same order and names as the index cards.
OBJECTS = [
    ("bus_stop", "bus_stop.html", "bus shelter"),
    ("information_sign", "information_sign.html", "information sign"),
    ("bench", "bench.html", "bench"),
    ("bollard", "bollard.html", "bollard"),
    ("flashlight", "flashlight.html", "lamppost"),
    ("bus_stop_sign", "bus_stop_sign.html", "bus-stop sign"),
]

NAV_CSS = """
  /* site navigation - see src/registration/_site_nav.py */
  .sitenav { display:flex; flex-wrap:wrap; align-items:baseline; gap:6px 18px; padding:9px 0 11px;
             border-bottom:1px solid var(--panel-border); margin-bottom:4px; font-size:12px; }
  .sitenav .brand { font-weight:650; color:var(--text); text-decoration:none; font-size:12.5px; }
  .sitenav .brand:hover { color:var(--accent); }
  .sitenav .group { display:flex; flex-wrap:wrap; align-items:baseline; gap:4px 9px; }
  .sitenav .group > .lbl { font-size:10px; font-weight:650; letter-spacing:.07em; text-transform:uppercase;
                           color:var(--text-faint); }
  .sitenav a { color:var(--text-dim); text-decoration:none; white-space:nowrap; }
  .sitenav a:hover { color:var(--accent); text-decoration:underline; }
  .sitenav a[aria-current="page"] { color:var(--text); font-weight:650; border-bottom:2px solid var(--accent); }
"""


def _link(href: str, label: str, active: bool) -> str:
    current = ' aria-current="page"' if active else ''
    return f'<a href="{href}"{current}>{label}</a>'


def nav_html(active: str = "") -> str:
    """`active` is a page id: "frame_count_study", "bollard", "results", "index", ..."""
    studies = " ".join(_link(h, lbl, active == pid) for pid, h, lbl in STUDIES)
    objects = " ".join(_link(h, lbl, active == pid) for pid, h, lbl in OBJECTS)
    return (
        '<nav class="sitenav">\n'
        f'    <a class="brand" href="index.html">photogrammetry vs&nbsp;LiDAR</a>\n'
        f'    <span class="group"><span class="lbl">Results</span>'
        f'{_link("results.html", "all objects × methods", active == "results")}</span>\n'
        f'    <span class="group"><span class="lbl">Studies</span>{studies}</span>\n'
        f'    <span class="group"><span class="lbl">Objects</span>{objects}</span>\n'
        f'    <span class="group"><span class="lbl">Tool</span>'
        f'{_link("tuner.html", "gap tuner", active == "tuner")}</span>\n'
        '  </nav>\n'
    )
