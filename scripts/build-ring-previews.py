#!/usr/bin/env python3
"""Build undistorted light and dark ring-style coverage maps for preview.

Rings are straight-line distance, sized from real uncongested drive times
measured earlier from the Nassau/Suffolk line at the LIE. Longitude is scaled
by cos(40.8°) so a mile east matches a mile north, and the SVG viewBox uses
that same square scale.
"""

import math
from pathlib import Path

import shapefile

ROOT = Path(__file__).resolve().parents[1]
STATES = Path("/tmp/geo/states/cb_2023_us_state_500k.shp")
COUNTIES = Path("/tmp/geo/counties/cb_2023_us_county_500k.shp")

# Nassau/Suffolk border nearest the Long Island Expressway.
ORIGIN = (40.76164, -73.44052)
COMMACK = (40.84347, -73.28332)
LAT0 = 40.8
MILES = 69.172
COS = math.cos(math.radians(LAT0))

CORE = {"36059", "36103", "36061", "36047", "36081", "36005", "36085"}
DRAW_STATES = {"NY", "NJ", "PA", "CT", "MA", "RI", "DE", "MD", "VT", "NH", "DC"}

CITIES = [
    ("New York", 40.7128, -74.0060),
    ("Philadelphia", 39.9526, -75.1652),
    ("Albany", 42.6526, -73.7562),
    ("Hartford", 41.7658, -72.6734),
    ("Boston", 42.3601, -71.0589),
    ("Baltimore", 39.2904, -76.6122),
]
STATE_LABELS = [
    ("NEW YORK", 42.20, -75.30),
    ("NEW JERSEY", 40.10, -74.55),
    ("PENNSYLVANIA", 40.95, -76.60),
    ("CONNECTICUT", 41.60, -72.70),
    ("MASSACHUSETTS", 42.25, -71.80),
]


def miles(lon, lat):
    x = (lon - ORIGIN[1]) * COS * MILES
    y = (lat - ORIGIN[0]) * MILES
    return x, y


def haversine(lat, lon):
    radius = 3958.8
    p1, p2 = math.radians(ORIGIN[0]), math.radians(lat)
    dp, dl = math.radians(lat - ORIGIN[0]), math.radians(lon - ORIGIN[1])
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def rings_of(shape):
    pts = shape.points
    parts = list(shape.parts) + [len(pts)]
    out = []
    for i in range(len(parts) - 1):
        ring = pts[parts[i] : parts[i + 1]]
        if len(ring) >= 4:
            if ring[0] != ring[-1]:
                ring.append(ring[0])
            out.append(ring)
    return out


def ring_area(ring):
    area = 0.0
    for i in range(len(ring) - 1):
        area += ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]
    return abs(area) / 2


def douglas(points, eps):
    if len(points) < 3:
        return points

    def dist(p, a, b):
        dx, dy = b[0] - a[0], b[1] - a[1]
        if dx == dy == 0:
            return math.hypot(p[0] - a[0], p[1] - a[1])
        t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
        return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))

    dmax, idx = 0.0, 0
    for i in range(1, len(points) - 1):
        d = dist(points[i], points[0], points[-1])
        if d > dmax:
            dmax, idx = d, i
    if dmax > eps:
        return douglas(points[: idx + 1], eps)[:-1] + douglas(points[idx:], eps)
    return [points[0], points[-1]]


def path_d(rings, project, eps):
    chunks = []
    for ring in rings:
        projected = [project(lon, lat) for lon, lat in ring]
        simplified = douglas(projected, eps)
        if len(simplified) < 4:
            continue
        clean = [simplified[0]]
        for pt in simplified[1:]:
            if math.hypot(pt[0] - clean[-1][0], pt[1] - clean[-1][1]) > eps * 0.25:
                clean.append(pt)
        if len(clean) < 4:
            continue
        parts = [f"M{clean[0][0]:.1f} {clean[0][1]:.1f}"]
        parts += [f"L{x:.1f} {y:.1f}" for x, y in clean[1:]]
        parts.append("Z")
        chunks.append("".join(parts))
    return "".join(chunks)


def choose_radii():
    cities = {name: haversine(lat, lon) for name, lat, lon in CITIES}
    for name, dist in sorted(cities.items(), key=lambda item: item[1]):
        print(f"  {name:16} {dist:6.1f} mi")
    # Just past Hartford and Philadelphia, short of Albany.
    radius_3h = max(cities["Hartford"], cities["Philadelphia"]) + 8
    # Just past Boston and Baltimore, short of a longer reach such as Washington.
    radius_5h = max(cities["Boston"], cities["Baltimore"]) + 12
    print(f"ring 3h {radius_3h:.1f} mi   ring 5h {radius_5h:.1f} mi")
    return radius_3h, radius_5h


