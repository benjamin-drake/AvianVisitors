#!/usr/bin/env python3
"""The frame's 3D-printed back: holds the panel in the wooden frame, carries the
boards, and takes a slot-in stand. Writes STLs to out/enclosure/.

    python enclosure/back.py              # needs: pip install manifold3d numpy (matplotlib for --preview)
    python enclosure/back.py --preview    # also out/enclosure/preview_*.png

Coordinates are as seen from the FRONT of the frame, hung portrait: x to the
right, y up, mm. z = 0 is the face that presses on the back of the panel (it
prints face down on the bed), z grows towards the wall.

What sits in the wooden frame's rebate, front to back:
    glass (optional), your mount/mat, the panel (0.74 mm), then this back's "plug",
    which presses the stack forward. The flange round the plug sits on the back
    of the wooden frame and is held by small wood screws, so it lifts off.

The panel's ribbon (FPC) comes out of its LEFT long edge (front view), about
70-142 mm down from the top. It bends back behind the panel and plugs into the
small adapter board, which is screwed into a window in the back with its
connectors facing the panel. The adapter's white ribbon goes out through the
window to the driver board (HAT) on the back. The Pi Zero sits beside it, wired
with the 9-wire cable. Check the ribbon side on yours: if it's on the right,
set FPC_ON_LEFT = False.

Sources: Waveshare 9.7inch e-Paper (E) outline drawing (panel 210.80 x 154.90,
active area 201.60 x 141.12, FPC tail 30.50 wide at 70.37 mm, 28.69 mm long;
HAT 65.00 x 30.50, holes 3.0 mm at 3.5/3.5/4.0 from the edges). Pi Zero:
65 x 30, M2.5 holes 58 x 23. Adapter board measured: 51 x 21, holes 45 x 17.5.
"""
from __future__ import annotations

import argparse
import math
import struct
from pathlib import Path

import numpy as np
from manifold3d import Manifold

# --- Panel and the wooden frame's rebate --------------------------------------------
PANEL_W, PANEL_H = 154.90, 210.80   # portrait as hung (the drawing is landscape)
FIT = 1.0                           # clearance round the panel in the rebate, each side
BEND = 4.0                          # extra room on the ribbon side for the ribbon's bend
FPC_ON_LEFT = True
FPC_ROOT = (68.0, 145.0)            # where the ribbon leaves the panel, mm down from its top
FPC_TAIL_CENTRE = 70.37 + 30.50 / 2  # centre of the narrow tail, mm down from the top

REBATE_W = PANEL_W + 2 * FIT + BEND  # the opening to cut in the wooden frame's rebate
REBATE_H = PANEL_H + 2 * FIT
PLUG_CLEAR = 0.4                    # plug smaller than the rebate by this, each side
PLUG_T = 2.5                        # how far the plug reaches into the rebate
FLANGE = 14.0                       # flange overlap onto the wooden frame, each side
PLATE_T = 4.0                       # flange/plate thickness
CORNER_R = 4.0

# --- Adapter board (panel ribbon -> white ribbon) -----------------------------------------
ADAPTER = (21.0, 51.0)              # x, y (long side vertical, along the panel edge)
ADAPTER_HOLES = (17.5, 45.0)
ADAPTER_FROM_EDGE = 17.0            # its board edge, mm in from the panel's ribbon edge
ADAPTER_SLOT = 3.0                  # holes are slots, +-3 mm in x, to fine-tune on assembly
ADAPTER_PCB_Z = 2.9                 # board's back face sits here; connectors face the panel
M2_CLEAR = 2.4                      # M2 x 6 mm MAX: tab 2 + board 1.6 + nut 1.6; longer pokes at the panel

# --- Boards on the back -------------------------------------------------------------
STANDOFF_H, STANDOFF_D, PILOT = 6.0, 6.0, 2.2   # pilot for M2.5 self-tapping screws (or heat-set: 3.5)
HAT = (30.5, 65.0)                  # rotated: its ribbon connector faces the adapter window
HAT_HOLES = (23.0, 58.0)
ZERO = (30.0, 65.0)                 # Pi Zero, upright, ports facing the frame's edge
ZERO_HOLES = (23.0, 58.0)
# This Zero's header is soldered on the underside, so it mounts LOGO SIDE UP (pins up for
# the jumper wires), SD card at the BOTTOM, ports facing the edge. PWR IN is 54 mm from
# the SD end, i.e. 11 mm from the top of the board.
ZERO_PWR_FROM_TOP = 11.0

