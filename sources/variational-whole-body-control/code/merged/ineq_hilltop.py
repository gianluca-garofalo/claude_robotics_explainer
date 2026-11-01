"""Inequalities in the first-order theory: the hilltop with a speed limit |v| <= vbar.

L = 1/2 m v^2 + 1/2 kappa q^2, omega = sqrt(kappa/m), qdot = v, admissible set V = [-vbar, vbar].
(1) Constrained Hamiltonian H_V(q,p) = sup_{|v|<=vbar} [p v - L]  (closed form vs numerical sup).
(2) Infinitesimal-window rule with W = V_unc = 1/2 sqrt(m kappa) q^2: v* = clip(-omega q, +-vbar).
    Certificate: H_V(q, -V_unc') = 0 for |q| <= q_s = vbar/omega and -1/2 (sqrt(kappa)|q| - sqrt(m) vbar)^2 < 0 beyond.
(3) Constrained remaining action V_con (closed form): H_V(q, -V_con') = 0 everywhere, V_con is C^2 at q_s,
    V_con >= V_unc, and the clipped law is optimal: int_0^inf L dt along it equals V_con(q0).
(4) One discrete step (rectangle rule, h = 0.1, W = 1/2 q^2) with the step bound q - q' <= h vbar active:
    KKT multiplier mu >= 0 and arrival momentum p' = d_2 L_d = -W'(q') + mu.
"""
import numpy as np
from scipy.integrate import solve_ivp, quad
from scipy.optimize import minimize_scalar

m, k, vbar = 1.0, 1.0, 0.5
w = np.sqrt(k/m); qs = vbar/w; c = np.sqrt(m*k)
L = lambda q, v: 0.5*m*v*v + 0.5*k*q*q


def HV(q, p):
    v = np.clip(p/m, -vbar, vbar)
    return p*v - L(q, v)


def HV_num(q, p):
    r = minimize_scalar(lambda v: -(p*v - L(q, v)), bounds=(-vbar, vbar), method='bounded', options={'xatol': 1e-12})
    return -r.fun


Vu = lambda q: 0.5*c*q*q
dVu = lambda q: c*q


def Vc(q):
    a = abs(q)
    if a <= qs:
        return 0.5*c*a*a
    return 0.5*c*qs*qs + 0.5*m*vbar*(a - qs) + k*(a**3 - qs**3)/(6*vbar)


def dVc(q):
    a = abs(q); s = np.sign(q)
    return s*(c*a if a <= qs else (0.5*m*vbar**2 + 0.5*k*a*a)/vbar)


qs_grid = np.linspace(-2, 2, 401)
print(f"m = kappa = {m}, vbar = {vbar}: saturation boundary q_s = vbar/omega = {qs}")
print("(1) max |H_V closed form - numerical sup| =", f"{max(abs(HV(q, p) - HV_num(q, p)) for q in qs_grid[::20] for p in np.linspace(-3, 3, 13)):.1e}")
cert = np.array([HV(q, -dVu(q)) for q in qs_grid])
pred = np.array([0.0 if abs(q) <= qs else -0.5*(np.sqrt(k)*abs(q) - np.sqrt(m)*vbar)**2 for q in qs_grid])
print("(2) H_V(q,-V_unc') vs formula: max diff", f"{np.abs(cert - pred).max():.1e}", "; at q = 1:", f"{HV(1.0, -dVu(1.0)):.6f}",
      "; certificate holds exactly on |q| <= q_s:", bool(np.all((cert >= -1e-15) == (np.abs(qs_grid) <= qs + 1e-12))))
res = np.array([HV(q, -dVc(q)) for q in qs_grid])
print("(3) max |H_V(q,-V_con')| =", f"{np.abs(res).max():.1e}", "; min (V_con - V_unc) =", f"{min(Vc(q) - Vu(q) for q in qs_grid):.1e}",
      "; V_con(1) =", f"{Vc(1.0):.6f}", " V_unc(1) =", f"{Vu(1.0):.6f}")
inner1, outer1 = c*qs, (0.5*m*vbar**2 + 0.5*k*qs*qs)/vbar          # one-sided first derivatives at q_s
inner2, outer2 = c, k*qs/vbar                                    # one-sided second derivatives
print(f"    one-sided values at q_s: V_con' {inner1:.6f} | {outer1:.6f};  V_con'' {inner2:.6f} | {outer2:.6f};"
      f"  third derivative 0 | {k/vbar:.6f}  (C^2, not C^3)")
sol = solve_ivp(lambda t, y: [np.clip(-w*y[0], -vbar, vbar), L(y[0], np.clip(-w*y[0], -vbar, vbar))], [0, 60], [1.0, 0.0],
                rtol=1e-12, atol=1e-14, max_step=0.01)
print("    clipped law from q0 = 1: int_0^60 L dt =", f"{sol.y[1, -1]:.6f}", " (V_con(1) =", f"{Vc(1.0):.6f})",
      "; saturated until t =", f"{(1 - qs)/vbar:.3f} s")
# (4) one discrete step with a step bound
h, q = 0.1, 1.0
Ld = lambda q, qp: m*(qp - q)**2/(2*h) + h*k*q*q/2
Wd = lambda x: 0.5*x*x
r = minimize_scalar(lambda qp: Ld(q, qp) + Wd(qp), bounds=(q - h*vbar, q + h*vbar), method='bounded', options={'xatol': 1e-13})
qp = r.x
d2L = m*(qp - q)/h
mu = d2L + qp                       # g = q - q' - h vbar <= 0, grad_{q'} g = -1:  d2L + W' - mu = 0
print(f"(4) unconstrained step q' = {q/(1 + h):.6f}; with q - q' <= h vbar: q' = {qp:.6f}, mu = {mu:.6f} (>= 0),"
      f" p' = d_2 L_d = {d2L:.6f} = -W'(q') + mu = {-qp + mu:.6f}")
