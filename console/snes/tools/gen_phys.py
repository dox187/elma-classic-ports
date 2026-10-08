"""Writes the data of the physics (src/phys.asm, test/phys_spec.c):

  gen_phys.py ELMA_RES OUT_DIR [--hz HZ]

OUT_DIR/phys_const.h, phys_const.inc  the constants for HZ steps a second
OUT_DIR/phys_tables.h, phys_tables.asm sine, 1/sqrt, 1/x and the rolling
                                       inertia, as integers
OUT_DIR/phys_levels.asm                the lines, the grid and the objects of
                                       each level, and phys_lev_addr
OUT_DIR/phys/levNN.bin                 the same data of each level, for the
                                       tests on the host

Units (see docs/physics.md): positions P = 1/65536 m, velocities V =
1/2^24 m a step, angles and angular velocities 1/2^28 rad (a step), torques
1/16 Nm, unit vectors 32768 = 1 (Q15).
"""

import argparse
import math
import os
import struct
import sys

import elmadata

GAME_RATE = 0.4368             # game time units a second (182 * 0.0024)
P = 65536.0                    # position units a meter
V = 2.0 ** 24                  # velocity units a meter a step
W = 2.0 ** 28                  # angle units a radian
T = 16.0                       # torque units a newton meter
CELL_SH = 17                   # the grid: 2 m cells (1 << 17 P)
LINE_SIZE = 32
OBJ_SIZE = 12
HEADER_SIZE = 96
REACH = 0.41                   # a line is in a cell this near (the wheel's radius and more)

# The bike (ADATOK.CPP initmotor, initadatok):
R_WHEEL, R_HEAD, R_OBJ = 0.4, 0.238, 0.4
M_BODY, M_WHEEL = 200.0, 10.0
TH_BODY, TH_WHEEL = 200.0 * 0.55 * 0.55, 0.32
K_SPRING, S_DAMP = 10000.0, 1000.0
GRAV = 10.0


def factor(f, name):
    """M and SH of f = M / 2^SH, M a signed 16-bit number as large as it can be."""
    if f == 0:
        return 0, 0
    sh = 0
    while abs(f) * 2 ** (sh + 1) < 32767.5 and sh < 40:
        sh += 1
    while abs(f) * 2 ** sh >= 32767.5:
        sh -= 1
    if sh < 0:
        raise ValueError('%s: %r is too large' % (name, f))
    m = int(round(f * 2 ** sh))
    return m, sh


