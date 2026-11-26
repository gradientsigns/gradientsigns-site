#!/usr/bin/env python3
"""Build the Gradient Signs website service-area map.

Renders a light Census / Natural Earth basemap of the New York region
with a solid ~4-hour ring and a dashed inner ring, in royal purple.
Home base is Commack, NY.

Shapefiles are not stored in this repo. Point MAP_DATA (and MAP_FONTS)
at a local copy of the line-card data, then run:

    MAP_DATA=/path/to/line-card/data \\
    MAP_FONTS=/path/to/line-card/assets/fonts \\
    python3 scripts/build-service-area-map.py

Outputs (under assets/ by default):
    service-area-map.webp      ~1600px wide
    service-area-map-2x.webp   ~3200px wide
"""

from __future__ import annotations

import argparse
import math
import os
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.patheffects
import numpy as np
import shapefile
from matplotlib.collections import LineCollection, PatchCollection
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Circle, PathPatch
from matplotlib.path import Path as MplPath
from PIL import Image
from pyproj import Transformer
from shapely.geometry import shape as shp_shape
from shapely.ops import transform as shp_transform

mpl.patheffects = matplotlib.patheffects
mpl.rcParams["axes.linewidth"] = 0

# Commack, NY hamlet center (not a street address)
HOME_LAT = 40.8433
HOME_LON = -73.2831
HOME_NAME = "Commack, NY"

# Approximate drive-time rings as straight-line radii (not true isochrones)
RING_2H_MI = 100.0
RING_4H_MI = 200.0

FOCUS_STATES = {"NY", "NJ", "PA", "CT", "MA"}
NEIGHBOR_STATES = {"NY", "NJ", "PA", "CT", "MA", "RI", "DE", "MD", "VT", "NH", "DC"}

PURPLE = "#661AFF"
PURPLE_LT = "#8B6BFF"
PURPLE_DK = "#5512E0"
INK = "#1C1C1C"
MUTED = "#4A5560"
WATER = "#D4E3EC"
LAND = "#F8F6F3"
LAND_OTHER = "#ECEAE6"
COUNTY = "#D0D5CC"
STATE = "#6E787F"
ROAD = "#C4B8A4"
ROAD_MAJ = "#A89880"
STATE_LABEL = "#5C6570"
OCEAN_LABEL = "#6A8494"

CITIES = [
    ("New York City", 40.7128, -74.0060, (8, -10), "right"),
    ("Philadelphia", 39.9526, -75.1652, (-8, -11), "right"),
    ("Albany", 42.6526, -73.7562, (8, 8), "left"),
    ("Hartford", 41.7658, -72.6734, (8, 8), "left"),
]

# Lon/lat anchors so labels stay put when the projection center moves
STATE_LABELS = [
    ("NEW YORK", -75.55, 42.35),
    ("NEW JERSEY", -74.55, 40.05),
    ("PENNSYLVANIA", -76.85, 40.95),
    ("CONNECTICUT", -72.55, 41.55),
    ("MASSACHUSETTS", -72.15, 42.35),
]
LONG_ISLAND = (-72.58, 40.88)
ATLANTIC = (-71.85, 39.55)

# Geographic window in miles from Commack
XMIN, XMAX = -270.0, 220.0
YMIN, YMAX = -230.0, 235.0

AEQD = (
    f"+proj=aeqd +lat_0={HOME_LAT} +lon_0={HOME_LON} "
    "+x_0=0 +y_0=0 +datum=WGS84 +units=mi +no_defs"
)
TO_XY = Transformer.from_crs("EPSG:4326", AEQD, always_xy=True)


def data_dir() -> Path:
    return Path(os.environ.get("MAP_DATA", "/workspace/line-card/data"))


def fonts_dir() -> Path:
    return Path(os.environ.get("MAP_FONTS", "/workspace/line-card/assets/fonts"))


def font(name: str, size: float) -> FontProperties:
    path = fonts_dir() / name
    if path.exists():
        return FontProperties(fname=str(path), size=size)
    family = "Oswald" if name.startswith("Oswald") else "DejaVu Sans"
    weight = "bold" if "Bold" in name else ("medium" if "SemiBold" in name or "Medium" in name else "normal")
    return FontProperties(family=family, size=size, weight=weight)


def fp_oswald_m(s):
    return font("Oswald-Medium.ttf", s)


def fp_oswald_r(s):
    return font("Oswald-Regular.ttf", s)


