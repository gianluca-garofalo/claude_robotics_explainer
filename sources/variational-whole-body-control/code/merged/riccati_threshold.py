"""Threshold for the scaled boundary term W = (c/2) q^T P q with a rectangle-rule discrete Lagrangian.

Same 3-D random quadratic problem as note/sec10_general_N_descent.py (seed 1, h = 0.1).
Condition (4) with the best one-step reference flow reads T(cP) <= cP, where T is the one-step
Riccati map of the rectangle rule.  Necessary: c >= c* = lambda_max(P^-1 P_d) (T is monotone and
T^k(cP) -> P_d).  The script prints the smallest eigenvalue of cP - T(cP) for c around c*.
"""
import numpy as np, scipy.linalg as sl

rng = np.random.default_rng(1); n = 3; h = 0.1
A = rng.normal(size=(n, n)); Q = A@A.T + np.eye(n); B = rng.normal(size=(n, n)); R = B@B.T + np.eye(n)
P = sl.solve_continuous_are(np.zeros((n, n)), np.eye(n), Q, R); Rh = R/h


def T(X):
    K = np.linalg.solve(Rh + X, Rh); I = np.eye(n)
    return (K - I).T@Rh@(K - I) + K.T@X@K + h*Q


Pd = P.copy()
for _ in range(5000):
    Pd = T(Pd)
cst = np.linalg.eigvals(np.linalg.solve(P, Pd)).real.max()
print("c* = lambda_max(P^-1 P_d) = %.6f" % cst)
for c in [1.0, cst - 1e-3, cst - 1e-6, cst, cst + 1e-6, cst + 1e-3, 1.5, 3.0]:
    ev = np.linalg.eigvalsh(c*P - T(c*P))
    print(f"  c = {c:.6f}: min eig(cP - T(cP)) = {ev.min():+.3e}  ->", "PSD" if ev.min() >= -1e-12 else "not PSD")