def constants(hz):
    dt = GAME_RATE / hz
    c = []     # (name, value, comment)
    k = []     # (name, factor, comment): multipliers as M/2^SH

    def i(name, v, com=''):
        c.append((name, int(v), com))

    def f(name, v, com=''):
        k.append((name, v, com))

    i('PHYS_HZ', hz, 'steps a second')
    i('G_V', round(GRAV * dt * dt * V), 'gravity in a step (V)')
    i('LOKET_W', round(12.0 * dt * W), 'a volt: Loket 12 rad/s')
    i('OMEGAVALT_W', round(3.0 * dt * W), 'what is left of it: Omegavalt 3 rad/s')
    i('TULP_W', round(110.0 * dt * W), 'no more gas over 110 rad/s (tulporgesomega)')
    i('GAS_T', round(600.0 * T), 'gas: 600 Nm')
    # The keys of the volts: belsoresz takes one Ugroturelem (0.4) after the
    # last one, a volt ends Ugroturelem*0.25 after it started (leptet):
    i('VOLT_GAP', math.floor(0.4 / dt) + 1, 'steps from a volt to the next one')
    i('VOLT_END', math.floor(0.1 / dt) + 1, 'steps of a volt')
    i('ELSZ_V', round(0.01 * dt * V), 'Elszakadasisebhat 0.01 m/s')
    i('BUMP_MIN_V', math.floor(1.5 * dt * V), 'a bump is heard over 1.5 m/s (Utodeshatar)')
    i('V1MS_16', round(dt * 65536), '1 m/s in 1/65536 m a step')
    i('R_WHEEL_P', math.floor(R_WHEEL * P), 'radius of a wheel')
    i('R_WHEEL_SQ', math.ceil(R_WHEEL * R_WHEEL * P * P), 'its square (2^-32 m^2)')
    i('R_HEAD_P', math.floor(R_HEAD * P), 'radius of the head (Fejsugar)')
    i('R_HEAD_SQ', math.ceil(R_HEAD * R_HEAD * P * P), '')
    i('BAND_P', round((R_WHEEL - 0.005) * P), 'a wheel is kept this far from a line (Belsosav 0.005)')
    i('MERGE_P', math.ceil(0.1 * P), 'contact points nearer are one (Talppontegybeolvadasitav)')
    i('MERGE_SQ', math.ceil(0.01 * P * P), '')
    i('OBJ_WHEEL_SQ', math.ceil((R_WHEEL + R_OBJ) ** 2 * 2 ** 30), 'objects: (0.4 + 0.4)^2 in 2^-30 m^2')
    i('OBJ_HEAD_SQ', math.ceil((R_HEAD + R_OBJ) ** 2 * 2 ** 30), '(0.238 + 0.4)^2')
    i('OBJ_WHEEL_P', math.ceil((R_WHEEL + R_OBJ) * P), '')
    i('OBJ_HEAD_P', math.ceil((R_HEAD + R_OBJ) * P), '')
    i('PI_W', round(math.pi * W), 'angles are kept between -pi and pi')
    i('TWOPI_W', round(2 * math.pi * W), '')
    i('HALFPI_W', round(math.pi / 2 * W), '')
    i('SPRING_ZERO_P', math.floor(0.0001 * P), 'no spring force under 0.0001 m (erokszamitasa)')
    # The bike relative to the body, in 2^-15 m:
    i('K85_15', round(0.85 * 32768), 'the wheels from the body: (+-0.85, -0.6) m')
    i('K60_15', round(0.6 * 32768), '')
    i('K44_15', round(0.44 * 32768), 'the rider rests 0.44 m over the body (Kord5y)')
    i('K09_15', round(0.09 * 32768), 'the head from the rider: (-+0.09, 0.63) m')
    i('K63_15', round(0.63 * 32768), '')
    # vezeto_hatarolas, in 2^-15 m, unit vectors Q15:
    avx, avy = 0.14 - (-0.35), 0.36 - 0.13
    nx, ny = -avy, avx
    ln = math.hypot(nx, ny)
    i('SEAT_X', round(-0.35 * 32768), 'the rider stays over the seat: a point of it')
    i('SEAT_Y', round(0.13 * 32768), '')
    i('SEAT_NX', round(nx / ln * 32768), 'and its normal (Q15)')
    i('SEAT_NY', round(ny / ln * 32768), '')
    i('RIDER_TOP', round(0.48 * 32768), 'highest')
    i('RIDER_LEFT', round(-0.5 * 32768), '')
    i('RIDER_RIGHT', round(0.26 * 32768), '')
    i('RIDER_ELL', round(0.48 / 0.26 * 16384), 'the ellipse front up (Q14)')
    i('RIDER_TOP_SQ', round(0.48 * 32768) ** 2, '')
    i('SEAT_C8', round((round(-0.35 * 32768) * round(nx / ln * 32768) +
                        round(0.13 * 32768) * round(ny / ln * 32768)) / 256), 'SEAT * SEAT_N / 256')

    f('K_SPRING', K_SPRING / M_WHEEL * dt * dt * V / P, 'wheel spring: gumi (P) to V')
    f('K_DAMP', S_DAMP / M_WHEEL * dt, 'wheel damping: relv (V) to V')
    f('K_TS', K_SPRING * dt * dt / TH_BODY * W * 2.0 ** -20, 'spring torque on the body: cross >> 10 (2^-20 m^2) to W')
    f('K_TD', S_DAMP * dt / TH_BODY * W * 2.0 ** -21, 'damping torque: cross >> 16 (2^-21 m^2 a step) to W')
    f('K_20', M_WHEEL / M_BODY, 'the body has 20 times the mass of a wheel')
    f('K_FREE', dt * dt / TH_WHEEL * W / T, 'a free wheel: torque (T) to W')
    f('K_FN', M_WHEEL * R_WHEEL ** 2, 'a rolling wheel: force (V) times m R^2')
    f('K_MR', R_WHEEL * dt * dt * V / T, 'and torque (T) times R dt^2')
    f('K_BRK_S', 1000.0 * T * 2.0 ** -20, 'brake: 1000 Nm/rad, deflection (2^-20 rad) to T')
    f('K_BRK_W', 100.0 * T / dt * 2.0 ** -20, 'and 100 Nms/rad, (2^-20 rad a step) to T')
    f('K_RIDER_S', 5 * K_SPRING / M_BODY * dt * dt * V / 32768, 'the rider: spring 5x, (2^-15 m) to V')
    f('K_RIDER_D', 3 * S_DAMP / M_BODY * dt, 'damping 3x, V to V')
    f('K_BUMP', 32.0 / (dt * V), 'bump volume 0..255 of V (ero/0.8*0.1)')
    f('K_REGI', T * M_WHEEL / (dt * dt * V) * 2.0 ** -16 * 2.0 ** 16, 'biztostalppont_regi: hossz*F (P*V >> 16) to T')
    f('K_WVIEW', 65536.0 / (2 * math.pi) * 2.0 ** -13, 'angle (W >> 15) to 65536 a turn')
    f('K_OMEGA', 256.0 / (dt * W) * 2 ** 8, '|omega| (W >> 8) to 1/256 rad/s')
    f('K_FRIC', 2.0 ** -8 / dt, 'friction for the sound: (2^-24 m^2 a step) to 65536 m^2/s')
    return c, k