# --- Stand --------------------------------------------------------------------------
LEAN = 15.0                         # frame leans back this far from vertical
LEG_ANGLE = 45.0                    # leg's angle from the back's surface
LEG_W, LEG_T = 40.0, 6.0
LEG_SOCKET_DEPTH = 22.0
LEG_CLEAR = 0.35
SOCKET_Y = 70.0                     # socket centre, mm above the plate's bottom edge
FRAME_BELOW = 15.0                  # wooden frame's bottom edge (on the table) below the plate's bottom edge

SCREW_HOLE, SCREW_HEAD = 3.6, 7.5   # countersunk No.4 / 3.5 mm wood screws into the frame

SEG = 48


def box(x0, y0, z0, x1, y1, z1) -> Manifold:
    return Manifold.cube([x1 - x0, y1 - y0, z1 - z0]).translate([x0, y0, z0])


def rounded_box(x0, y0, z0, x1, y1, z1, r) -> Manifold:
    w, h = x1 - x0, y1 - y0
    core = box(x0 + r, y0, z0, x1 - r, y1, z1) + box(x0, y0 + r, z0, x1, y1 - r, z1)
    for cx in (x0 + r, x1 - r):
        for cy in (y0 + r, y1 - r):
            core += cyl(cx, cy, z0, z1 - z0, r)
    return core


def cyl(x, y, z, h, r, r2=None) -> Manifold:
    return Manifold.cylinder(h, r, r if r2 is None else r2, SEG).translate([x, y, z])


def standoffs(cx, cy, sx, sy, z) -> tuple[Manifold, Manifold]:
    """Four posts on a sx x sy hole pattern centred at (cx, cy); returns (posts, pilot holes)."""
    posts, holes = Manifold(), Manifold()
    for dx in (-sx / 2, sx / 2):
        for dy in (-sy / 2, sy / 2):
            posts += cyl(cx + dx, cy + dy, z, STANDOFF_H, STANDOFF_D / 2)
            holes += cyl(cx + dx, cy + dy, z - 1, STANDOFF_H + 2, PILOT / 2)
    return posts, holes


def layout() -> dict:
    """Where everything goes (front view), shared by the model and the previews."""
    px0 = FIT + (BEND if FPC_ON_LEFT else 0)
    py0 = FIT
    top = py0 + PANEL_H
    edge_x = px0 if FPC_ON_LEFT else px0 + PANEL_W
    inward = 1 if FPC_ON_LEFT else -1
    ad_cy = top - FPC_TAIL_CENTRE
    ad_x0 = edge_x + inward * ADAPTER_FROM_EDGE
    ad_cx = ad_x0 + inward * ADAPTER[0] / 2
    hat_cx = ad_cx + inward * (ADAPTER[0] / 2 + ADAPTER_SLOT + 12 + HAT[0] / 2)
    hat_cy = ad_cy
    ox0, oy0 = -FLANGE, -FLANGE
    ox1, oy1 = REBATE_W + FLANGE, REBATE_H + FLANGE
    zero_cx = (ox1 - 26 - ZERO[0] / 2) if FPC_ON_LEFT else (ox0 + 26 + ZERO[0] / 2)
    zero_cy = oy0 + 28 + ZERO[1] / 2
    return dict(px0=px0, py0=py0, top=top, edge_x=edge_x, inward=inward,
                ad_cx=ad_cx, ad_cy=ad_cy, hat_cx=hat_cx, hat_cy=hat_cy,
                zero_cx=zero_cx, zero_cy=zero_cy, outer=(ox0, oy0, ox1, oy1),
                socket=((ox0 + ox1) / 2, oy0 + SOCKET_Y))


