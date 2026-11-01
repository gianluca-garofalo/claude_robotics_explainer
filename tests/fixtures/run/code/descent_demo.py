"""Fixture script (tests only): scalar receding-horizon example, standard library only.

Plant x+ = a x + b u, stage cost l = q x^2 + r u^2, value V = P x^2 with P from the discrete Riccati equation.
Prints P, the gain K, the closed-loop factor, and the largest descent defect V(x+) - V(x) + l(x, u) over 20 steps
(zero up to rounding, because V is the exact infinite-horizon value). Writes figures/concept.svg.
"""
import os

a, b, q, r = 1.2, 1.0, 1.0, 1.0
P = q
for _ in range(500):
    P = q + a * a * P - (a * b * P) ** 2 / (r + b * b * P)
K = a * b * P / (r + b * b * P)

x, worst, vs = 1.0, -1.0e9, []
for k in range(21):
    vs.append(P * x * x)
    u = -K * x
    xn = a * x + b * u
    worst = max(worst, P * xn * xn - P * x * x + q * x * x + r * u * u)
    x = xn

print(f"P = {P:.6f}")
print(f"K = {K:.6f}")
print(f"closed-loop factor a - b K = {a - b * K:.6f}")
print(f"max descent defect over 20 steps = {worst:.1e}")

W, H, L, T, B = 520, 220, 50, 20, 40
pts = " ".join(f"{L + k * (W - L - 20) / 20:.1f},{T + (H - T - B) * (1 - v / vs[0]):.1f}" for k, v in enumerate(vs))
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" aria-label="Value V(x_k) falling to zero along the closed-loop trajectory">
  <line x1="{L}" y1="{H - B}" x2="{W - 10}" y2="{H - B}" stroke="#64748b"/>
  <line x1="{L}" y1="{H - B}" x2="{L}" y2="{T - 5}" stroke="#64748b"/>
  <polyline points="{pts}" fill="none" stroke="#3b82f6" stroke-width="2"/>
  <text x="{W - 12}" y="{H - B + 18}" text-anchor="end" font-size="13" fill="#64748b">step k</text>
  <text x="{L + 8}" y="{T + 8}" font-size="13" fill="#0f172a">V(x_k) = P x_k^2</text>
</svg>
"""
os.makedirs("figures", exist_ok=True)
with open(os.path.join("figures", "concept.svg"), "w", encoding="utf-8") as fh:
    fh.write(svg)
print("wrote figures/concept.svg")