def fp_inter_r(s):
    return font("Inter-Regular.ttf", s)


def fp_inter_m(s):
    return font("Inter-Medium.ttf", s)


def fp_inter_sb(s):
    return font("Inter-SemiBold.ttf", s)


def fp_inter_b(s):
    return font("Inter-Bold.ttf", s)


def project_geom(geom):
    return shp_transform(lambda x, y, z=None: TO_XY.transform(x, y), geom)


def geom_from_shape(shp_obj):
    return shp_shape(shp_obj.__geo_interface__)


def path_from_polygon(poly):
    def ring(coords):
        coords = list(coords)
        if coords[0] != coords[-1]:
            coords.append(coords[0])
        n = len(coords)
        codes = [MplPath.MOVETO] + [MplPath.LINETO] * (n - 2) + [MplPath.CLOSEPOLY]
        return coords, codes

    verts, codes = ring(poly.exterior.coords)
    for interior in poly.interiors:
        v, c = ring(interior.coords)
        verts.extend(v)
        codes.extend(c)
    return MplPath(verts, codes)


def patches_from_geom(geom, **kw):
    patches = []
    if geom.is_empty:
        return patches
    geoms = [geom] if geom.geom_type == "Polygon" else list(geom.geoms) if geom.geom_type == "MultiPolygon" else []
    for g in geoms:
        patches.append(PathPatch(path_from_polygon(g), **kw))
    return patches


def load_states():
    path = data_dir() / "cb_2024_us_state_5m" / "cb_2024_us_state_5m.shp"
    focus, other = [], []
    r = shapefile.Reader(str(path))
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        st = rec["STUSPS"]
        if st not in NEIGHBOR_STATES:
            continue
        geom = project_geom(geom_from_shape(sr.shape))
        if geom.is_empty:
            continue
        (focus if st in FOCUS_STATES else other).append((st, rec["NAME"], geom))
    return focus, other


def load_counties():
    path = data_dir() / "cb_2024_us_county_5m" / "cb_2024_us_county_5m.shp"
    out = []
    r = shapefile.Reader(str(path))
    for sr in r.iterShapeRecords():
        rec = sr.record.as_dict()
        if rec["STUSPS"] not in FOCUS_STATES:
            continue
        geom = project_geom(geom_from_shape(sr.shape))
        if geom.is_empty:
            continue
        out.append((rec["STUSPS"], rec["NAME"], geom))
    return out


def lines_from_geom(geom):
    segs = []
    if geom.geom_type == "LineString":
        segs.append(np.array(geom.coords))
    elif geom.geom_type == "MultiLineString":
        for g in geom.geoms:
            segs.append(np.array(g.coords))
    return segs


def load_roads():
    path = data_dir() / "ne_10m_roads" / "ne_10m_roads.shp"
    major, secondary = [], []
    r = shapefile.Reader(str(path))
    for sr in r.iterShapeRecords():
        b = sr.shape.bbox
        if b[2] < -82 or b[0] > -67 or b[3] < 37 or b[1] > 46:
            continue
        rec = sr.record.as_dict()
        if rec.get("sov_a3") not in ("USA", "CAN", ""):
            continue
        typ = rec.get("type") or ""
        if typ == "Ferry Route":
            continue
        rank = rec.get("scalerank") or 10
        expr = rec.get("expressway") or 0
        geom = project_geom(geom_from_shape(sr.shape))
        if geom.is_empty:
            continue
        segs = lines_from_geom(geom)
        is_major = typ in ("Major Highway", "Beltway") or expr == 1 or rank <= 3
        (major if is_major else secondary).extend(segs)
    return major, secondary


def load_lakes():
    path = data_dir() / "ne_10m_lakes" / "ne_10m_lakes.shp"
    out = []
    r = shapefile.Reader(str(path))
    for sr in r.iterShapeRecords():
        b = sr.shape.bbox
        if b[2] < -82 or b[0] > -67 or b[3] < 37 or b[1] > 46:
            continue
        geom = project_geom(geom_from_shape(sr.shape))
        if geom.is_empty:
            continue
        out.append(geom)
    return out


def add_geom_patches(ax, geoms, facecolor, edgecolor, lw, zorder, alpha=1.0):
    patches = []
    for g in geoms:
        patches.extend(
            patches_from_geom(g, facecolor=facecolor, edgecolor=edgecolor, lw=lw, alpha=alpha)
        )
    if patches:
        ax.add_collection(PatchCollection(patches, match_original=True, zorder=zorder))


