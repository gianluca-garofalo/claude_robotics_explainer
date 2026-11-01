"""Torque limits and the terminal constraint as inequalities on the two-link arm (merged document, Sec. 10.7).

(1) Infinitesimal-window rule with the torque box |tau| <= tau_max (tau = g + u): the box-constrained minimizer of
    l + Wdot is the componentwise clip of -R^{-1}s for the diagonal R used here (checked with a QP solver), i.e.
    saturated PD+g; with Gauss's weight R = T0 M^{-1} it is the M^{-1}-metric projection, which is not a clip.
(2) Certificate with the box: D_U(z) = min_{u in U(z)} [l + Wdot] = l(z,u_clip) + Wdot(z,u_clip) >= D(z).
    Largest level of {W <= c} on which D_U <= 0 (sampled ray search, like condcheck.py), compared with the torque-limit
    level 0.340 below which the box is inactive.
(3) KKT of the receding-window problem (single shooting, N = 10) along the first steps of the run from (1.0, -0.95):
    active torque bounds with multipliers >= 0 and the multiplier mu >= 0 of the active terminal constraint W(z_N) <= 0.3.
    The arrival momentum is pi_N = -(1 + mu) grad W(z_N): an active terminal constraint acts as a boundary term (1+mu) W.
Needs quadprog (pip install quadprog). Run time: about two minutes.
"""
import os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'note', 'sec8_arm'))
import numpy as np                                           # noqa: E402
import quadprog                                              # noqa: E402
from model import Mmat, gvec, qd, TAU_MAX                    # noqa: E402
from condcheck import designs                                # noqa: E402

d = designs()['good']
rng = np.random.default_rng(3)


def box(z):
    g = gvec(qd + z[..., :2]); return -TAU_MAX - g, TAU_MAX - g


def u_clip(z):
    lb, ub = box(z); return np.clip(d.uref(z), lb, ub)


def D_box(z):
    u = u_clip(z); return d.ell(z, u) + d.Wdot(z, u)


def qp_box(G, s, lb, ub):
    """min 1/2 u'Gu + s'u  s.t. lb <= u <= ub  (quadprog: min 1/2 x'Gx - a'x, C'x >= b)."""
    C = np.hstack([np.eye(2), -np.eye(2)]); b = np.concatenate([lb, -ub])
    return quadprog.solve_qp(G, -s, C, b, 0)[0]


# ---------------------------------------------------------------- (1)
worst = 0.0; nsat = 0
for _ in range(2000):
    z = np.concatenate([rng.normal(scale=0.4, size=2), rng.normal(scale=4.0, size=2)])
    s = d.s(z); lb, ub = box(z)
    uq = qp_box(d.R, s, lb, ub); uc = u_clip(z)
    worst = max(worst, np.abs(uq - uc).max()); nsat += int(np.any((uc <= lb + 1e-12) | (uc >= ub - 1e-12)))
print(f"(1) diagonal R: box-QP minimizer vs componentwise clip, 2000 states ({nsat} saturated): max diff {worst:.1e}")
T0 = 0.05
gap = 0.0
for _ in range(2000):
    z = np.concatenate([rng.normal(scale=0.4, size=2), rng.normal(scale=4.0, size=2)])
    M = Mmat(qd + z[:2]); s = d.s(z); lb, ub = box(z)
    RG = T0*np.linalg.inv(M); u_unc = -np.linalg.solve(RG, s)
    uq = qp_box(RG, s, lb, ub); uc = np.clip(u_unc, lb, ub)
    if np.abs(uq - uc).max() > gap:
        gap, zg, ug, ucg, uug, RGg, sg = np.abs(uq - uc).max(), z, uq, uc, u_unc, RG, s
gq = gvec(qd + zg[:2]); cost = lambda u: 0.5*u@RGg@u + sg@u
print(f"    Gauss weight R = T0 M^-1 (T0 = {T0} s), same 2000 states: largest |QP - clip| = {gap:.2f} N m; at z = {np.round(zg, 2)}:"
      f" unconstrained tau = {np.round(uug + gq, 1)}, QP tau = {np.round(ug + gq, 1)}, clipped tau = {np.round(ucg + gq, 1)};"
      f" cost QP {cost(ug):.2f} < clip {cost(ucg):.2f}")