def write_constants(out, hz):
    c, k = constants(hz)
    h = ['// Generated by tools/gen_phys.py: constants of the physics for %d steps a second.' % hz,
         '#ifndef PHYS_CONST_H', '#define PHYS_CONST_H', '']
    a = ['; Generated by tools/gen_phys.py: constants of the physics for %d steps a second.' % hz, '']
    for name, v, com in c:
        if com:
            h.append('// ' + com + ':')
            a.append('; ' + com + ':')
        h.append('#define %s %d' % (name, v))
        a.append('.DEFINE %s %d' % (name, v))
    h += ['', '// Multipliers: x * NAME_M >> NAME_SH, rounded:']
    a += ['', '; Multipliers: x * NAME_M >> NAME_SH, rounded:']
    for name, v, com in k:
        m, sh = factor(v, name)
        if sh < 8 and name != 'K_FREE':
            raise ValueError('%s: shift %d' % (name, sh))
        if com:
            h.append('// %s (%.6g):' % (com, v))
            a.append('; %s (%.6g):' % (com, v))
        h.append('#define %s_M %d' % (name, m))
        h.append('#define %s_SH %d' % (name, sh))
        a.append('.DEFINE %s_M %d' % (name, m))
        a.append('.DEFINE %s_SH %d' % (name, sh))
    h += ['', '#endif', '']
    with open(os.path.join(out, 'phys_const.h'), 'w') as fh:
        fh.write('\n'.join(h))
    with open(os.path.join(out, 'phys_const.inc'), 'w') as fh:
        fh.write('\n'.join(a) + '\n')


# Tables ------------------------------------------------------------------