def add_scale_bar(ax, x, y, miles=50, color=INK, fontsize=7):
    hw = miles / 2
    ax.plot([x - hw, x + hw], [y, y], color=color, lw=1.6, solid_capstyle="butt", zorder=20)
    ax.plot([x - hw, x - hw], [y - 3, y + 3], color=color, lw=1.6, zorder=20)
    ax.plot([x, x], [y - 2.2, y + 2.2], color=color, lw=1.0, zorder=20)
    ax.plot([x + hw, x + hw], [y - 3, y + 3], color=color, lw=1.6, zorder=20)
    ax.text(x, y + 8, f"{int(miles)} miles", ha="center", va="bottom", color=color, fontproperties=fp_inter_m(fontsize), zorder=20)
    ax.text(x - hw, y - 8, "0", ha="center", va="top", color=color, fontproperties=fp_inter_r(fontsize - 1), zorder=20)
    ax.text(x + hw, y - 8, str(int(miles)), ha="center", va="top", color=color, fontproperties=fp_inter_r(fontsize - 1), zorder=20)


def add_north_arrow(ax, x, y, color=INK, size=16):
    ax.annotate(
        "",
        xy=(x, y + size),
        xytext=(x, y),
        arrowprops=dict(arrowstyle="-|>", color=color, lw=1.4, mutation_scale=12),
        zorder=20,
    )
    ax.text(x, y + size + 6, "N", ha="center", va="bottom", color=color, fontproperties=fp_oswald_m(8), zorder=20)


def halo_text(ax, x, y, text, fp, color=INK, ha="left", va="center", zorder=22):
    ax.text(
        x,
        y,
        text,
        ha=ha,
        va=va,
        fontproperties=fp,
        color=color,
        zorder=zorder,
        path_effects=[
            mpl.patheffects.withStroke(linewidth=3.0, foreground="white", capstyle="round", joinstyle="round")
        ],
    )


def polygon_outlines(geoms):
    lines = []
    for g in geoms:
        parts = [g] if g.geom_type == "Polygon" else list(g.geoms) if g.geom_type == "MultiPolygon" else []
        for p in parts:
            lines.append(np.array(p.exterior.coords))
            for ring in p.interiors:
                lines.append(np.array(ring.coords))
    return lines


