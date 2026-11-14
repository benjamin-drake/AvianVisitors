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
ADAPTER = (21.0, 53.0)              # x, y (long side vertical); 51 measured, +2 so it drops in (test print)
ADAPTER_HOLES = (17.5, 45.0)
ADAPTER_FROM_EDGE = 17.0            # its board edge, mm in from the panel's ribbon edge
ADAPTER_SLOT = 3.0                  # holes are slots, +-3 mm in x, to fine-tune on assembly
RIBBON_ROOM = 3.5                   # depth behind the panel for the ribbon's U-turn (was 2.0: too sharp)
ADAPTER_PCB_Z = RIBBON_ROOM + 0.9   # board's back face sits here; connectors face the panel
M2_CLEAR = 2.4                      # M2 x 6 mm MAX: tab 2 + board 1.6 + nut 1.6; longer pokes at the panel

# --- Boards on the back -------------------------------------------------------------
STANDOFF_D, PILOT = 6.0, 2.2        # pilot for M2.5 self-tapping screws (or heat-set: 3.5)
HAT_POST = 10.0                     # the HAT's 40-pin socket hangs underneath (unused, ~8.5 mm)
ZERO_POST = 8.0                     # room under the Zero for its ports and the power plug
BOARD_GAP = 14.0                    # HAT to Zero: the 9-wire cable runs across here
HAT = (30.5, 65.0)                  # rotated: its ribbon connector faces the adapter window
HAT_HOLES = (23.0, 58.0)
ZERO = (30.0, 65.0)                 # Pi Zero, upright, ports facing away from the HAT
ZERO_HOLES = (23.0, 58.0)
# This Zero's header is soldered on the underside, so it mounts LOGO SIDE UP (pins up for
# the jumper wires, header towards the HAT), SD card at the BOTTOM, ports facing away from
# the HAT. PWR IN is 54 mm from the SD end, i.e. 11 mm from the top of the board.
ZERO_PWR_FROM_TOP = 11.0

# --- Slide-on cover over the boards ------------------------------------------------
COVER_WALL = 2.0
COVER_DEPTH = 38.0                  # outside height above the back. The Zero's Dupont sockets top out
                                    # ~26 mm above the back; 36 mm inside leaves room for the wires to bend
COVER_MARGIN = 5.0                  # room round the boards and the adapter window
PLUG_ROOM = 20.0                    # beside the Zero's ports, for the power plug to turn down
DOVE_F, DOVE_T = 4.0, 2.5           # the cover's 45-degree edge: 4 mm out at the back, 2.5 mm tall
DOVE_CLEAR = 0.3
RAIL_W = 3.0
END_WALL = 2.4                      # fixed wall on the back that closes the cover's open bottom

# --- Stand --------------------------------------------------------------------------
LEANS = (10.0, 15.0, 20.0)          # the three lean settings, degrees back from vertical
LEAN = 15.0                         # the one drawn in the side preview
LEG_ANGLE = 45.0                    # leg's angle from the back's surface
LEG_W, LEG_T = 40.0, 6.0
LEG_SOCKET_DEPTH = 38.0             # slot length; the leg goes in 20-37 mm depending on the setting
PIN_FROM_MOUTH = 10.0               # the pin crosses the slot this far in from its mouth
PIN_CLEAR, PIN_PILOT = 3.3, 2.6     # M3 x 30 screw: clear through the roof and the leg, bites below
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


def standoffs(cx, cy, sx, sy, z, h) -> tuple[Manifold, Manifold]:
    """Four posts on a sx x sy hole pattern centred at (cx, cy); returns (posts, pilot holes)."""
    posts, holes = Manifold(), Manifold()
    for dx in (-sx / 2, sx / 2):
        for dy in (-sy / 2, sy / 2):
            posts += cyl(cx + dx, cy + dy, z, h, STANDOFF_D / 2)
            holes += cyl(cx + dx, cy + dy, z - 1, h + 2, PILOT / 2)
    return posts, holes