def back() -> Manifold:
    L = layout()
    ox0, oy0, ox1, oy1 = L["outer"]
    zb = PLUG_T                      # back face of the plug = front face of the flange
    zt = PLUG_T + PLATE_T            # outer (wall-side) face
    plug = rounded_box(PLUG_CLEAR, PLUG_CLEAR, 0, REBATE_W - PLUG_CLEAR, REBATE_H - PLUG_CLEAR, zb + 0.01, 1.5)
    plate = rounded_box(ox0, oy0, zb, ox1, oy1, zt, CORNER_R)
    body = plug + plate

    # Room for the ribbon's bend and its run behind the panel to the adapter.
    ex, inward = L["edge_x"], L["inward"]
    rx0, rx1 = sorted((ex - inward * (BEND + FIT + 1), L["ad_cx"]))
    r_y0, r_y1 = L["top"] - FPC_ROOT[1] - 3, L["top"] - FPC_ROOT[0] + 3
    body -= box(rx0, r_y0, -1, rx1, r_y1, 2.0)   # 2 mm of room behind the panel for the ribbon

    # Adapter window, with tabs at its four holes (slotted for fine adjustment).
    ax, ay = L["ad_cx"], L["ad_cy"]
    aw, ah = ADAPTER[0] + 2 * ADAPTER_SLOT + 1.0, ADAPTER[1] + 1.0
    body -= box(ax - aw / 2, ay - ah / 2, -1, ax + aw / 2, ay + ah / 2, zt + 1)
    tab_z0 = ADAPTER_PCB_Z + 1.6
    hx, hy = ADAPTER_HOLES[0] / 2, ADAPTER_HOLES[1] / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = ax + sx * hx, ay + sy * hy
            tab = box(cx - 4.5 - ADAPTER_SLOT, cy - 4.0, tab_z0, cx + 4.5 + ADAPTER_SLOT, cy + 4.0, zt)
            tab -= box(cx - ADAPTER_SLOT, cy - M2_CLEAR / 2, tab_z0 - 1, cx + ADAPTER_SLOT, cy + M2_CLEAR / 2, zt + 1)
            for ex_ in (-ADAPTER_SLOT, ADAPTER_SLOT):
                tab -= cyl(cx + ex_, cy, tab_z0 - 1, zt - tab_z0 + 2, M2_CLEAR / 2)
            # keep the tab inside the window's outline (it's the window's own ledge)
            tab ^= box(ax - aw / 2, ay - ah / 2, tab_z0, ax + aw / 2, ay + ah / 2, zt)
            body += tab
    # The white ribbon leaves the window between the adapter's edge and the window's side.

    # HAT and Pi Zero standoffs on the outer face.
    for (cx, cy, (hxs, hys)) in ((L["hat_cx"], L["hat_cy"], HAT_HOLES), (L["zero_cx"], L["zero_cy"], ZERO_HOLES)):
        posts, holes = standoffs(cx, cy, hxs, hys, zt - 0.01)
        body = body + posts - holes

    # Power: the cable from PWR IN runs down a channel to a notch in the bottom edge.
    pwr_y = L["zero_cy"] + ZERO[1] / 2 - ZERO_PWR_FROM_TOP
    side = 1 if FPC_ON_LEFT else -1
    port_x = L["zero_cx"] + side * (ZERO[0] / 2 + 3)
    ch_x = port_x + side * 9
    gap = 4.6                                     # micro-USB cables are ~3-3.5 mm: press in
    for sgn in (-1, 1):
        wx = ch_x + sgn * (gap / 2 + 1)
        body += box(wx - 1, oy0, zt - 0.01, wx + 1, pwr_y + 2, zt + 5.5)
        lip_x = ch_x + sgn * gap / 2
        body += box(min(lip_x, lip_x - sgn * 0.8), oy0, zt + 4.5, max(lip_x, lip_x - sgn * 0.8), pwr_y + 2, zt + 5.5)

    # Stand socket: a block with a slot angled LEG_ANGLE from the surface, opening downwards.
    sx, sy = L["socket"]
    S = socket_geometry(L)
    blk_w = LEG_W + 2 * LEG_CLEAR + 8
    block = box(sx - blk_w / 2, S["blk_y0"], zt - 0.01, sx + blk_w / 2, S["blk_y1"], zt + S["blk_d"])
    slot = box(-(LEG_W / 2 + LEG_CLEAR), -(LEG_T / 2 + LEG_CLEAR), 0,
               LEG_W / 2 + LEG_CLEAR, LEG_T / 2 + LEG_CLEAR, 120)
    slot = slot.rotate([90 - LEG_ANGLE, 0, 0]).translate([sx, S["start"][0], S["start"][1]])
    body += block - slot

    # Countersunk screw holes in the flange.
    for (x, y) in screw_points(L):
        body -= cyl(x, y, -1, zt + 2, SCREW_HOLE / 2)
        body -= cyl(x, y, zt - (SCREW_HEAD - SCREW_HOLE) / 2 - 0.01, (SCREW_HEAD - SCREW_HOLE) / 2 + 0.02, SCREW_HOLE / 2, SCREW_HEAD / 2)
    return body