def draw_basemap(ax, states_focus, states_other, counties, roads_maj, roads_sec, lakes):
    ax.set_facecolor(WATER)
    ax.set_aspect("equal")
    ax.set_xlim(XMIN, XMAX)
    ax.set_ylim(YMIN, YMAX)
    ax.axis("off")

    add_geom_patches(ax, [g for _, _, g in states_other], LAND_OTHER, "none", 0, zorder=1)
    add_geom_patches(ax, [g for _, _, g in states_focus], LAND, "none", 0, zorder=2)
    add_geom_patches(ax, lakes, WATER, "none", 0, zorder=3)

    county_lines = polygon_outlines([g for _, _, g in counties])
    if county_lines:
        ax.add_collection(LineCollection(county_lines, colors=COUNTY, linewidths=0.25, zorder=4, capstyle="round"))

    if roads_sec:
        ax.add_collection(LineCollection(roads_sec, colors=ROAD, linewidths=0.35, zorder=5, alpha=0.7, capstyle="round"))
    if roads_maj:
        ax.add_collection(LineCollection(roads_maj, colors=ROAD_MAJ, linewidths=0.7, zorder=6, capstyle="round"))

    state_lines = polygon_outlines([g for _, _, g in states_focus + states_other])
    if state_lines:
        ax.add_collection(LineCollection(state_lines, colors=STATE, linewidths=0.9, zorder=7, capstyle="round"))

    # Pale purple fills, then the dashed inner ring and solid 4-hour ring
    ax.add_patch(Circle((0, 0), RING_4H_MI, facecolor=PURPLE, edgecolor="none", alpha=0.08, zorder=3.5))
    ax.add_patch(Circle((0, 0), RING_2H_MI, facecolor=PURPLE_LT, edgecolor="none", alpha=0.14, zorder=3.6))
    ax.add_patch(
        Circle((0, 0), RING_2H_MI, facecolor="none", edgecolor=PURPLE_LT, lw=1.35, linestyle=(0, (4, 2.5)), zorder=9)
    )
    ax.add_patch(Circle((0, 0), RING_4H_MI, facecolor="none", edgecolor=PURPLE, lw=1.7, linestyle="solid", zorder=9))

    def ring_label(radius, text, angle_deg, inward=14):
        ang = math.radians(angle_deg)
        r = radius - inward
        x = r * math.cos(ang)
        y = r * math.sin(ang)
        halo_text(ax, x, y, text, fp_inter_sb(7.5), color=PURPLE_DK, ha="center", va="center")

    ring_label(RING_2H_MI, "Approx. 2 hours  ·  100 miles", -32, inward=14)
    ring_label(RING_4H_MI, "Approx. 4 hours  ·  200 miles", 8, inward=16)

    for name, lon, lat in STATE_LABELS:
        x, y = TO_XY.transform(lon, lat)
        halo_text(ax, x, y, name, fp_oswald_m(9), color=STATE_LABEL, ha="center", va="center")

    x, y = TO_XY.transform(*LONG_ISLAND)
    halo_text(ax, x, y, "LONG ISLAND", fp_oswald_m(7), color=STATE_LABEL, ha="center", va="center")
    x, y = TO_XY.transform(*ATLANTIC)
    halo_text(ax, x, y, "ATLANTIC OCEAN", fp_oswald_r(8), color=OCEAN_LABEL, ha="center", va="center")

    for name, lat, lon, offset, ha in CITIES:
        x, y = TO_XY.transform(lon, lat)
        ax.plot(x, y, "o", ms=4.2, color=INK, zorder=21, markeredgecolor="white", markeredgewidth=0.7)
        halo_text(ax, x + offset[0], y + offset[1], name, fp_inter_sb(7.4), color=INK, ha=ha, va="center")

    ax.plot(
        0,
        0,
        marker="*",
        markersize=16,
        color=PURPLE,
        markeredgecolor="white",
        markeredgewidth=0.6,
        zorder=23,
    )
    halo_text(ax, 8, -16, HOME_NAME, fp_inter_b(8), color=PURPLE_DK, ha="left", va="center", zorder=24)

    add_scale_bar(ax, -200, -195, miles=50, color=INK, fontsize=7)
    add_north_arrow(ax, -245, -175, color=INK, size=16)
    return ax


def compose(out_dir: Path) -> None:
    print("Loading shapefiles…")
    states_focus, states_other = load_states()
    counties = load_counties()
    roads_maj, roads_sec = load_roads()
    lakes = load_lakes()
    print(
        f"states focus={len(states_focus)} other={len(states_other)} "
        f"counties={len(counties)} roads maj/sec={len(roads_maj)}/{len(roads_sec)} lakes={len(lakes)}"
    )

    # 10 in wide; 320 dpi yields a 3200px 2x master, then a 1600px 1x
    width_in = 10.0
    data_aspect = (XMAX - XMIN) / (YMAX - YMIN)
    side = 0.18
    map_w = width_in - 2 * side
    map_h = map_w / data_aspect
    height_in = map_h + 2 * side
    dpi_2x = 320

    fig = plt.figure(figsize=(width_in, height_in), dpi=dpi_2x, facecolor="white")
    ax = fig.add_axes([side / width_in, side / height_in, map_w / width_in, map_h / height_in])
    draw_basemap(ax, states_focus, states_other, counties, roads_maj, roads_sec, lakes)
    for spine in ax.spines.values():
        spine.set_visible(True)
        spine.set_color("#C8CDD2")
        spine.set_linewidth(0.6)

    from io import BytesIO
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi_2x, facecolor="white")
    plt.close(fig)
    buf.seek(0)
    im_2x = Image.open(buf).convert("RGB")
    im_1x = im_2x.resize((im_2x.width // 2, im_2x.height // 2), Image.Resampling.LANCZOS)

    for src, name in ((im_1x, "service-area-map.webp"), (im_2x, "service-area-map-2x.webp")):
        dest = out_dir / name
        src.save(dest, format="WEBP", quality=88, method=6)
        print("wrote", dest, src.size, f"{dest.stat().st_size / 1024:.0f} KB")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None, help="Output directory (default: repo assets/)")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    out_dir = args.out or (repo / "assets")
    out_dir.mkdir(parents=True, exist_ok=True)
    if not data_dir().exists():
        raise SystemExit(
            f"MAP_DATA not found: {data_dir()}\n"
            "Set MAP_DATA to the line-card data directory (Census + Natural Earth shapefiles)."
        )
    compose(out_dir)


if __name__ == "__main__":
    main()