def along_y(points, y0, y1) -> Manifold:
    """Extrude a profile drawn in (x, z) along y, from y0 to y1."""
    from manifold3d import CrossSection
    area = sum(x0 * z1 - x1 * z0 for (x0, z0), (x1, z1) in zip(points, points[1:] + points[:1]))
    if area < 0:                                               # clockwise reads as a hole
        points = points[::-1]
    prof = Manifold.extrude(CrossSection([points]), y1 - y0)   # profile in XY, length along +Z
    return prof.rotate([90, 0, 0]).translate([0, y1, 0])       # (X, Y, Z) -> (X, -Z, Y), then shift


def dovetail_profiles(L, zt):
    """(x, z) profiles of the cover's two angled edges and the back's two rails."""
    cx0, _, cx1, _ = L["cover_out"]
    F, T, c, R = DOVE_F, DOVE_T, DOVE_CLEAR, RAIL_W
    # 45-degree all the way to the wall (no flat ledge), so it prints upside down unsupported.
    edge_l = [(cx0 + 0.5, zt), (cx0 - F, zt), (cx0 - F + T, zt + T), (cx0, zt + F), (cx0 + 0.5, zt + F)]
    rail_l = [(cx0 - F - c - R, zt - 0.01), (cx0 - F - c, zt - 0.01), (cx0 - F + T - c, zt + T),
              (cx0 - F - c - R, zt + T)]
    mirror = lambda pts, about: [(2 * about - x, z) for x, z in reversed(pts)]  # noqa: E731
    mid = (cx0 + cx1) / 2
    return edge_l, mirror(edge_l, mid), rail_l, mirror(rail_l, mid)


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
    # All three boards in one row, so one cover goes over them: adapter, HAT, Zero.
    zero_cx = hat_cx + inward * (HAT[0] / 2 + BOARD_GAP + ZERO[0] / 2)
    zero_cy = ad_cy
    win_half = (ADAPTER[0] + 2 * ADAPTER_SLOT + 1.0) / 2
    xa = ad_cx - inward * (win_half + COVER_MARGIN)                  # inside of the cover, ribbon side
    xb = zero_cx + inward * (ZERO[0] / 2 + PLUG_ROOM)                # inside, beyond the Zero's ports
    half_h = max(ADAPTER[1] + 1.0, HAT[1], ZERO[1]) / 2
    cover_in = (min(xa, xb), ad_cy - half_h - COVER_MARGIN, max(xa, xb), ad_cy + half_h + COVER_MARGIN)
    w = COVER_WALL
    cover_out = (cover_in[0] - w, cover_in[1] - w, cover_in[2] + w, cover_in[3] + w)
    cable_x = zero_cx + inward * (ZERO[0] / 2 + PLUG_ROOM / 2)       # power cable leaves the cover here
    return dict(px0=px0, py0=py0, top=top, edge_x=edge_x, inward=inward,
                ad_cx=ad_cx, ad_cy=ad_cy, hat_cx=hat_cx, hat_cy=hat_cy,
                zero_cx=zero_cx, zero_cy=zero_cy, outer=(ox0, oy0, ox1, oy1),
                socket=((ox0 + ox1) / 2, oy0 + SOCKET_Y),
                cover_in=cover_in, cover_out=cover_out, cable_x=cable_x)


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
    body -= box(rx0, r_y0, -1, rx1, r_y1, RIBBON_ROOM)   # room behind the panel for the ribbon

    # Adapter window, with tabs at its four holes (slotted for fine adjustment).
    ax, ay = L["ad_cx"], L["ad_cy"]
    aw, ah = ADAPTER[0] + 2 * ADAPTER_SLOT + 1.0, ADAPTER[1] + 1.0
    body -= box(ax - aw / 2, ay - ah / 2, -1, ax + aw / 2, ay + ah / 2, zt + 1)
    tab_z0 = ADAPTER_PCB_Z + 1.6
    tab_z1 = max(zt, tab_z0 + 2.0)   # tabs 2 mm thick; they stand proud of the back if need be
    hx, hy = ADAPTER_HOLES[0] / 2, ADAPTER_HOLES[1] / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = ax + sx * hx, ay + sy * hy
            tab = box(cx - 4.5 - ADAPTER_SLOT, cy - 4.0, tab_z0, cx + 4.5 + ADAPTER_SLOT, cy + 4.0, tab_z1)
            tab -= box(cx - ADAPTER_SLOT, cy - M2_CLEAR / 2, tab_z0 - 1, cx + ADAPTER_SLOT, cy + M2_CLEAR / 2, tab_z1 + 1)
            for ex_ in (-ADAPTER_SLOT, ADAPTER_SLOT):
                tab -= cyl(cx + ex_, cy, tab_z0 - 1, tab_z1 - tab_z0 + 2, M2_CLEAR / 2)
            # keep the tab inside the window's outline (it's the window's own ledge)
            tab ^= box(ax - aw / 2, ay - ah / 2, tab_z0, ax + aw / 2, ay + ah / 2, tab_z1)
            body += tab
    # The white ribbon leaves the window between the adapter's edge and the window's side.

    # HAT and Pi Zero standoffs on the outer face.
    for (cx, cy, (hxs, hys), h) in ((L["hat_cx"], L["hat_cy"], HAT_HOLES, HAT_POST),
                                    (L["zero_cx"], L["zero_cy"], ZERO_HOLES, ZERO_POST)):
        posts, holes = standoffs(cx, cy, hxs, hys, zt - 0.01, h)
        body = body + posts - holes

    # Power: the cable leaves the cover through a notch in its bottom wall, then presses
    # into a channel down to the plate's bottom edge.
    ch_x, ch_top = L["cable_x"], L["cover_out"][1] - 3
    gap = 4.6                                     # micro-USB cables are ~3-3.5 mm: press in
    for sgn in (-1, 1):
        wx = ch_x + sgn * (gap / 2 + 1)
        body += box(wx - 1, oy0, zt - 0.01, wx + 1, ch_top, zt + 5.5)
        lip_x = ch_x + sgn * gap / 2
        body += box(min(lip_x, lip_x - sgn * 0.8), oy0, zt + 4.5, max(lip_x, lip_x - sgn * 0.8), ch_top, zt + 5.5)

    # Rails for the slide-on cover: it drops in from above and rests on the end wall; its own
    # weight keeps it there (no catch: anything on the rails would drag along the whole slide).
    _, _, rail_l, rail_r = dovetail_profiles(L, zt)
    cx0, cy0, cx1, cy1 = L["cover_out"]
    for rail, sgn, cx in ((rail_l, -1, cx0), (rail_r, 1, cx1)):
        body += along_y(rail, cy0 - 2.3, cy1)
        outer = cx + sgn * (DOVE_F + DOVE_CLEAR + RAIL_W)
        body += box(min(cx - sgn * 2, outer), cy0 - 2.3, zt - 0.01, max(cx - sgn * 2, outer), cy0 - 0.3, zt + DOVE_T)

    # Fixed end wall: the cover's open bottom closes against it. The power cable leaves
    # through a notch in it.
    end = box(cx0, cy0 - END_WALL - 0.3, zt - 0.01, cx1, cy0 - 0.3, zt + COVER_DEPTH)
    end -= box(L["cable_x"] - 3.0, cy0 - END_WALL - 1, zt - 1, L["cable_x"] + 3.0, cy0 + 1, zt + 7)
    body += end

    # Stand socket: a block with a slot angled LEG_ANGLE from the surface, opening downwards.
    sx, sy = L["socket"]
    S = socket_geometry(L)
    blk_w = LEG_W + 2 * LEG_CLEAR + 8
    block = box(sx - blk_w / 2, S["blk_y0"], zt - 0.01, sx + blk_w / 2, S["blk_y1"], zt + S["blk_d"])
    slot = box(-(LEG_W / 2 + LEG_CLEAR), -(LEG_T / 2 + LEG_CLEAR), 0,
               LEG_W / 2 + LEG_CLEAR, LEG_T / 2 + LEG_CLEAR, 120)
    slot = slot.rotate([90 - LEG_ANGLE, 0, 0]).translate([sx, S["start"][0], S["start"][1]])
    # Pin across the slot, square to the leg: M3 screw in from the block's outside.
    n = (math.sin(math.radians(LEG_ANGLE)), math.cos(math.radians(LEG_ANGLE)))   # (y, z), up and out
    P = S["pin"]
    def along_n(r, t0, t1):  # cylinder on the pin's axis, from t0 to t1 mm along n
        c = Manifold.cylinder(t1 - t0, r, r, SEG)       # along +z
        c = c.translate([0, 0, t0]).rotate([-LEG_ANGLE, 0, 0])   # +z -> n
        return c.translate([sx, P[0], P[1]])
    pin = along_n(PIN_CLEAR / 2, -(LEG_T / 2 + LEG_CLEAR) + 0.01, 60) + along_n(PIN_PILOT / 2, -12, 1)
    body += block - slot - pin

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
    pin = (mouth[0] - PIN_FROM_MOUTH * d[0], mouth[1] - PIN_FROM_MOUTH * d[1])
    blk_d = mouth[1] - zt                                         # the slot opens through the block's back face
    blk_y1 = start[0] + half * math.sin(a) + 4                    # 4 mm of roof above the blind end
    blk_y0 = mouth[0] - half * math.sin(a) - 1
    return dict(start=start, mouth=mouth, pin=pin, blk_d=blk_d, blk_y0=blk_y0, blk_y1=blk_y1, d=d)


