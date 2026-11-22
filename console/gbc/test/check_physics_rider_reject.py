"""Exhaust the integer regions skipped by the conservative rider bounds."""
import argparse,json,re
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--gen',type=Path,default=BASE/'build/gen');p.add_argument('--out',type=Path,default=BASE/'build/rider-reject-check');a=p.parse_args();text=(a.gen/'riding_constants.h').read_text();v={key:int(value)for key,value in re.findall(r'#define (\w+) (-?\d+)(?:\n|$)',text)}
row=re.search(r'#define RIDING_ELLIPSE_INSIDE_Y_VALUES ([\d,]+)',text);assert row,'generate current riding_constants.h first';table=list(map(int,row[1].split(',')))
def kmul(x,name):return max(-32768,min(32767,(x*v[name+'_M']+(1<<(v[name+'_E']-1)))>>v[name+'_E']))
right,top=v['RIDER_RIGHT'],v['RIDER_TOP'];shift=v['RIDING_ELLIPSE_BUCKET_SHIFT'];assert len(table)==(right>>shift)+1
ellipse_pairs=0
for x in range(1,right+1):
 xs=kmul(x,'C_ELLIPSE')
 for y in range(1,top+1):
  assert y>table[x>>shift]or xs*xs+y*y<=top*top,(x,y,table[x>>shift])
  ellipse_pairs+=1
seat_pairs=0;low=32767;high=-32768
if v['RIDING_SEAT_FAST_ENABLED']:
 for x in range(-32768,v['RIDING_SEAT_FAST_X']+1):
  sx=x-v['SEAT_X'];assert -32768<=sx<=32767
  nx=kmul(sx,'C_SEAT_NX')
  for y in range(v['RIDING_SEAT_FAST_Y'],top+1):
   sy=y-v['SEAT_Y'];assert -32768<=sy<=32767
   under=kmul(sy,'C_SEAT_NY')-nx
   assert 0<=under<=32767,(x,y,under)
   low=min(low,under);high=max(high,under);seat_pairs+=1
def prove_rotated_box():
    # Cs and Sn are sampled from the same interpolated phase. Linear extrema
    # over the box occur at corners, and rounding preserves monotonicity.
    assembly = (BASE/'src/physics_rider_response.s').read_text()
    radius = int(re.search(r'^rider_box_radius = (\d+)$', assembly, re.M)[1])
    math_source = (BASE/'src/physics_math.c').read_text()
    sine = list(map(int, re.findall(r'-?\d+', re.search(
        r'Sintab\[257\] = \{([^}]+)\}', math_source)[1])))
    def trig(phase):
        i, f = divmod(phase & 65535, 256)
        return sine[i] + ((sine[i+1] - sine[i]) * f >> 8)

    # Use the actual scheduled Q24 coefficients, including both subphases.
    def coefficients(name):
        values = re.search(r'q24_' + name + r'\[2\]=\{([^}]+)\}', text)
        if values:
            return list(map(int, values[1].split(',')))
        assert not v.get('RIDING_PC_SCHEDULE')
        return [v[name+'_M'] << (24-v[name+'_E'])]

    q14, q24 = 1 << 14, 1 << 24
    profiles = set(zip(*(coefficients(name) for name in
                         ('C_SEAT_NX', 'C_SEAT_NY', 'C_ELLIPSE'))))
    minimum_under = 32767
    for phase in range(65536):
        cs, sn = trig(phase+16384), trig(phase)
        cx = -((13*(sn >> 8) >> 1) + 3)
        cy = -((13*~(cs >> 8) >> 1) + 3)
        corners = [(dx*cs+dy*sn, dy*cs-dx*sn)
                   for dx in (cx-radius, cx+radius)
                   for dy in (cy-radius, cy+radius)]
        xmax = max(abs((x+q14//2)//q14) for x, y in corners)
        ymin = min((y+q14//2)//q14 for x, y in corners)
        ymax = max((y+q14//2)//q14 for x, y in corners)
        assert -xmax >= v['RIDER_LEFT'] and xmax <= right and ymax <= top
        for nx, ny, ellipse in profiles:
            under = ((ymin-v['SEAT_Y'])*ny+q24//2)//q24 - ((xmax-v['SEAT_X'])*nx+q24//2)//q24
            under_max = ((ymax-v['SEAT_Y'])*ny+q24//2)//q24 - ((-xmax-v['SEAT_X'])*nx+q24//2)//q24
            assert 0 <= under <= under_max <= 32767
            minimum_under = min(minimum_under, under)
            for x, y in corners:
                # For either turn, this convex function bounds the squared
                # ellipse radius, allowing half a unit at both roundings.
                # Its maximum over the entire box is attained at a corner.
                xs_bound = (abs(x)+q14//2)*ellipse + q14*q24//2
                y_bound = (abs(y)+q14//2)*q24
                assert xs_bound**2 + y_bound**2 <= (top*q14*q24)**2
    return dict(phases=65536, box_points_per_phase=(2*radius+1)**2,
                turns=2, minimum_seat_under=minimum_under)

report={'ellipse_integer_pairs':ellipse_pairs,'seat_integer_pairs':seat_pairs,'ellipse_table_bytes':len(table)*2,'minimum_seat_under':low,'maximum_seat_under':high,'rotated_box':prove_rotated_box(),'differences':0};a.out.mkdir(parents=True,exist_ok=True);(a.out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