def tables(hz):
    dt = GAME_RATE / hz
    t = {}
    # sin(j/512) from 0 to pi/2, Q22 (24 bits), and the steps to the next:
    qs = [round(4194304 * math.sin(j / 512.0)) for j in range(807)]
    t['phys_qsin'] = ('s24', qs[:-1])
    t['phys_qsind'] = ('s16', [qs[j + 1] - qs[j] for j in range(806)])
    # 1/sqrt(m) for m = 64..256 (Q15, times 8):
    rsq = [min(32767, round(32768 * 8 / math.sqrt(64 + j))) for j in range(193)]
    t['phys_rsq'] = ('s16', rsq[:-1])
    t['phys_rsqd'] = ('s16', [rsq[j + 1] - rsq[j] for j in range(192)])
    # The torque of a wheel on its axle (Ftestnyom): 128/m for m = 128..256
    # times dt^2 V / (m T) 2^13 / 2^15:
    ktn = dt * dt * V / M_WHEEL / T * 2.0 ** 13 / 32768
    rcp = [round(32768 * 128.0 / (128 + j) * ktn) for j in range(129)]
    if max(rcp) > 32767:
        raise ValueError('phys_rcp')
    t['phys_rcp'] = ('s16', rcp[:-1])
    t['phys_rcpd'] = ('s16', [rcp[j + 1] - rcp[j] for j in range(128)])
    # The rolling wheel (beallit): 1/(theta + m h^2) for h = j*128 P (Q13):
    rho = [round(8192 / (TH_WHEEL + M_WHEEL * (j * 128 / P) ** 2)) for j in range(207)]
    t['phys_rho'] = ('s16', rho[:-1])
    t['phys_rhod'] = ('s16', [rho[j + 1] - rho[j] for j in range(206)])
    return t


def write_tables(out, hz):
    t = tables(hz)
    h = ['// Generated by tools/gen_phys.py: tables of the physics.',
         '#ifndef PHYS_TABLES_H', '#define PHYS_TABLES_H', '',
         '']
    a = ['; Generated by tools/gen_phys.py: tables of the physics.', '.include "hdr.asm"', '',
         '.SECTION ".phys_tables" SUPERFREE']
    for name, (typ, vals) in t.items():
        ctyp = {'s24': 'int32_t', 's16': 'int16_t', 's8': 'int8_t'}[typ]
        h.append('static const %s %s[%d] = {' % (ctyp, name, len(vals)))
        for j in range(0, len(vals), 12):
            h.append('\t' + ', '.join(str(v) for v in vals[j:j + 12]) + ',')
        h.append('};')
        a.append('%s:' % name)
        d, mask = {'s24': ('.dl', 0xFFFFFF), 's16': ('.dw', 0xFFFF), 's8': ('.db', 0xFF)}[typ]
        for j in range(0, len(vals), 12):
            a.append('\t%s %s' % (d, ', '.join(str(v & mask) for v in vals[j:j + 12])))
    h += ['', '#endif', '']
    a += ['.ENDS', '']
    with open(os.path.join(out, 'phys_tables.h'), 'w') as fh:
        fh.write('\n'.join(h))
    with open(os.path.join(out, 'phys_tables.asm'), 'w') as fh:
        fh.write('\n'.join(a))


# Levels ------------------------------------------------------------------

def fx(v):
    return int(round(v * P))


def u24(v):
    if not 0 <= v < 1 << 24:
        raise ValueError('out of the grid: %r' % v)
    return struct.pack('<I', v)[:3]


