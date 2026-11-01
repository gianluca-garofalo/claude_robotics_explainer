"""Compact inline SVG: phase plane of the double-integrator LQR (q1=q2=r=1)."""
import numpy as np
from scipy.linalg import solve_continuous_are, expm

A = np.array([[0., 1.], [0., 0.]]); B = np.array([[0.], [1.]])
Q = np.eye(2); r = 1.0
P = solve_continuous_are(A, B, Q, np.array([[r]]))
K = B.T @ P / r; Acl = A - B @ K

ml, mr, mt, mb = 52, 16, 14, 30
qmin, qmax, vmin, vmax = -0.35, 1.25, -0.62, 0.30
s = 380.0  # px per unit, same on both axes so normals look normal
X = lambda q: ml + (q - qmin)*s
Y = lambda v: mt + (vmax - v)*s
W = int(round(ml + (qmax - qmin)*s + mr)); Hh = int(round(mt + (vmax - vmin)*s + mb))
px0, py0, pw, ph = X(qmin), Y(vmax), (qmax - qmin)*s, (vmax - vmin)*s

el = []
el.append(f'<rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph:.1f}" fill="none" stroke="#e2e8f0"/>')
el.append(f'<line x1="{X(qmin):.1f}" y1="{Y(0):.1f}" x2="{X(qmax):.1f}" y2="{Y(0):.1f}" stroke="#94a3b8" stroke-width="1"/>')
el.append(f'<line x1="{X(0):.1f}" y1="{Y(vmin):.1f}" x2="{X(0):.1f}" y2="{Y(vmax):.1f}" stroke="#94a3b8" stroke-width="1"/>')
el.append(f'<text x="{X(qmax):.1f}" y="{Y(vmin)+18:.1f}" text-anchor="end" font-size="14" fill="#64748b" font-style="italic">q</text>')
el.append(f'<text x="{X(qmin)-7:.1f}" y="{Y(vmax)+12:.1f}" text-anchor="end" font-size="14" fill="#64748b" font-style="italic">v</text>')
for qt in [0.5, 1.0]:
    el.append(f'<line x1="{X(qt):.1f}" y1="{Y(vmin):.1f}" x2="{X(qt):.1f}" y2="{Y(vmin)+4:.1f}" stroke="#94a3b8"/>')
    el.append(f'<text x="{X(qt):.1f}" y="{Y(vmin)+17:.1f}" text-anchor="middle" font-size="11" fill="#64748b">{qt:g}</text>')
el.append(f'<text x="{X(0):.1f}" y="{Y(vmin)+17:.1f}" text-anchor="middle" font-size="11" fill="#64748b">0</text>')
for vt, lab in [(-0.5, '&#8722;0.5'), (0.0, '0')]:
    el.append(f'<line x1="{X(qmin)-4:.1f}" y1="{Y(vt):.1f}" x2="{X(qmin):.1f}" y2="{Y(vt):.1f}" stroke="#94a3b8"/>')
    el.append(f'<text x="{X(qmin)-7:.1f}" y="{Y(vt)+4:.1f}" text-anchor="end" font-size="11" fill="#64748b">{lab}</text>')

clip = []
w_, U_ = np.linalg.eigh(P)
th = np.linspace(0, 2*np.pi, 241)
z0 = np.array([1.0, 0.0])
V0 = 0.5*z0 @ P @ z0
for c in [V0, 0.4, 0.15, 0.04]:
    pts = U_ @ np.vstack([np.sqrt(2*c/w_[0])*np.cos(th), np.sqrt(2*c/w_[1])*np.sin(th)])
    d = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in pts.T)
    clip.append(f'<polyline points="{d}" fill="none" stroke="#22c55e" stroke-width="1" stroke-dasharray="4 3"/>')
ts = np.linspace(0, 12, 300)
traj = np.array([expm(Acl*t) @ z0 for t in ts])
d = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in traj)
clip.append(f'<polyline points="{d}" fill="none" stroke="#3b82f6" stroke-width="2.2"/>')
el.append('<g clip-path="url(#clip7)">\n    ' + "\n    ".join(clip) + '\n  </g>')

el.append(f'<circle cx="{X(0):.1f}" cy="{Y(0):.1f}" r="3" fill="#0f172a"/>')
scale = 0.15
for t in [0.0, 0.6, 1.3]:
    z = expm(Acl*t) @ z0
    pi = -P @ z
    a, b = z; ea, eb = z + scale*pi
    el.append(f'<line x1="{X(a):.1f}" y1="{Y(b):.1f}" x2="{X(ea):.1f}" y2="{Y(eb):.1f}" stroke="#f59e0b" stroke-width="2.2" marker-end="url(#arr7)"/>')
    el.append(f'<circle cx="{X(a):.1f}" cy="{Y(b):.1f}" r="{4.5 if t == 0 else 3.2}" fill="#3b82f6"/>')
el.append(f'<text x="{X(1.0)+4:.1f}" y="{Y(0)-9:.1f}" text-anchor="middle" font-size="12.5" fill="#0f172a">z&#8320; = (1, 0)</text>')
# legend (top-left, inside plot)
lx, ly = X(qmin)+10, Y(vmax)+18
el.append(f'<rect x="{lx-6:.1f}" y="{ly-15:.1f}" width="232" height="58" rx="4" fill="#ffffff" fill-opacity="0.9" stroke="#e2e8f0"/>')
el.append(f'<line x1="{lx:.1f}" y1="{ly-4:.1f}" x2="{lx+22:.1f}" y2="{ly-4:.1f}" stroke="#3b82f6" stroke-width="2.2"/>')
el.append(f'<text x="{lx+28:.1f}" y="{ly:.1f}" font-size="12" fill="#0f172a">optimal path, u* = &#960;<tspan baseline-shift="sub" font-size="9">v</tspan>/r</text>')
ly += 18
el.append(f'<line x1="{lx:.1f}" y1="{ly-4:.1f}" x2="{lx+22:.1f}" y2="{ly-4:.1f}" stroke="#22c55e" stroke-width="1" stroke-dasharray="4 3"/>')
el.append(f'<text x="{lx+28:.1f}" y="{ly:.1f}" font-size="12" fill="#0f172a">level sets of V</text>')
ly += 18
el.append(f'<line x1="{lx:.1f}" y1="{ly-4:.1f}" x2="{lx+22:.1f}" y2="{ly-4:.1f}" stroke="#f59e0b" stroke-width="2.2" marker-end="url(#arr7)"/>')
el.append(f'<text x="{lx+28:.1f}" y="{ly:.1f}" font-size="12" fill="#0f172a">momentum &#960; = &#8722;&#8711;V (scaled)</text>')

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {Hh}" role="img" aria-label="Phase plane of the double-integrator example: the optimal path from (1,0) curls into the origin across the level sets of V; the momentum is drawn as arrows normal to the level sets" style="width:100%;max-width:{W}px;height:auto;font-family:inherit">\n'
       '  <defs>\n    <marker id="arr7" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">\n'
       '      <path d="M0,0 L10,5 L0,10 z" fill="#f59e0b"/>\n    </marker>\n'
       f'    <clipPath id="clip7"><rect x="{px0:.1f}" y="{py0:.1f}" width="{pw:.1f}" height="{ph:.1f}"/></clipPath>\n  </defs>\n  '
       + "\n  ".join(el) + '\n</svg>')
import os
base = os.path.dirname(os.path.abspath(__file__)) + '/'
open(base + 'fig4_double_integrator.svg', 'w').write(svg)
print(len(svg), "bytes;", W, "x", Hh)
