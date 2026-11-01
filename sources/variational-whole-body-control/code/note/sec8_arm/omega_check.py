"""Discrete terminal condition (4) on Omega_c = {W <= c}, u_ref = -R^{-1}s, semi-implicit Euler.
needed c_W = sup_{z in Omega} h l(z,u_ref) / (W(z) - W(F(z,u_ref)));  sampled + local refinement."""
import numpy as np
from scipy.optimize import minimize
from model import *
from condcheck import designs
d = designs()['good']
rng = np.random.default_rng(7)
c = 0.3

def tau_ref(z): return gvec(qd + z[..., :2]) + d.uref(z)

def ratio(z, h):
    U = d.uref(z); dW = d.W(step(z, U, h)) - d.W(z)
    return h*d.ell(z, U)/(-dW), dW

n = 400000
dirs = rng.normal(size=(n, 4)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
lo = np.zeros(n); hi = np.full(n, 50.0)
for _ in range(60):
    mid = 0.5*(lo+hi); p = d.W(mid[:, None]*dirs) > c
    hi = np.where(p, mid, hi); lo = np.where(p, lo, mid)
rb = lo
for h in [0.005, 0.01]:
    out = []
    for frac in [1.0, 0.7, 0.4, 0.1, 1e-3]:
        Z = (rb*frac)[:, None]*dirs
        r, dW = ratio(Z, h)
        out.append((frac, r.max(), (dW < 0).all(), np.max(np.abs(tau_ref(Z))/TAU_MAX), np.max(d.W(step(Z, d.uref(Z), h)))/c))
    # local refinement of the worst samples on the full set (inside Omega via penalty-free constraint)
    Z = (rb*rng.uniform(0, 1, n)**0.25)[:, None]*dirs
    r, _ = ratio(Z, h); idx = np.argsort(r)[-20:]
    best = r.max()
    for i in idx:
        res = minimize(lambda z: -ratio(z, h)[0], Z[i], method='SLSQP',
                       constraints=[{'type': 'ineq', 'fun': lambda z: c - d.W(z)}], options={'ftol': 1e-14, 'maxiter': 300})
        if d.W(res.x) <= c*(1+1e-9) and np.linalg.norm(res.x) > 1e-8:
            best = max(best, -res.fun)
    print(f'h={h}: per-shell (fraction of boundary radius, max ratio, W decreases, max|tau|/limit, max W(F)/c):')
    for o in out: print('    ', ['%.4g' % x if not isinstance(x, (bool, np.bool_)) else x for x in o])
    print(f'  sup ratio (sampled + refined) on Omega_{c}: {best:.5f}')