def kill_bounds(lines):
    """Where the body dies leaving the level: ecset::kilogna of the
    original (ECSET.CPP) with its brush of the 1.11a, as P thresholds."""
    xs = [x for a, b in lines for x in (a[0], b[0])]
    ys = [y for a, b in lines for y in (a[1], b[1])]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    arany = 48.0

    def meghelyez(d):
        return (int(d * arany) + 0.5) / arany
    eox = meghelyez(minx - 10000 / arany)
    eoy = meghelyez(miny - 1000 / arany)
    emaxx = ((maxx + 10000 / arany) - eox) * arany
    esorszam = ((maxy + 1000 / arany) - eoy) * arany

    def px(r):
        return (r / P - 320.0 / arany - eox) * arany

    def py(r):
        return (r / P - 240.0 / arany - eoy) * arany

    def first(lo, hi, test):
        # The smallest r in lo..hi where test(r) is true (test monotonic):
        while lo < hi:
            mid = (lo + hi) // 2
            if test(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo
    big = 1 << 30
    x0 = first(-big, big, lambda r: not (px(r) < 20))
    y0 = first(-big, big, lambda r: not (py(r) < 20))
    x1 = first(-big, big, lambda r: math.floor(px(r)) + 639 > emaxx - 20)
    y1 = first(-big, big, lambda r: math.floor(py(r)) + 479 > esorszam - 20)
    return x0, x1, y0, y1


def racs_bounds(lines):
    """szakaszok::felsorolasreset: a point this far right or up of the grid
    of the original (cells of 1 m from 6 m around the lines) sets
    Racsonkivul, which kills the bike."""
    xs = [x for a, b in lines for x in (a[0], b[0])]
    ys = [y for a, b in lines for y in (a[1], b[1])]
    minx, maxx, miny, maxy = min(xs) - 6.0, max(xs) + 6.0, min(ys) - 6.0, max(ys) + 6.0
    xdim = int((maxx - minx) / 1.0 + 1)
    ydim = int((maxy - miny) / 1.0 + 1)

    def first(o, dim):
        lo, hi = -(1 << 30), 1 << 30
        while lo < hi:
            mid = (lo + hi) // 2
            d = (mid / P - o) * (1 / 1.0)
            if (int(d) if d > 0 else 0) > dim:
                hi = mid
            else:
                lo = mid + 1
        return lo
    return first(minx, xdim), first(miny, ydim)


def seg_box_dist(ax, ay, bx, by, x0, y0, x1, y1):
    """Distance of a segment from a box (0 if they meet)."""
    t0, t1 = 0.0, 1.0
    dx, dy = bx - ax, by - ay
    meets = True
    for p, q in ((-dx, ax - x0), (dx, x1 - ax), (-dy, ay - y0), (dy, y1 - ay)):
        if p == 0:
            if q < 0:
                meets = False
        else:
            r = q / p
            if p < 0:
                if r > t1:
                    meets = False
                elif r > t0:
                    t0 = r
            else:
                if r < t0:
                    meets = False
                elif r < t1:
                    t1 = r
    if meets and t0 <= t1:
        return 0.0

    def pt_box(px, py):
        return math.hypot(max(x0 - px, 0, px - x1), max(y0 - py, 0, py - y1))

    def seg_pt(px, py):
        l2 = dx * dx + dy * dy
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / l2))
        return math.hypot(ax + t * dx - px, ay + t * dy - py)
    return min(pt_box(ax, ay), pt_box(bx, by), seg_pt(x0, y0), seg_pt(x1, y0),
               seg_pt(x0, y1), seg_pt(x1, y1))


def unit_q15(ux, uy):
    """A unit vector as Q15 (at most 32767) and the rest of it in 2^-23
    (signed bytes)."""
    ex = max(-32767, min(32767, round(ux * 32768)))
    ey = max(-32767, min(32767, round(uy * 32768)))
    lx = round((ux * 32768 - ex) * 256)
    ly = round((uy * 32768 - ey) * 256)
    return ex, ey, max(-128, min(127, lx)), max(-128, min(127, ly))


def killer_order(objects):
    """topol::killerekelore: killers first, then apples, flowers, the
    start (a stable bubble sort)."""
    rank = {elmadata.T_KILLER: 1, elmadata.T_APPLE: 2, elmadata.T_FLOWER: 3}
    objs = list(objects)
    n = len(objs)
    for _ in range(n + 4):
        for j in range(n - 1):
            if rank.get(objs[j][0], 10) > rank.get(objs[j + 1][0], 10):
                objs[j], objs[j + 1] = objs[j + 1], objs[j]
    return objs


