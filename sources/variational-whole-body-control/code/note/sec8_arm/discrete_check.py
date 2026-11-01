"""Torque-limit level and discrete condition (4) for u_ref = -R^{-1} s on sublevel sets of W."""
import numpy as np
from model import *
from condcheck import designs, KD, Lam, Qe_good, Qv_good, R
d = designs()['good']

rng = np.random.default_rng(3)
ndir = 200000
dirs = rng.normal(size=(ndir, 4)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
Wd = d.W(dirs*1e-3)/1e-6  # quadratic coefficient (approx) for scaling

def tau_ref(z):
    return gvec(qd + z[..., :2]) + d.uref(z)

def ray_level(fun, rmax=5.0, nr=400):
    """smallest W at which fun(z) > 0 first occurs along rays (fun <= 0 near 0)."""
    rs = np.geomspace(1e-4, rmax, nr)
    best = np.inf; bz = None
    for c0 in range(0, ndir, 10000):
        Dd = dirs[c0:c0+10000]
        Z = rs[None, :, None]*Dd[:, None, :]
        pos = fun(Z) > 0
        has = pos.any(1)
        if not has.any(): continue
        Dd = Dd[has]; idx = np.argmax(pos[has], 1)
        lo = np.where(idx > 0, rs[np.maximum(idx-1, 0)], 0.0); hi = rs[idx]
        for _ in range(50):
            mid = 0.5*(lo+hi); p = fun(mid[:, None]*Dd) > 0
            hi = np.where(p, mid, hi); lo = np.where(p, lo, mid)
        Z = hi[:, None]*Dd; Wz = d.W(Z); k = np.argmin(Wz)
        if Wz[k] < best: best, bz = Wz[k], Z[k]
    return best, bz

ctau, ztau = ray_level(lambda Z: np.max(np.abs(tau_ref(Z))/TAU_MAX, -1) - 1)
print('torque-limit level c_tau =', ctau, 'at z=', ztau, 'tau=', tau_ref(ztau), ' q=', qd+ztau[:2])
np.save('ctau.npy', ctau)

def sample_sublevel(c, n=400000):
    """points in {W <= c}: random direction, radius solving W = c * U^(1/2)... (log-uniform in W)."""
    D0 = dirs[:n % ndir or ndir]
    # find radius rc with W(rc d) = c by bisection
    lo = np.zeros(len(D0)); hi = np.full(len(D0), 50.0)
    for _ in range(60):
        mid = 0.5*(lo+hi); p = d.W(mid[:, None]*D0) > c
        hi = np.where(p, mid, hi); lo = np.where(p, lo, mid)
    frac = 10**rng.uniform(-4, 0, size=len(D0))   # log-uniform fraction of the radius
    return (lo*frac)[:, None]*D0

for h in [0.01, 0.005]:
    for c in [0.5, 1.0, 2.0, ctau]:
        Z = sample_sublevel(c)
        U = d.uref(Z)
        Zp = step(Z, U, h)
        dW = d.W(Zp) - d.W(Z)
        hl = h*d.ell(Z, U)
        ok_dec = (dW < 0).all()
        need = np.max(hl/(-dW)) if ok_dec else np.inf
        viol1 = np.max(dW + hl)
        print(f'h={h} c={c:.4f}: W decreases everywhere? {ok_dec}; max[dW + h l] (c_W=1) = {viol1:.3e}; '
              f'needed c_W = {need:.5f}; max |tau| ratio = {np.max(np.abs(tau_ref(Z))/TAU_MAX):.3f}; '
              f'invariant: max W(F)/c = {np.max(d.W(Zp))/c:.4f}')
# quadratic-limit (near origin) ratio
Z = dirs[:100000]*1e-4
for h in [0.01, 0.005]:
    U = d.uref(Z); dW = d.W(step(Z, U, h)) - d.W(Z); print('near-origin needed c_W h=', h, np.max(h*d.ell(Z, U)/(-dW)))
