"""Condition check D(z) = min_u [l + Wdot] <= 0 : quadratic analysis and largest sublevel set (sampled)."""
import numpy as np
from scipy.optimize import minimize
from model import *

lam = 2.0
Lam = lam*np.eye(2)
R = np.diag([0.05, 0.1])
KD = np.linalg.inv(R)
M0 = Mmat(qd)
Ke_match = Lam@KD - Lam@M0@Lam
Qe_good = np.diag([40.0, 20.0])
Qv_good = np.diag([4.0, 4.0])

def designs():
    return {
        'good': Design(Lam, Ke_match, Qe_good, Qv_good, R, 'matched K_e, Q with margin'),
        'KeLK': Design(Lam, Lam@KD, Qe_good, Qv_good, R, 'K_e = Lam K_D (no M0 correction)'),
        'SL': Design(Lam, 2*Lam@KD, Qe_good, Qv_good, R, 'Slotine-Li K_e = 2 Lam K_D'),
        'Qbig': Design(Lam, Ke_match, 1.5*Lam@KD@Lam, Qv_good, R, 'Q_e = 1.5 Lam K_D Lam'),
        'edge': Design(Lam, Ke_match, Lam@KD@Lam, KD - (M0@Lam + Lam@M0), R, 'Q at the matching bound (theta=1)'),
    }


def quad_D(d):
    """Hessian of D at 0 (finite differences) and the analytic formula."""
    Ma = d.Lam@M0
    A = np.block([[d.Qe - d.Lam@d.Rinv@d.Lam, (d.Ke - d.Lam@d.Rinv + d.Lam@M0@d.Lam)],
                  [(d.Ke - d.Lam@d.Rinv + d.Lam@M0@d.Lam).T, d.Qv - d.Rinv + M0@d.Lam + d.Lam@M0]])
    # A is the Hessian of D: D2 = 1/2 z^T A z
    eps = 1e-4; H = np.zeros((4, 4))
    for i in range(4):
        for j in range(4):
            zi = np.zeros(4); zj = np.zeros(4); zi[i] = eps; zj[j] = eps
            H[i, j] = (d.D(zi+zj) - d.D(zi-zj) - d.D(-zi+zj) + d.D(-zi-zj))/(4*eps**2)
    return A, H


def ray_search(d, ndir=200000, seed=0, rmax=3.0, nr=300):
    rng = np.random.default_rng(seed)
    dirs = rng.normal(size=(ndir, 4)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    rs = np.geomspace(1e-4, rmax, nr)
    best = np.inf; bestz = None
    chunk = 10000
    for c0 in range(0, ndir, chunk):
        Dd = dirs[c0:c0+chunk]
        Z = rs[None, :, None]*Dd[:, None, :]   # (n, nr, 4)
        Dv = d.D(Z)
        pos = Dv > 0
        has = pos.any(1)
        if not has.any():
            continue
        Dd = Dd[has]; idx = np.argmax(pos[has], 1)
        lo = np.where(idx > 0, rs[np.maximum(idx-1, 0)], 0.0); hi = rs[idx]
        for _ in range(50):
            mid = 0.5*(lo+hi)
            p = d.D(mid[:, None]*Dd) > 0
            hi = np.where(p, mid, hi); lo = np.where(p, lo, mid)
        Z = hi[:, None]*Dd; Wz = d.W(Z)
        k = np.argmin(Wz)
        if Wz[k] < best:
            best, bestz = Wz[k], Z[k]
    return best, bestz


def refine(d, z0):
    # minimize W subject to D(z) >= 0, staying away from the origin
    cons = [{'type': 'ineq', 'fun': lambda z: d.D(z)},
            {'type': 'ineq', 'fun': lambda z: z@z - 1e-6}]
    r = minimize(lambda z: d.W(z), z0, constraints=cons, method='SLSQP', options={'ftol': 1e-14, 'maxiter': 500})
    return r


RMAX = 30.0
if __name__ == '__main__':
    np.set_printoptions(precision=4, suppress=True)
    print('M0 =\n', M0, '\neig M0', np.linalg.eigvalsh(M0))
    print('K_D =', np.diag(KD), ' Lambda =', lam)
    print('K_e matched =\n', Ke_match, ' eig', np.linalg.eigvalsh(Ke_match))
    print('K_D - 2 sym(M0 Lam) =\n', KD - (M0@Lam+Lam@M0), ' eig', np.linalg.eigvalsh(KD - (M0@Lam+Lam@M0)))
    print('Lam K_D Lam = ', np.diag(Lam@KD@Lam))
    # sanity: Wdot formula vs finite difference along rhs
    rng = np.random.default_rng(1)
    d = designs()['good']
    errs = []
    for _ in range(200):
        z = rng.normal(size=4)*0.3; u = rng.normal(size=2)*5
        hh = 1e-6
        fd = (d.W(z + hh*rhs(z, u)) - d.W(z - hh*rhs(z, u)))/(2*hh)
        errs.append(abs(fd - d.Wdot(z, u)))
    print('max |Wdot formula - FD| =', max(errs))
    out = {}
    for key, d in designs().items():
        A, H = quad_D(d)
        ev = np.linalg.eigvalsh(0.5*(A+A.T))
        print(f'\n== {key}: {d.name}')
        print('  Hessian formula vs FD max diff', np.abs(0.5*(A+A.T) - H).max())
        print('  eig of Hessian of D at 0:', ev)
        print('  W positive definite? eig Ke', np.linalg.eigvalsh(d.Ke))
        best, bz = ray_search(d, rmax=RMAX)
        print('  ray search: c* ~', best, ' at z =', bz)
        if bz is not None:
            r = refine(d, bz)
            print('  refined: W =', r.fun, ' D =', d.D(r.x), ' z =', r.x, r.message)
            out[key] = (ev, best, r.fun, r.x)
        else:
            out[key] = (ev, best, None, None)
    np.save('cond_results.npy', out, allow_pickle=True)