def screw_points(L) -> list[tuple[float, float]]:
    ox0, oy0, ox1, oy1 = L["outer"]
    m = FLANGE / 2
    xs, ys = (ox0 + m, (ox0 + ox1) / 2, ox1 - m), (oy0 + m, (oy0 + oy1) / 2, oy1 - m)
    return [(x, y) for x in xs for y in ys if not (x == xs[1] and y == ys[1])]


def reach(lean: float) -> float:
    """Distance from the socket's mouth to the tip of the (rounded) foot, along the leg,
    for the frame to lean back `lean` degrees."""
    L = layout()
    t, a = math.radians(lean), math.radians(LEG_ANGLE)
    S = socket_geometry(L)
    y = S["mouth"][0] - L["outer"][1] + FRAME_BELOW      # mouth, along the back from the table
    z = S["mouth"][1]
    v = y * math.cos(t) - z * math.sin(t)                # mouth's height above the table
    r = LEG_T / 2                                        # the foot is a half-round: works at any lean
    return (v - r) / math.cos(a - t) + r


def leg_settings() -> tuple[float, list[tuple[float, float, float]]]:
    """(leg length, [(lean, how far it goes in, hole's distance from the leg's top end)])."""
    reaches = [reach(t) for t in LEANS]
    length = min(reaches) + LEG_SOCKET_DEPTH - 1.0       # deepest setting stops 1 mm short of the end
    rows = [(t, length - r, length - r - PIN_FROM_MOUTH) for t, r in zip(LEANS, reaches)]
    return length, rows


