"""Preview images for back.py: the back as you'll see it from behind (with the boards
drawn in), a side view standing on the table, and a 3D view. Needs matplotlib."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import back as B  # noqa: E402

WOOD = "#b98b5a"


def _tris(m):
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    return v[np.asarray(mesh.tri_verts)]


def _shade(tris, light=(-0.4, -0.5, 1.0), base=(0.73, 0.55, 0.35)):
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    n = np.nan_to_num(n, nan=0.0, posinf=0.0, neginf=0.0)  # degenerate slivers
    lv = np.array(light) / np.linalg.norm(light)
    k = 0.35 + 0.65 * np.clip(np.abs((n * lv).sum(axis=1)), 0, 1)  # not @: spurious BLAS warnings on macOS
    return np.clip(np.outer(k, base), 0, 1)


def render(back_m, leg_m, L, out: Path, cover_m=None) -> None:
    # 1. From behind, with the boards and the panel outline (mirrored: as seen from the back).
    fig, ax = plt.subplots(figsize=(7, 8.6))
    tris = _tris(back_m)
    top = tris[:, :, 2].max(axis=1)
    order = np.argsort(top)
    polys = [[(-x, y) for x, y, _ in t] for t in tris[order]]
    from matplotlib.collections import PolyCollection
    h = top[order] / top.max()
    shade = np.clip(np.outer(0.45 + 0.55 * h, (0.73, 0.55, 0.35)) * _shade(tris[order], light=(0.3, 0.4, 1.0)) / 0.73 * 1.25, 0, 1)
    ax.add_collection(PolyCollection(polys, facecolors=shade, edgecolors="none"))
    mx = lambda x: -x  # noqa: E731
    px0, py0 = L["px0"], L["py0"]
    ax.add_patch(Rectangle((mx(px0 + B.PANEL_W), py0), B.PANEL_W, B.PANEL_H, fill=False, ls="--", lw=1, ec="#555"))
    ax.text(mx(px0 + B.PANEL_W / 2), py0 + B.PANEL_H - 8, "panel (behind)", ha="center", fontsize=8, color="#444")
    for (cx, cy, (w, h), label, col) in (
            (L["hat_cx"], L["hat_cy"], B.HAT, "driver HAT", "#2a5db0"),
            (L["zero_cx"], L["zero_cy"], B.ZERO, "Pi Zero", "#2e8b57"),
            (L["ad_cx"], L["ad_cy"], B.ADAPTER, "adapter", "#c0392b")):
        ax.add_patch(Rectangle((mx(cx + w / 2), cy - h / 2), w, h, alpha=0.35, color=col))
        ax.text(mx(cx), cy, label, ha="center", va="center", rotation=90, fontsize=8, color="k")
    cx0, cy0, cx1, cy1 = L["cover_out"]
    ax.add_patch(Rectangle((mx(cx1), cy0), cx1 - cx0, cy1 - cy0, fill=False, lw=1.5, ec="k", ls=":"))
    ax.text(mx(cx0) - 2, cy1 + 2, "cover slides down onto the rails", ha="right", fontsize=8)
    ox0, oy0, ox1, oy1 = L["outer"]
    ax.set_xlim(mx(ox1) - 8, mx(ox0) + 8)
    ax.set_ylim(oy0 - 8, oy1 + 8)
    ax.set_aspect("equal")
    ax.set_title("Back, seen from behind (boards drawn in)", fontsize=10)
    ax.set_xlabel("mm")
    fig.tight_layout()
    fig.savefig(out / "preview_back.png", dpi=130)
    plt.close(fig)

    # 2. Side view standing on the table (cross-section through the stand).
    t, a = math.radians(B.LEAN), math.radians(B.LEG_ANGLE)
    S = B.socket_geometry(L)
    _, length = B.leg()
    def world(y, z):  # plate (y from table-level bottom, z out of the back) -> (h back, v up)
        y = y - oy0 + B.FRAME_BELOW
        return (y * math.sin(t) + z * math.cos(t), y * math.cos(t) - z * math.sin(t))
    fig, ax = plt.subplots(figsize=(6, 6))
    ytop = oy1 + 15
    frame = [world(oy0 - B.FRAME_BELOW, -20), world(ytop, -20), world(ytop, 0), world(oy0 - B.FRAME_BELOW, 0)]
    ax.fill(*zip(*frame), color=WOOD, alpha=0.6, label="wooden frame")
    plate = [world(oy0, B.PLUG_T), world(oy1, B.PLUG_T), world(oy1, B.PLUG_T + B.PLATE_T), world(oy0, B.PLUG_T + B.PLATE_T)]
    ax.fill(*zip(*plate), color="#7a5a3a", label="printed back")
    st, mo, d = S["start"], S["mouth"], S["d"]
    foot = (mo[0] + d[0] * (length - B.LEG_SOCKET_DEPTH), mo[1] + d[1] * (length - B.LEG_SOCKET_DEPTH))
    ax.plot(*zip(world(*st), world(*foot)), lw=6, color="#5b3d22", solid_capstyle="butt", label="leg")
    blk = [world(S["blk_y0"], B.PLUG_T + B.PLATE_T), world(S["blk_y1"], B.PLUG_T + B.PLATE_T),
           world(S["blk_y1"], B.PLUG_T + B.PLATE_T + S["blk_d"]), world(S["blk_y0"], B.PLUG_T + B.PLATE_T + S["blk_d"])]
    ax.fill(*zip(*blk), color="#7a5a3a")
    com = world((oy0 + oy1) / 2, 0)
    ax.plot([com[0]], [com[1]], "kx")
    ax.annotate("centre of weight", com, (com[0] + 15, com[1]), fontsize=8, va="center")
    ax.axhline(0, color="k", lw=1)
    fh = world(*foot)[0]
    ax.set_title(f"Standing: leans {B.LEAN:.0f}°, foot {fh:.0f} mm behind the front edge, "
                 f"weight {com[0]:.0f} mm behind", fontsize=9)
    ax.set_aspect("equal")
    ax.legend(fontsize=8, loc="upper right")
    fig.tight_layout()
    fig.savefig(out / "preview_side.png", dpi=130)
    plt.close(fig)

    # 3. 3D view of the back, the leg, and the cover lifted off above its rails.
    fig = plt.figure(figsize=(8, 7))
    ax = fig.add_subplot(projection="3d")
    parts = [(back_m, (0, 0, 0), (0.73, 0.55, 0.35)), (leg_m, (L["outer"][2] + 25, 0, 0), (0.6, 0.42, 0.25))]
    if cover_m is not None:
        parts.append((cover_m, (0, 95, 0), (0.80, 0.62, 0.40)))
    for m, off, base in parts:
        tr = _tris(m) * np.array([-1, 1, 1]) + np.array([-off[0], off[1], off[2]])
        ax.add_collection3d(Poly3DCollection(tr, facecolors=_shade(tr, base=base), edgecolors="none"))
    ax.set_xlim(-L["outer"][2] - 140, -L["outer"][0] + 5)
    ax.set_ylim(L["outer"][1] - 5, L["outer"][3] + 40)
    ax.set_zlim(-60, 140)
    ax.set_box_aspect((1.6, 1.2, 0.95))
    ax.view_init(elev=32, azim=-115)
    ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(out / "preview_3d.png", dpi=130)
    plt.close(fig)
    # 4. Section across the cover and its rails, at the middle of the boards.
    if cover_m is not None:
        fig, ax = plt.subplots(figsize=(8, 3.2))
        y = L["ad_cy"] + 2
        for m, col in ((back_m, "#7a5a3a"), (cover_m, "#d9a066")):
            cs = m.translate([0, -y, 0]).rotate([-90, 0, 0]).slice(0.0)
            for poly in cs.to_polygons():
                poly = np.asarray(poly)
                ax.fill(-poly[:, 0], poly[:, 1], color=col, ec="k", lw=0.4)
        cx0, _, cx1, _ = L["cover_out"]
        ax.set_xlim(-cx1 - 12, -cx0 + 12)
        ax.set_ylim(-1, B.PLUG_T + B.PLATE_T + B.COVER_DEPTH + 4)
        ax.set_aspect("equal")
        ax.set_title("Across the cover (seen from below): the angled edges sit under the rails", fontsize=9)
        fig.tight_layout()
        fig.savefig(out / "preview_cover_section.png", dpi=130)
        plt.close(fig)
    print(f"previews -> {out}/preview_*.png")