def socket_geometry(L) -> dict:
    """The slot's blind end (start), where it leaves the block (mouth), and the block's extent.
    The slot runs along d = (-cos a, sin a) in (y, z): down and out of the back."""
    a = math.radians(LEG_ANGLE)
    zt = PLUG_T + PLATE_T
    d = (-math.cos(a), math.sin(a))
    half = LEG_T / 2 + LEG_CLEAR
    start = (L["socket"][1] + 10, zt + 2 + half * math.cos(a))   # near wall clears the plate by ~2 mm
    mouth = (start[0] + LEG_SOCKET_DEPTH * d[0], start[1] + LEG_SOCKET_DEPTH * d[1])
    blk_d = mouth[1] - zt                                         # the slot opens through the block's back face
    blk_y1 = start[0] + half * math.sin(a) + 4                    # 4 mm of roof above the blind end
    blk_y0 = mouth[0] - half * math.sin(a) - 1
    return dict(start=start, mouth=mouth, blk_d=blk_d, blk_y0=blk_y0, blk_y1=blk_y1, d=d)


def screw_points(L) -> list[tuple[float, float]]:
    ox0, oy0, ox1, oy1 = L["outer"]
    m = FLANGE / 2
    xs, ys = (ox0 + m, (ox0 + ox1) / 2, ox1 - m), (oy0 + m, (oy0 + oy1) / 2, oy1 - m)
    return [(x, y) for x in xs for y in ys if not (x == xs[1] and y == ys[1])]


def leg() -> tuple[Manifold, float]:
    """The stand's leg, printed flat. Its foot is cut level with the table."""
    L = layout()
    t, a = math.radians(LEAN), math.radians(LEG_ANGLE)
    # Height of the socket mouth above the table, then the leg length down to it.
    S = socket_geometry(L)
    y_mouth = S["mouth"][0] - L["outer"][1] + FRAME_BELOW
    z_mouth = S["mouth"][1]
    v = y_mouth * math.cos(t) - z_mouth * math.sin(t)
    reach = v / math.cos(a - t)
    length = reach + LEG_SOCKET_DEPTH
    w, th = LEG_W, LEG_T
    # Profile in (x along leg, y across thickness), foot bevel = angle between leg and table.
    foot = math.radians(90) - (a - t)
    cut = th * math.tan(foot)
    pts = [(0, 0), (length, 0), (length - cut, th), (0, th)] if cut < length else [(0, 0), (length, 0), (0, th)]
    from manifold3d import CrossSection
    prof = CrossSection([pts])
    body = Manifold.extrude(prof, w)                      # x: length, y: thickness, z: width
    body = body.rotate([90, 0, 0])                        # lay it flat: thickness up
    return body, length


def write_stl(m: Manifold, path: Path) -> None:
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties)[:, :3]
    f = np.asarray(mesh.tri_verts)
    tri = v[f]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    with open(path, "wb") as fh:
        fh.write(b"garden frame back".ljust(80, b" "))
        fh.write(struct.pack("<I", len(f)))
        rec = np.zeros(len(f), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
        rec["n"], rec["v"] = n, tri
        fh.write(rec.tobytes())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "out" / "enclosure")
    ap.add_argument("--preview", action="store_true")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    L = layout()
    b = back()
    lg, length = leg()
    # Print orientation: the back as modelled (panel face on the bed); mirror so the
    # slicer shows it the way round you'll see it from behind.
    write_stl(b.mirror([1, 0, 0]), args.out / "frame_back.stl")
    write_stl(lg, args.out / "frame_stand_leg.stl")
    ox0, oy0, ox1, oy1 = L["outer"]
    bb = b.bounding_box()
    print(f"back: {ox1 - ox0:.1f} x {oy1 - oy0:.1f} mm outside, {bb[5] - bb[2]:.1f} mm deep at the stand socket")
    print(f"rebate to cut in the wooden frame: {REBATE_W:.1f} x {REBATE_H:.1f} mm (panel + {FIT} mm each side + {BEND} mm for the ribbon)")
    print(f"leg: {length:.0f} x {LEG_W:.0f} x {LEG_T:.0f} mm; volume back {b.volume() / 1000:.0f} cm3, leg {lg.volume() / 1000:.0f} cm3")
    print(f"-> {args.out}")
    if args.preview:
        from preview_back import render  # noqa: E402  (enclosure/preview_back.py)
        render(b, lg, L, args.out)


if __name__ == "__main__":
    main()