def load_geometry():
    states, core = [], []
    state_reader = shapefile.Reader(str(STATES))
    for shape, rec in zip(state_reader.shapes(), state_reader.records()):
        info = rec.as_dict()
        if info["STUSPS"] not in DRAW_STATES:
            continue
        rings = rings_of(shape)
        if not rings:
            continue
        states.append((info["STUSPS"], rings))
    county_reader = shapefile.Reader(str(COUNTIES))
    for shape, rec in zip(county_reader.shapes(), county_reader.records()):
        info = rec.as_dict()
        if info["GEOID"] not in CORE:
            continue
        rings = rings_of(shape)
        if rings:
            core.append(rings)
    return states, core


THEMES = {
    "light": {
        "water": "#d4e3ec",
        "land": "#f8f6f3",
        "stroke": "#6e787f",
        "core": "#7851A9",
        "core_line": "#5c3488",
        "ring3": "#7851A9",
        "ring3_fill": "rgba(120,81,169,0.16)",
        "ring5": "#4169E1",
        "ring5_fill": "rgba(65,105,225,0.10)",
        "label": "#1c1c1c",
        "label_halo": "#ffffff",
        "state": "#5c6570",
        "marker": "#7851A9",
    },
    "dark": {
        "water": "#10141c",
        "land": "#1c2128",
        "stroke": "#8b949e",
        "core": "#9b6fd4",
        "core_line": "#d4c4f0",
        "ring3": "#c4a8e8",
        "ring3_fill": "rgba(155,111,212,0.22)",
        "ring5": "#8eaaee",
        "ring5_fill": "rgba(65,105,225,0.16)",
        "label": "#f4f0e8",
        "label_halo": "#10141c",
        "state": "#b7b1a8",
        "marker": "#f4f0e8",
    },
}


def build_svg(theme_name, radius_3h, radius_5h, states, core):
    theme = THEMES[theme_name]
    pad = 55
    span = radius_5h + pad
    width = height = span * 2

    def project(lon, lat):
        x, y = miles(lon, lat)
        return x + span, span - y

    state_d = []
    for _abbr, rings in states:
        state_d.append(path_d(rings, project, 1.6))
    core_d = "".join(path_d(rings, project, 0.35) for rings in core)
    cx, cy = project(COMMACK[1], COMMACK[0])
    ox, oy = project(ORIGIN[1], ORIGIN[0])

    def label(name, lon, lat, kind):
        x, y = project(lon, lat)
        if not (18 < x < width - 18 and 16 < y < height - 16):
            return ""
        return f'<text class="{kind}" x="{x:.1f}" y="{y:.1f}">{name}</text>'

    labels = []
    for name, lat, lon in CITIES:
        labels.append(label(name, lon, lat, "city"))
    for name, lat, lon in STATE_LABELS:
        labels.append(label(name, lon, lat, "state"))
    # Ring labels sit in the Atlantic, southeast of the origin.
    labels.append(
        f'<text class="ring" x="{ox + radius_3h * 0.62:.1f}" y="{oy + radius_3h * 0.55:.1f}">About 3 hours</text>'
    )
    labels.append(
        f'<text class="ring" x="{ox + radius_5h * 0.72:.1f}" y="{oy + radius_5h * 0.42:.1f}">About 5 hours</text>'
    )

    # 50-mile scale bar, lower left. Same mile scale as the map.
    bar_x, bar_y = 36, height - 42
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:.1f} {height:.1f}" width="{width:.1f}" height="{height:.1f}" preserveAspectRatio="xMidYMid meet" role="img" aria-labelledby="service-map-title service-map-desc" style="aspect-ratio: 1 / 1">
  <title id="service-map-title">Coverage map with distance rings</title>
  <desc id="service-map-desc">Long Island and New York City are the core. The inner ring is about 3 hours and the outer ring is about 5 hours, as straight-line distance from the Nassau Suffolk line at the Long Island Expressway. The map scale is equal in both directions.</desc>
  <rect width="{width:.1f}" height="{height:.1f}" fill="{theme["water"]}"/>
  <g fill="{theme["land"]}" stroke="{theme["stroke"]}" stroke-width="0.8" stroke-linejoin="round">
    <path d="{''.join(state_d)}"/>
  </g>
  <circle cx="{ox:.1f}" cy="{oy:.1f}" r="{radius_5h:.1f}" fill="{theme["ring5_fill"]}" stroke="{theme["ring5"]}" stroke-width="1.6"/>
  <circle cx="{ox:.1f}" cy="{oy:.1f}" r="{radius_3h:.1f}" fill="{theme["ring3_fill"]}" stroke="{theme["ring3"]}" stroke-width="1.35" stroke-dasharray="5 3.2"/>
  <path d="{core_d}" fill="{theme["core"]}" stroke="{theme["core_line"]}" stroke-width="0.7" stroke-linejoin="round"/>
  <g class="home" aria-hidden="true">
    <circle cx="{cx:.1f}" cy="{cy:.1f}" r="5.2" fill="{theme["label_halo"]}"/>
    <circle cx="{cx:.1f}" cy="{cy:.1f}" r="2.5" fill="{theme["marker"]}"/>
  </g>
  <g class="scale" aria-hidden="true" fill="none" stroke="{theme["label"]}" stroke-width="1.1">
    <path d="M{bar_x:.1f} {bar_y:.1f} h50"/>
    <path d="M{bar_x:.1f} {bar_y-3:.1f} v6 M{bar_x+50:.1f} {bar_y-3:.1f} v6"/>
  </g>
  <text class="scale-label" x="{bar_x:.1f}" y="{bar_y+12:.1f}">50 miles</text>
  <g class="map-labels" aria-hidden="true">
    {''.join(labels)}
  </g>