def level_blob(lev):
    """The data of a level: (bytes, offsets of its 16-bit pointer fields)."""
    lines = []
    for grass, poly in lev.polygons:
        if grass:
            continue
        for j, a in enumerate(poly):
            lines.append((a, poly[(j + 1) % len(poly)]))
    xs = [x for a, b in lines for x in (a[0], b[0])]
    ys = [y for a, b in lines for y in (a[1], b[1])]
    gx, gy = math.floor(min(xs)) - 1, math.floor(min(ys)) - 1
    cell = (1 << CELL_SH) / P
    gw = int(math.ceil((max(xs) + 1 - gx) / cell))
    gh = int(math.ceil((max(ys) + 1 - gy) / cell))
    if gw > 255 or gh > 255 or (gw * cell) > 250 or (gh * cell) > 250:
        raise ValueError('level %s is too large' % lev.name)
    ptrs = []
    # The lines:
    lrec = []
    for (ax, ay), (bx, by) in lines:
        dx, dy = bx - ax, by - ay
        ln = math.hypot(dx, dy)
        ex, ey, lx, ly = unit_q15(dx / ln, dy / ln)
        box = [math.floor((min(ax, bx) - REACH - gx) * 256), math.ceil((max(ax, bx) + REACH - gx) * 256),
               math.floor((min(ay, by) - REACH - gy) * 256), math.ceil((max(ay, by) + REACH - gy) * 256)]
        box = [max(0, min(65535, v)) for v in box]
        # How far the length of e is from 1, as (2^30 - |e|^2)/2:
        dn = ((1 << 30) - (ex * ex + ey * ey)) >> 1
        if not -32768 <= dn <= 32767:
            raise ValueError('dn %d' % dn)
        # Points from the corner of the grid, as 24 bits:
        pa = [fx(ax) - fx(gx), fx(ay) - fx(gy)]
        pb = [fx(bx) - fx(gx), fx(by) - fx(gy)]
        rec = struct.pack('<4H', box[0], box[1], box[2], box[3])
        rec += u24(pa[0]) + u24(pa[1]) + struct.pack('<2h2bh', ex, ey, lx, ly, dn)
        rec += u24(fx(ln)) + u24(pb[0]) + u24(pb[1]) + b'\0'
        lrec.append(rec)
    # The cells: the lines near each, in the order of the lines:
    cells = {}
    for li, ((ax, ay), (bx, by)) in enumerate(lines):
        cx0 = max(0, int((min(ax, bx) - REACH - gx) // cell))
        cx1 = min(gw - 1, int((max(ax, bx) + REACH - gx) // cell))
        cy0 = max(0, int((min(ay, by) - REACH - gy) // cell))
        cy1 = min(gh - 1, int((max(ay, by) + REACH - gy) // cell))
        for cx in range(cx0, cx1 + 1):
            for cy in range(cy0, cy1 + 1):
                if seg_box_dist(ax, ay, bx, by, gx + cx * cell, gy + cy * cell,
                                gx + (cx + 1) * cell, gy + (cy + 1) * cell) <= REACH:
                    cells.setdefault((cx, cy), []).append(li)
    off_lines = HEADER_SIZE
    off_objs = off_lines + LINE_SIZE * len(lines)
    objs = killer_order(lev.objects)
    off_lists = off_objs + OBJ_SIZE * len(objs)
    # Lists: count, then the offsets of the lines:
    lists = bytearray()
    list_at = {}
    for key in sorted(cells):
        lst = tuple(cells[key])
        if lst in list_at:
            continue
        list_at[lst] = off_lists + len(lists)
        lists += struct.pack('<H', len(lst))
        for li in lst:
            ptrs.append(off_lists + len(lists))
            lists += struct.pack('<H', off_lines + LINE_SIZE * li)
    off_rows = off_lists + len(lists)
    # Rows: the offset of the runs of each row (and one more), runs of cells
    # with the same list: first cell, offset of the list (0: none).
    runs = bytearray()
    row_runs = []
    for cy in range(gh):
        row_runs.append(len(runs))
        prev = None
        for cx in range(gw):
            lst = tuple(cells.get((cx, cy), ()))
            if lst != prev:
                at = list_at.get(lst, 0)
                runs += struct.pack('<BH', cx, at)
                prev = lst
    row_runs.append(len(runs))
    off_runs = off_rows + 2 * (gh + 1)
    rows = bytearray()
    for j, r in enumerate(row_runs):
        ptrs.append(off_rows + len(rows))
        rows += struct.pack('<H', off_runs + r)
    # Pointers inside the runs:
    for j in range(0, len(runs), 3):
        if struct.unpack_from('<H', runs, j + 1)[0]:
            ptrs.append(off_runs + j + 1)
    # Objects (killerekelore order):
    orec = bytearray()
    apples = 0
    start = None
    for t, x, y, grav, anim in objs:
        orec += struct.pack('<4B2i', t, anim, grav, 0, fx(x), fx(y))
        if t == elmadata.T_APPLE:
            apples += 1
        if t == elmadata.T_START:
            start = (x, y)
    # The bike at the start (initmotor moved by setallaktiv, in doubles):
    sx, sy = start
    dxs, dys = sx - 1.9, sy - 3.0
    k1 = (2.75 + dxs, 3.6 + dys)
    k2 = (1.9 + dxs, 3.0 + dys)
    k4 = (3.6 + dxs, 3.0 + dys)
    rid = (2.75 + dxs, 4.04 + dys)
    kx0, kx1, ky0, ky1 = kill_bounds(lines)
    rx, ry = racs_bounds(lines)
    head = struct.pack('<2i2H2H4H2i4i', fx(gx), fx(gy), gw, gh, len(lines), len(objs),
                       off_lines, off_objs, off_lists, off_rows, rx, ry, kx0, kx1, ky0, ky1)
    head += struct.pack('<8i', fx(k1[0]), fx(k1[1]), fx(k2[0]), fx(k2[1]), fx(k4[0]), fx(k4[1]),
                        fx(rid[0]), fx(rid[1]))
    head += struct.pack('<H', apples)
    head += b'\0' * (HEADER_SIZE - len(head))
    ptrs += [16, 18, 20, 22]
    data = bytearray(head) + b''.join(lrec) + orec + lists + rows + runs
    return bytes(data), ptrs


def write_levels(res, out):
    levels = elmadata.internal_levels(elmadata.Resource(res))
    os.makedirs(os.path.join(out, 'phys'), exist_ok=True)
    a = ['; Generated by tools/gen_phys.py: the lines, grid and objects of the levels.',
         '.include "hdr.asm"', '']
    total = 0
    for n, lev in enumerate(levels):
        data, ptrs = level_blob(lev)
        if len(data) > 0x8000:
            raise ValueError('level %d: %d bytes' % (n, len(data)))
        total += len(data)
        with open(os.path.join(out, 'phys', 'lev%02d.bin' % n), 'wb') as fh:
            fh.write(data)
        # In the ROM the pointers are addresses in the bank of the level:
        ptrset = set(ptrs)
        a.append('.SECTION ".phys_lev%02d" SUPERFREE' % n)
        a.append('phys_lev%02d:' % n)
        j = 0
        row = []

        def flush():
            if row:
                a.append('\t.db ' + ', '.join(row))
                row.clear()
        while j < len(data):
            if j in ptrset:
                flush()
                a.append('\t.dw phys_lev%02d + %d' % (n, struct.unpack_from('<H', data, j)[0]))
                j += 2
                continue
            row.append(str(data[j]))
            j += 1
            if len(row) == 16:
                flush()
        flush()
        a.append('.ENDS')
        a.append('')
    a.append('.SECTION ".phys_lev_addr" SUPERFREE')
    a.append('phys_lev_addr:')
    for n in range(len(levels)):
        a.append('\t.dl phys_lev%02d' % n)
    a.append('.ENDS')
    a.append('')
    with open(os.path.join(out, 'phys_levels.asm'), 'w') as fh:
        fh.write('\n'.join(a))
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('res')
    ap.add_argument('out')
    ap.add_argument('--hz', type=int, default=80)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    write_constants(args.out, args.hz)
    write_tables(args.out, args.hz)
    total = write_levels(args.res, args.out)
    print('gen_phys.py: %d bytes of level data' % total)


if __name__ == '__main__':
    main()
