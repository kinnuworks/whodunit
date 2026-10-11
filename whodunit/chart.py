"""Draw the simulator's accuracy curves as SVG, and write the same numbers as tables.

Hand-written SVG, so the eval has no plotting dependency and the charts share the case
file's paper and ribbon colours. Each file carries its own dark variant.
"""

import math
from pathlib import Path

SERIES = (
    # key, label, css class
    ("statistical", "Statistical bisect, named at 95% and right", "s-named"),
    ("statistical_top", "Statistical bisect, top suspect is right", "s-top"),
    ("plain_repeated", "Plain bisect, repeats to fill the budget", "s-repeat"),
    ("plain_once", "Plain bisect, one replay per commit", "s-once"),
)

STYLE = """
  .paper { fill: #F3EDDF; } .ink { fill: #201B15; } .muted { fill: #6B6156; }
  .rule { stroke: #D8CDB6; stroke-width: 1; } .axis { stroke: #6B6156; stroke-width: 1; }
  .title { font: 400 27px 'Young Serif', Georgia, serif; }
  .sub, .panel, .tick, .legend { font-family: 'Alegreya Sans', 'Gill Sans', 'Trebuchet MS', sans-serif; }
  .sub { font-size: 15px; } .panel { font-size: 15px; font-weight: 700; } .tick { font-size: 13px; } .legend { font-size: 15px; }
  .line { fill: none; stroke-linejoin: round; stroke-linecap: round; }
  .s-named { stroke: #B4261F; stroke-width: 2.5; }
  .s-top { stroke: #B4261F; stroke-width: 1.5; stroke-dasharray: 5 4; }
  .s-repeat { stroke: #201B15; stroke-width: 2; }
  .s-once { stroke: #6B6156; stroke-width: 2; stroke-dasharray: 1 5; }
  .hit { fill: transparent; }
  @media (prefers-color-scheme: dark) {
    .paper { fill: #1B1714; } .ink { fill: #EDE4D3; } .muted { fill: #A3978A; }
    .rule { stroke: #3A3128; } .axis { stroke: #A3978A; }
    .s-named, .s-top { stroke: #E5604F; } .s-repeat { stroke: #EDE4D3; } .s-once { stroke: #A3978A; }
  }
"""


def _value(cell: dict, key: str) -> float:
    return (cell["top_right"] if key == "statistical_top" else cell["right"]) / cell["trials"]


def _points(sweep: dict, key: str, rate: float) -> list[tuple[int, float, dict]]:
    method = "statistical" if key == "statistical_top" else key
    cells = [c for c in sweep["cells"] if c["method"] == method and c["bad_rate"] == rate]
    return [(c["budget"], _value(c, key), c) for c in sorted(cells, key=lambda c: c["budget"])]


