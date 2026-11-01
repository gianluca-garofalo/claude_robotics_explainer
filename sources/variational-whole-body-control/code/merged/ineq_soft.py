"""Strict versus soft priority with an inequality in conflict (merged document, Sec. 13.4); fixed seed, n = 7.

Level 1: inequality J_1 qdd >= a_1 (2 rows).  Level 2: posture task qdd = qdd_des (7 rows), in conflict with level 1.
Lexicographic (strict) solution: min 1/2 |qdd - qdd_des|^2  s.t.  J_1 qdd >= a_1  (the inequality is satisfiable).
Weighted (soft) solution: min 1/2 w |s|^2 + 1/2 |qdd - qdd_des|^2  s.t.  J_1 qdd + s >= a_1  (s penalizes violation).
The weighted solution tends to the lexicographic one as w -> infinity, with an error O(1/w); the multiplier of the
inequality at the level where it is decided is >= 0.  Needs quadprog.
"""
import numpy as np
import quadprog

rng = np.random.default_rng(4)
n = 7
J1 = rng.normal(size=(2, n)); qdd_des = rng.normal(size=n)
a1 = J1 @ qdd_des + np.array([1.0, 0.4])          # both rows violated by the posture task alone

x_lex, _, _, _, mu_lex, _ = quadprog.solve_qp(np.eye(n), qdd_des, J1.T, a1, 0)
print("lexicographic: J_1 qdd - a_1 =", np.round(J1 @ x_lex - a1, 12), "; inequality multipliers (>= 0):", np.round(mu_lex, 4),
      "; posture residual |qdd - qdd_des| =", f"{np.linalg.norm(x_lex - qdd_des):.4f}")
print("   w        |qdd_w - qdd_lex|   w * error    violation max(a_1 - J_1 qdd_w)")
for w in [1.0, 10.0, 100.0, 1e3, 1e4, 1e5]:
    G = np.zeros((n + 2, n + 2)); G[:n, :n] = np.eye(n); G[n:, n:] = w*np.eye(2)
    a = np.concatenate([qdd_des, np.zeros(2)])
    C = np.hstack([J1, np.eye(2)]).T
    x = quadprog.solve_qp(G, a, C, a1, 0)[0][:n]
    err = np.linalg.norm(x - x_lex)
    print(f"   {w:8.0e}   {err:.6e}        {w*err:.4f}      {np.max(a1 - J1 @ x):.3e}")