# ---------------------------------------------------------------- (2)
def ray_search(D, ndir=100000, rmax=10.0, nr=400, seed=0):
    r = np.random.default_rng(seed)
    dirs = r.normal(size=(ndir, 4)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    rs = np.geomspace(1e-3, rmax, nr); best = np.inf; bestz = None
    for c0 in range(0, ndir, 5000):
        Dd = dirs[c0:c0 + 5000]
        Z = rs[None, :, None]*Dd[:, None, :]
        pos = D(Z) > 0; has = pos.any(1)
        if not has.any():
            continue
        Dd = Dd[has]; idx = np.argmax(pos[has], 1)
        lo = np.where(idx > 0, rs[np.maximum(idx - 1, 0)], 0.0); hi = rs[idx]
        for _ in range(50):
            mid = 0.5*(lo + hi); p = D(mid[:, None]*Dd) > 0
            hi = np.where(p, mid, hi); lo = np.where(p, lo, mid)
        Zb = hi[:, None]*Dd; Wz = d.W(Zb); k = np.argmin(Wz)
        if Wz[k] < best:
            best, bestz = Wz[k], Zb[k]
    return best, bestz


from scipy.optimize import minimize                          # noqa: E402
RS = np.geomspace(1e-3, 12.0, 3000)


def first_fail(dv):
    """W at the first point along the ray z = r dv (|dv| = 1) where D_U > 0 (grid + bisection); inf if none."""
    dv = dv/np.linalg.norm(dv); Dv = D_box(RS[:, None]*dv[None, :]); pos = np.nonzero(Dv > 0)[0]
    if len(pos) == 0:
        return np.inf
    i = pos[0]; lo, hi = (RS[i - 1] if i > 0 else 0.0), RS[i]
    for _ in range(60):
        mid = 0.5*(lo + hi)
        if D_box(mid*dv) > 0:
            hi = mid
        else:
            lo = mid
    return float(d.W(hi*dv))


cands = []
for seed in (0, 11, 12):
    lev_s, z_s = ray_search(D_box, ndir=100000, rmax=12.0, nr=500, seed=seed)
    cands.append(z_s/np.linalg.norm(z_s))
    print(f"(2) ray search, seed {seed:2d} (1e5 directions): first failure of D_U <= 0 at W = {lev_s:.3f}")
best_lev = np.inf
for dv in cands:                                   # local refinement over directions (Nelder-Mead on the unit sphere)
    r = minimize(lambda x: first_fail(x), dv, method='Nelder-Mead', options={'xatol': 1e-6, 'fatol': 1e-6, 'maxiter': 600})
    best_lev = min(best_lev, r.fun)
print(f"    after local refinement over directions: the certificate with the torque box holds on {{W <= c}} for c up to about {best_lev:.2f}")
print("    without the box the same search gives about 1.0e3 (condcheck.py); below 0.340 the box is inactive (discrete_check.py)")
from model import step                                        # noqa: E402
h = 0.005; dirs = rng.normal(size=(200000, 4)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
for Wbar in [0.34, 1.0, 2.0, 4.0, 6.0]:
    lo_ = np.zeros(len(dirs)); hi_ = np.full(len(dirs), 60.0)
    for _ in range(60):
        mid = 0.5*(lo_ + hi_); pp = d.W(mid[:, None]*dirs) > Wbar
        hi_ = np.where(pp, mid, hi_); lo_ = np.where(pp, lo_, mid)
    worst_ratio = 0.0; decr = True
    for frac in [1.0, 0.85, 0.7, 0.5, 0.3, 0.1, 0.01]:
        Z = (lo_*frac)[:, None]*dirs; U = u_clip(Z); dW = d.W(step(Z, U, h)) - d.W(Z)
        decr = decr and bool((dW < 0).all()); worst_ratio = max(worst_ratio, (h*d.ell(Z, U)/(-dW)).max())
    print(f"    discrete condition (h = {h} s, c = 1, clipped reference): on {{W <= {Wbar}}} sup h l/(W - W o Phi_h) = {worst_ratio:.4f},"
          f" W decreases: {decr}")

# ---------------------------------------------------------------- (3)
from mpc import cost_grad, term_con, term_con_grad, ref_tail, f_G, rollout, H_STEP, C_OMEGA   # noqa: E402
from closedloop import solve_scaled                          # noqa: E402
N = 10; z = np.array([1.0 - qd[0], -0.95 - qd[1], 0.0, 0.0]); x = None
print(f"(3) KKT along the receding-window run from (1.0, -0.95), N = {N}:")
for k in range(10):
    if x is None:
        x = ref_tail(z, N).ravel()
    Jc = cost_grad(x, z, N)[0]
    r = solve_scaled(z, N, x, max(Jc, 1e-300)); xs = r.x
    J, gJ = cost_grad(xs, z, N); gW = -term_con_grad(xs, z, N)          # gradient of W(z_N) w.r.t. the torques
    act_t = abs(term_con(xs, z, N)) < 1e-7
    tm = np.tile(TAU_MAX, N); up = xs >= tm - 1e-7; lo = xs <= -tm + 1e-7; free = ~(up | lo)
    mu = -(gW[free]@gJ[free])/(gW[free]@gW[free]) if act_t else 0.0
    res = gJ + mu*gW
    nu_up = -res[up]; nu_lo = res[lo]
    print(f"    k = {k}: terminal constraint active: {act_t}, mu = {mu:7.3f}; bounds active: {int(up.sum() + lo.sum()):2d};"
          f" min bound multiplier {min(np.concatenate([nu_up, nu_lo, [np.inf]])):9.3e};"
          f" stationarity residual on free torques {np.abs(res[free]).max():.1e}")
    zz = rollout(z, xs.reshape(N, 2))                                    # predicted path; warm start as in closedloop.py
    z = np.asarray(f_G(z, xs[:2], H_STEP), float).ravel()
    x = np.concatenate([xs[2:], ref_tail(zz[N], 1).ravel()])
