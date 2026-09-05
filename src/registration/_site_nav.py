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

from pathlib import Path

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
  /* forces the second row to start at Objects, so the bar breaks brand+results+studies /
     objects+tool instead of leaving Tool alone on a line of its own */
  .sitenav .row-break { flex-basis:100%; height:0; }
"""


def _link(href: str, label: str, active: bool) -> str:
    current = ' aria-current="page"' if active else ''
    return f'<a href="{href}"{current}>{label}</a>'


def sync_index(path: Path | None = None) -> None:
    """Rewrite site/index.html's copy of the bar (CSS + markup) from this module.

    index.html is the one page no builder generates, so its nav is a copy - and a copy is a
    thing that goes stale. Running this after any edit here keeps it identical:

        python src/registration/_site_nav.py
    """
    import re

    path = path or Path(__file__).resolve().parents[2] / "site" / "index.html"
    s = path.read_text(encoding="utf-8")
    s2, n_css = re.subn(r"\n  /\* site navigation.*?\.sitenav \.row-break \{[^}]*\}\n",
                        NAV_CSS.rstrip("\n") + "\n", s, flags=re.S)
    if not n_css:  # first sync, or the CSS block predates .row-break
        s2, n_css = re.subn(r'\n  /\* site navigation.*?aria-current="page"\] \{[^}]*\}\n',
                            NAV_CSS.rstrip("\n") + "\n", s, flags=re.S)
    s3, n_nav = re.subn(r'<nav class="sitenav">.*?</nav>\n', nav_html("index"), s2, flags=re.S)
    if not (n_css and n_nav):
        raise SystemExit(f"{path}: found {n_css} nav CSS block(s) and {n_nav} <nav> - fix by hand")
    path.write_text(s3, encoding="utf-8")
    print(f"Synced the nav in {path}")


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
        '    <span class="row-break"></span>\n'
        f'    <span class="group"><span class="lbl">Objects</span>{objects}</span>\n'
        f'    <span class="group"><span class="lbl">Tool</span>'
        f'{_link("tuner.html", "gap tuner", active == "tuner")}</span>\n'
        '  </nav>\n'
    )


if __name__ == "__main__":
    sync_index()