</svg>'''
    return svg


PAGE = """<!DOCTYPE html>
<html lang="en" data-theme="{theme}">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Coverage map preview, {label} — Gradient Signs</title>
  <link rel="stylesheet" href="/assets/site.css" />
  <style>
    .preview-note {{ margin: 0 0 0.8rem; color: var(--muted); font-size: 0.88rem; }}
    .area-map svg {{
      display: block;
      width: 100%;
      height: auto;
      max-width: 100%;
      aspect-ratio: 1 / 1;
    }}
    .area-map .map-labels text, .area-map .scale-label {{
      font-family: Outfit, "Segoe UI", sans-serif;
      text-anchor: middle;
      fill: {label_fill};
      stroke: {halo};
      stroke-width: 3px;
      paint-order: stroke;
      font-size: 8px;
      font-weight: 500;
    }}
    .area-map .map-labels .state {{ font-size: 7px; letter-spacing: 0.12em; fill: {state_fill}; }}
    .area-map .map-labels .ring {{ font-size: 7.4px; fill: {ring_fill}; }}
    .area-map .scale-label {{ font-size: 7px; text-anchor: start; }}
    @media (max-width: 760px) {{
      .area-map .map-labels {{ display: none; }}
    }}
  </style>
</head>
<body>
  <header class="site-header">
    <a class="logo-link" href="/"><img class="logo logo-white" src="/assets/logo.png" alt="Gradient Signs" width="1216" height="645" />
      <img class="logo logo-blue" src="/assets/logo-dark.png" alt="" width="1216" height="645" /></a>
    <nav class="site-nav" aria-label="Primary">
      <a href="/">Home</a>
      <a href="/preview-map-light.html">Light map</a>
      <a href="/preview-map-dark.html">Dark map</a>
    </nav>
  </header>
  <main>
    <section class="service-area" aria-labelledby="service-area-title">
      <div class="wrap">
        <p class="eyebrow">Preview · {label}</p>
        <h2 id="service-area-title">Coverage</h2>
        <p class="lede">Core coverage: Long Island and New York City. We regularly travel 2–3 hours for surveys, installs, and service, and up to about 5 hours by arrangement.</p>
        <p class="preview-note">Not live. Rings are straight-line distance from the Nassau–Suffolk line, sized to those drive times. The scale is the same east–west and north–south.</p>
        <figure class="area-map">
          {svg}
          <figcaption class="area-caption">Core is Long Island and New York City. Inner ring, about 3 hours. Outer ring, about 5 hours.</figcaption>
        </figure>
        <dl class="coverage-sheet">
          <div>
            <dt>Coverage</dt>
            <dd>Nassau, Suffolk, NYC (5 boroughs)</dd>
          </div>
          <div>
            <dt>Regular travel</dt>
            <dd>2–3 hrs. New Jersey, Connecticut, Westchester and the Hudson Valley, eastern Pennsylvania.</dd>
          </div>
          <div>
            <dt>By arrangement</dt>
            <dd>Up to about 5 hrs.</dd>
          </div>
        </dl>
        <ul class="coverage-work">
          <li>Site surveys with photos and measurements</li>
          <li>Installs, removals, and service calls</li>
          <li>Photo documentation and closeout on every job</li>
          <li>Permit coordination</li>
          <li>Single point of contact</li>
        </ul>
        <p class="area-home">Commack, home base</p>
        <a class="btn" href="/request.html">Request work</a>
      </div>
    </section>
  </main>
</body>
</html>
"""


def main():
    print("Distances from the Nassau/Suffolk line:")
    radius_3h, radius_5h = choose_radii()
    states, core = load_geometry()
    pages = {
        "light": ("preview-map-light.html", "Light", THEMES["light"]),
        "dark": ("preview-map-dark.html", "Dark", THEMES["dark"]),
    }
    for name, (filename, label, theme) in pages.items():
        svg = build_svg(name, radius_3h, radius_5h, states, core)
        html = PAGE.format(
            theme=name,
            label=label,
            svg=svg,
            label_fill=theme["label"],
            halo=theme["label_halo"],
            state_fill=theme["state"],
            ring_fill=theme["ring3"] if name == "light" else theme["ring5"],
        )
        dest = ROOT / filename
        dest.write_text(html)
        print("wrote", dest, dest.stat().st_size)


if __name__ == "__main__":
    main()