def leg() -> tuple[Manifold, float]:
    """The stand's leg, printed flat: a half-round foot and one hole per lean setting."""
    length, rows = leg_settings()
    w, th = LEG_W, LEG_T
    r = th / 2
    arc = [(length - r + r * math.sin(u), r - r * math.cos(u))
           for u in np.linspace(0, math.pi, 13)]
    pts = [(0, 0)] + arc + [(0, th)]
    from manifold3d import CrossSection
    body = Manifold.extrude(CrossSection([pts]), w)       # x: length, y: thickness, z: width
    for _, _, hole in rows:
        body -= Manifold.cylinder(th + 2, PIN_CLEAR / 2, PIN_CLEAR / 2, SEG).rotate([-90, 0, 0]).translate([hole, -1, w / 2])
    body = body.rotate([90, 0, 0])                        # lay it flat: thickness up
    return body, length


def cover() -> Manifold:
    """The slide-on cover, in place over the boards (model coordinates)."""
    L = layout()
    zt = PLUG_T + PLATE_T
    w = COVER_WALL
    x0, y0, x1, y1 = L["cover_out"]
    shell = rounded_box(x0, y0, zt, x1, y1, zt + COVER_DEPTH, 2.0)
    # Open at the bottom: that end leads as it slides down over the boards, and it closes
    # against a fixed wall on the back.
    shell -= box(x0 + w, y0 - 1, zt - 1, x1 - w, y1 - w, zt + COVER_DEPTH - w)
    edge_l, edge_r, _, _ = dovetail_profiles(L, zt)
    shell += along_y(edge_l, y0, y1) + along_y(edge_r, y0, y1)
    # Vents: a row of slots near the top and the bottom of the face (warm air rises).
    span = x1 - x0 - 24
    n = max(3, int(span // 18))
    for row_y in (y0 + 8, y1 - 10):
        for i in range(n):
            sx = x0 + 12 + span * (i + 0.5) / n
            shell -= box(sx - 6, row_y, zt + COVER_DEPTH - w - 1, sx + 6, row_y + 2, zt + COVER_DEPTH + 1)
    # Thumb grip near the top: three shallow grooves cut into the face (a raised ridge
    # would need supports, as the face prints on the bed).
    for gy in (y1 - 22, y1 - 19, y1 - 16):
        shell -= box(x0 + 20, gy, zt + COVER_DEPTH - 0.8, x1 - 20, gy + 1.5, zt + COVER_DEPTH + 1)
    return shell


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
    cv = cover()
    # Printed upside down: its face on the bed, angled edges at the top (45 degrees, no supports).
    flipped = cv.mirror([1, 0, 0]).rotate([180, 0, 0])
    write_stl(flipped.translate([0, 0, -flipped.bounding_box()[2]]), args.out / "frame_cover.stl")
    ox0, oy0, ox1, oy1 = L["outer"]
    bb = b.bounding_box()
    print(f"back: {ox1 - ox0:.1f} x {oy1 - oy0:.1f} mm outside, {bb[5] - bb[2]:.1f} mm deep at the stand socket")
    print(f"rebate to cut in the wooden frame: {REBATE_W:.1f} x {REBATE_H:.1f} mm (panel + {FIT} mm each side + {BEND} mm for the ribbon)")
    print(f"leg: {length:.0f} x {LEG_W:.0f} x {LEG_T:.0f} mm; volume back {b.volume() / 1000:.0f} cm3, leg {lg.volume() / 1000:.0f} cm3")
    for lean, ins, hole in leg_settings()[1]:
        print(f"  lean {lean:.0f} deg: leg {ins:.1f} mm into the socket, pin through the hole {hole:.1f} mm from its top")
    cx0, cy0, cx1, cy1 = L["cover_out"]
    print(f"cover: {cx1 - cx0:.0f} x {cy1 - cy0:.0f} x {COVER_DEPTH:.0f} mm, {cv.volume() / 1000:.0f} cm3; "
          f"overlaps back: {(b ^ cv).volume():.2f} mm3 (should be 0)")
    print(f"-> {args.out}")
    if args.preview:
        from preview_back import render  # noqa: E402  (enclosure/preview_back.py)
        render(b, lg, L, args.out, cv)


if __name__ == "__main__":
    main()
