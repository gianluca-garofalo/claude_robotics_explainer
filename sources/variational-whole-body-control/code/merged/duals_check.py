"""Duals as physical quantities: unit bookkeeping and basis (coordinate) dependence.

(1) Gauss's principle in power units.  With the stage cost l = (T0/2) tau_c^T M^-1 tau_c
    (a power) and the task constraint J M^-1 tau_c = a_x - J qdd_free, the multiplier is
    T0 * lambda, where lambda = Lambda (a_x - J qdd_free) is the operational-space force:
    a momentum (impulse), exactly as the velocity momentum pi_v in tau* = pi_v / T0.
(2) Momenta are covectors.  For the two-link arm boundary term W = 1/2 s^T M s + 1/2 e^T K_e e,
    the multipliers in the coordinates (e, v) and (e, s), s = v + Gamma e, satisfy
    pi_v = pi~_s and pi_q = pi~_e + Gamma^T pi~_s (finite differences), and the pairing with the
    velocities, pi . zdot = pi~ . (edot, sdot) = -Wdot, does not depend on the coordinates.
"""
import os, sys
import numpy as np
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'note', 'sec8_arm'))
from model import Mmat, Cmat, qd, rhs          # noqa: E402
from condcheck import designs                  # noqa: E402

rng = np.random.default_rng(11)

# ---------------------------------------------------------------- (1) units
n, m, T0 = 7, 2, 0.05
X = rng.normal(size=(n, n)); M = X @ X.T + n*np.eye(n); Mi = np.linalg.inv(M)
J = rng.normal(size=(m, n)); Lam = np.linalg.inv(J @ Mi @ J.T)
qdd_free = rng.normal(size=n); a_x = rng.normal(size=m)
lam = Lam @ (a_x - J @ qdd_free)
# KKT of  min (T0/2) tau^T M^-1 tau  s.t.  J M^-1 tau = a_x - J qdd_free
K = np.block([[T0*Mi, -(J @ Mi).T], [J @ Mi, np.zeros((m, m))]])
sol = np.linalg.solve(K, np.concatenate([np.zeros(n), a_x - J @ qdd_free]))
tau, mu = sol[:n], sol[n:]
print("(1) |mu - T0*lambda| =", np.abs(mu - T0*lam).max(),
      " |tau - J^T lambda| =", np.abs(tau - J.T @ lam).max())

# ---------------------------------------------------------------- (2) covectors
d = designs()['good']; G = d.Lam


def W_ev(e, v):
    return float(d.W(np.concatenate([e, v])))


def W_es(e, s):
    return W_ev(e, s - G @ e)


def grad(f, x, y, eps=1e-6):
    gx = np.array([(f(x + eps*ei, y) - f(x - eps*ei, y))/(2*eps) for ei in np.eye(2)])
    gy = np.array([(f(x, y + eps*ei) - f(x, y - eps*ei))/(2*eps) for ei in np.eye(2)])
    return gx, gy


worst = 0.0; worst_pair = 0.0
for _ in range(200):
    e = rng.normal(scale=0.5, size=2); v = rng.normal(size=2); u = rng.normal(scale=5, size=2)
    s = v + G @ e
    gq, gv = grad(W_ev, e, v); pi_q, pi_v = -gq, -gv            # coordinates (e, v)
    ge, gs = grad(W_es, e, s); pt_e, pt_s = -ge, -gs            # coordinates (e, s)
    worst = max(worst, np.abs(pi_v - pt_s).max(), np.abs(pi_q - (pt_e + G.T @ pt_s)).max())
    zdot = rhs(np.concatenate([e, v]), u); edot, vdot = zdot[:2], zdot[2:]
    sdot = vdot + G @ edot
    Wdot = float(d.Wdot(np.concatenate([e, v]), u))
    worst_pair = max(worst_pair, abs(pi_q @ edot + pi_v @ vdot + Wdot),
                     abs(pt_e @ edot + pt_s @ sdot + Wdot))
print("(2) max |pi_v - pi~_s|, |pi_q - (pi~_e + Gamma^T pi~_s)| over 200 states =", f"{worst:.1e}")
print("    max |pi . zdot + Wdot| in both coordinate systems =", f"{worst_pair:.1e}")
e = np.array([0.2, -0.1]); v = np.zeros(2); s = v + G @ e
gq, gv = grad(W_ev, e, v); ge, gs = grad(W_es, e, s)
print("    example at rest, e = (0.2, -0.1): pi_q =", np.round(-gq, 3), " pi~_e =", np.round(-ge, 3),
      " pi_v = pi~_s =", np.round(-gv, 3))
