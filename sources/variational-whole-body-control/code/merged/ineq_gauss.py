"""Unilateral constraints in Gauss's principle (merged document, Sec. 8.4); fixed seed, n = 7.

min 1/2 (qdd - qdd_free)^T M (qdd - qdd_free)  s.t.  J_E qdd = a_E (equality task),  J_I qdd >= a_I (three unilateral rows)
(1) KKT: M (qdd - qdd_free) = J^T lambda, lambda_I >= 0, J_I qdd >= a_I, lambda_I (J_I qdd - a_I) = 0 (complementarity).
(2) Fourier's inequality (unilateral d'Alembert): tau_c^T (qdd' - qdd) >= 0 for every admissible acceleration qdd'.
(3) Power of the unilateral forces lambda_i * xdot_i with xdot_i = J_i qdot:
    persistent contact (xdot_i = 0): zero; feedback-bounded inequality task moving away from its bound while active
    (xdot_i > 0, lambda_i > 0): positive, i.e. the force injects energy although it can only push.
Needs quadprog.
"""
import numpy as np
import quadprog

rng = np.random.default_rng(5)
n = 7
X = rng.normal(size=(n, n)); M = X @ X.T + n*np.eye(n)
qdd_free = rng.normal(size=n)
JE = rng.normal(size=(2, n)); aE = rng.normal(size=2)
JI = rng.normal(size=(3, n))


def gauss(JE, aE, JI, aI):
    C = np.vstack([JE, JI]).T; b = np.concatenate([aE, aI])
    x, f, _, _, lam, act = quadprog.solve_qp(M, M @ qdd_free, C, b, len(aE))
    return x, lam


# bounds: rows 1 and 3 would be violated by the equality-only solution, row 2 is not
x0, _ = gauss(JE, aE, np.zeros((0, n)), np.zeros(0))
aI = JI @ x0 + np.array([0.5, -0.5, 0.3])
qdd, lam = gauss(JE, aE, JI, aI)
tau_c = M @ (qdd - qdd_free); lamI = lam[2:]; gapI = JI @ qdd - aI
J = np.vstack([JE, JI])
print("(1) stationarity |M(qdd - qdd_free) - J^T lambda| =", f"{np.abs(tau_c - J.T @ lam).max():.1e}")
print("    lambda_I =", np.round(lamI, 4), " J_I qdd - a_I =", np.round(gapI, 4),
      " complementarity max|lambda_i gap_i| =", f"{np.abs(lamI*gapI).max():.1e}")
# (2) Fourier's inequality on random admissible accelerations
NE = np.linalg.svd(JE)[2][2:].T                       # null space of J_E
worst = np.inf; cnt = 0
for _ in range(20000):
    q2 = qdd + NE @ rng.normal(scale=2.0, size=n - 2)
    if np.all(JI @ q2 >= aI):
        cnt += 1; worst = min(worst, tau_c @ (q2 - qdd))
print(f"(2) Fourier's inequality on {cnt} admissible accelerations: min tau_c^T (qdd' - qdd) = {worst:.3e} (>= 0)")
# (3) power: velocities with xdot_1 = 0 (persistent contact on row 1) and xdot_3 = +0.5 (row 3 moving away)
A = np.vstack([JI[0], JI[2]]); qdot = np.linalg.lstsq(A, np.array([0.0, 0.5]), rcond=None)[0]
qdot = qdot + (np.eye(n) - np.linalg.pinv(A) @ A) @ rng.normal(size=n)
xdot = JI @ qdot
print(f"(3) xdot_I = {np.round(xdot, 4)}; powers lambda_i xdot_i = {np.round(lamI*xdot, 4)}"
      f"  (row 1: persistent contact, zero; row 3: active and receding, positive; row 2: inactive, zero)")
print(f"    total unilateral power {lamI @ xdot:.4f}; total constraint power tau_c^T qdot = {tau_c @ qdot:.4f}"
      f" = lambda^T J qdot = {lam @ (J @ qdot):.4f}")