def accuracy_svg(sweep: dict, title: str, subtitle: str) -> str:
    rates = sorted({c["bad_rate"] for c in sweep["cells"]}, reverse=True)
    budgets = sorted({c["budget"] for c in sweep["cells"]})
    columns, plot_w, plot_h = 3, 280, 150
    left, top, gap_x, gap_y = 64, 150, 56, 78
    rows = math.ceil(len(rates) / columns)
    width = left + columns * plot_w + (columns - 1) * gap_x + 40
    height = top + rows * plot_h + (rows - 1) * gap_y + 70
    lo, hi = math.log2(budgets[0]), math.log2(budgets[-1])
    ticks = [b for b in (10, 20, 40, 80, 160, 320) if budgets[0] <= b <= budgets[-1]]

    def x(budget: float) -> float:
        return (math.log2(budget) - lo) / (hi - lo) * plot_w

    def y(share: float) -> float:
        return plot_h - share * plot_h

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" aria-label="{title}. {subtitle}">',
        f"<style>{STYLE}</style>",
        f'<rect class="paper" width="{width}" height="{height}"/>',
        f'<text class="title ink" x="{left}" y="48">{title}</text>',
        f'<text class="sub muted" x="{left}" y="74">{subtitle}</text>',
    ]
    for n, (key, label, css) in enumerate(SERIES):
        lx, ly = left + (n % 2) * 470, 100 + (n // 2) * 24
        out.append(f'<line class="line {css}" x1="{lx}" y1="{ly}" x2="{lx + 34}" y2="{ly}"/>')
        out.append(f'<text class="legend ink" x="{lx + 44}" y="{ly + 5}">{label}</text>')
    for n, rate in enumerate(rates):
        ox = left + (n % columns) * (plot_w + gap_x)
        oy = top + (n // columns) * (plot_h + gap_y) + 30
        out.append(f'<g transform="translate({ox},{oy})">')
        out.append(f'<text class="panel ink" x="0" y="-14">The bug fails {rate:.0%} of the time</text>')
        for share in (0.0, 0.5, 1.0):
            out.append(f'<line class="rule" x1="0" y1="{y(share):.1f}" x2="{plot_w}" y2="{y(share):.1f}"/>')
            out.append(f'<text class="tick muted" x="-8" y="{y(share) + 4:.1f}" text-anchor="end">{share:.0%}</text>')
        out.append(f'<line class="axis" x1="0" y1="{plot_h}" x2="{plot_w}" y2="{plot_h}"/>')
        for b in ticks:
            out.append(f'<line class="axis" x1="{x(b):.1f}" y1="{plot_h}" x2="{x(b):.1f}" y2="{plot_h + 4}"/>')
            out.append(f'<text class="tick muted" x="{x(b):.1f}" y="{plot_h + 19}" text-anchor="middle">{b}</text>')
        if n + columns >= len(rates):  # nothing is drawn below this panel
            out.append(f'<text class="tick muted" x="{plot_w / 2}" y="{plot_h + 40}" text-anchor="middle">replays allowed</text>')
        # Draw the baselines first so the statistical bisect sits on top.
        for key, label, css in reversed(SERIES):
            points = _points(sweep, key, rate)
            path = " ".join(f"{'M' if i == 0 else 'L'}{x(b):.1f},{y(v):.1f}" for i, (b, v, _) in enumerate(points))
            out.append(f'<path class="line {css}" d="{path}"/>')
        for key, label, css in SERIES:
            for b, v, cell in _points(sweep, key, rate):
                wrong = f", wrong in {wrong_of_accused(cell)} accusations" if key != "statistical_top" and cell["right"] + cell["wrong"] else ""
                out.append(f'<circle class="hit" cx="{x(b):.1f}" cy="{y(v):.1f}" r="7"><title>{label}: {v:.0%} at {b} replays{wrong}</title></circle>')
        out.append("</g>")
    out.append("</svg>")
    return "\n".join(out) + "\n"


def wrong_of_accused(cell: dict) -> str:
    """Of the cases where a commit was named, how many named the wrong one: "3% (4 of 131)"."""
    accused = cell["right"] + cell["wrong"]
    return f"{cell['wrong'] / accused:.0%} ({cell['wrong']} of {accused})" if accused else "nobody named"


def table_markdown(sweep: dict) -> str:
    rates = sorted({c["bad_rate"] for c in sweep["cells"]}, reverse=True)
    budgets = sorted({c["budget"] for c in sweep["cells"]})
    lines = []
    for rate in rates:
        lines.append(f"The bug fails {rate:.0%} of the time. In the first four rows each cell is right / wrong / nobody named, as a percentage of all cases. "
                     "The last three rows count only the cases where a commit was named, and give the share of those that named the wrong one.\n")
        lines.append("| Replays allowed | " + " | ".join(str(b) for b in budgets) + " |")
        lines.append("| --- |" + " ---: |" * len(budgets))
        for key, label, _ in SERIES:
            if key == "statistical_top":
                row = [f"{v:.0%}" for _, v, _ in _points(sweep, key, rate)]
            else:
                row = [f"{c['right'] / c['trials']:.0%} / {c['wrong'] / c['trials']:.0%} / {c['nobody'] / c['trials']:.0%}" for _, _, c in _points(sweep, key, rate)]
            lines.append(f"| {label} | " + " | ".join(row) + " |")
        for key, label in (("statistical", "Statistical bisect"), ("plain_repeated", "Plain bisect with repeats"), ("plain_once", "Plain bisect, one replay")):
            lines.append(f"| {label}: wrong, of accusations made | " + " | ".join(wrong_of_accused(c) for _, _, c in _points(sweep, key, rate)) + " |")
        lines.append("")
    return "\n".join(lines)


def write_charts(results: dict, out: Path) -> None:
    tables = ["# Simulator tables\n", "Generated by `python -m whodunit.simulate`. The charts in this folder draw the same numbers.\n"]
    for name, sweep in results.items():
        good = sweep["good_rate"]
        baseline = "Good commits never fail." if good == 0 else f"Good commits fail {good:.0%} of the time on their own."
        subtitle = f"{sweep['suspects']} suspects, {sweep['trials']} simulated cases per point. {baseline}"
        title = "How often the right commit is named"
        (out / f"accuracy-{name.replace('_', '-')}.svg").write_text(accuracy_svg(sweep, title, subtitle))
        tables += [f"## {baseline}\n", f"{sweep['suspects']} suspects and {sweep['trials']} simulated cases per cell.\n", table_markdown(sweep)]
    (out / "tables.md").write_text("\n".join(tables))
