import sys, json, time
sys.path.insert(0, "/home/claude/3D-animator-architect/backend")
import cv2, numpy as np
from app.models.schemas import FloorPlanGeometry
from app.pipeline import cv_extract
from app.pipeline.validate import find_room_overlaps

project_dir, out = sys.argv[1], sys.argv[2]
d = json.load(open(f"{project_dir}/project.json"))
img_bytes = open(f"{project_dir}/floorplan_{d['floorplan_filename']}" if not d['floorplan_filename'].startswith('floorplan_') else f"{project_dir}/{d['floorplan_filename']}", "rb").read()
llm = FloorPlanGeometry.model_validate(d["geometry"])
t = time.time()
res = cv_extract.refine_geometry_with_cv(img_bytes, llm)
print(f"runtime {time.time()-t:.1f}s")
if res is None:
    print("RESULT: None (fallback to LLM)")
    sys.exit(0)
for f in res.compliance_flags:
    if "Bildanalyse" in f.standard:
        print(f.severity, f.message)
print("overlaps:", len(find_room_overlaps(res)))
print("walls:", len(res.walls), "openings:", sum(len(w.openings) for w in res.walls))
for r in res.rooms:
    from shapely.geometry import Polygon
    print(f"  {r.name:12s} label={r.area_m2}  polygon={Polygon([(p.x,p.y) for p in r.polygon]).area:.2f} m2")
# overlay: back to px using message ppm
import re
ppm = float(re.search(r"([0-9.]+) px/m", [f.message for f in res.compliance_flags if 'px/m' in f.message][0]).group(1))
img = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
# recompute origin: min of room polygon px is unknown; approximate by matching: store origin via first room bbox
# simpler: re-run internals is costly; draw in meter space onto blank canvas instead
W = int(max(max(p.x for r in res.rooms for p in r.polygon), max(max(w.start.x,w.end.x) for w in res.walls))*ppm)+80
H = int(max(max(p.y for r in res.rooms for p in r.polygon), max(max(w.start.y,w.end.y) for w in res.walls))*ppm)+80
canvas = np.full((H+40, W+40, 3), 255, np.uint8)
off = 40
rng = np.random.default_rng(1)
for r in res.rooms:
    pts = np.array([[(p.x*ppm)+off, (p.y*ppm)+off] for p in r.polygon], np.int32)
    cv2.fillPoly(canvas, [pts], tuple(int(c) for c in rng.integers(150, 240, 3)))
    cx, cy = pts.mean(axis=0).astype(int)
    cv2.putText(canvas, r.name, (cx-40, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,0), 2)
for w in res.walls:
    p0 = (int(w.start.x*ppm)+off, int(w.start.y*ppm)+off); p1 = (int(w.end.x*ppm)+off, int(w.end.y*ppm)+off)
    color = (40,40,40) if w.height_m > 1.5 else (0,140,255)
    cv2.line(canvas, p0, p1, color, max(2, int(w.thickness_m*ppm)))
    L = max(1e-6, ((w.end.x-w.start.x)**2+(w.end.y-w.start.y)**2)**0.5)
    ux, uy = (w.end.x-w.start.x)/L, (w.end.y-w.start.y)/L
    for o in w.openings:
        a = (w.start.x+ux*o.position_on_wall_m, w.start.y+uy*o.position_on_wall_m)
        b = (a[0]+ux*o.width_m, a[1]+uy*o.width_m)
        col = (255,120,0) if o.type.value=="window" else (0,200,0)
        cv2.line(canvas, (int(a[0]*ppm)+off,int(a[1]*ppm)+off), (int(b[0]*ppm)+off,int(b[1]*ppm)+off), col, max(2,int(w.thickness_m*ppm)))
cv2.imwrite(out, canvas)
print("saved", out)
