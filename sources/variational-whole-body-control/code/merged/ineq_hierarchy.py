"""An inequality task in the middle of a hierarchy: activation and deactivation (merged document, Sec. 13).

Fixed seed, n = 7, random SPD M.  Level 1: equality task (2 rows).  Level 2: inequality J_2 qdd >= a_2(t) (1 row; J_2 = -J2r, i.e. an upper
bound on the task coordinate x_2 = J2r q written as a lower bound on -x_2; the end of the script also runs J_2 = +J2r).
Level 3: equality task (3 rows).  The remaining 2 dof are resolved by Gauss's function.  The stack is feasible, so the
lexicographic (strict-priority) solution is the single QP  min 1/2|qdd - qdd_free|_M^2  s.t. all rows (quadprog).
a_2(t) = c0 + sin(pi t) - 1/2, t in [0, 1], with c0 = J_2 qdd of the solution without level 2: the inequality is
inactive for t < 1/6, active in between, inactive again for t > 5/6.
At every t: active stack in priority order -> block LDL^T (Theta, Lambda_bar), decoupled forces F = Theta^T lambda,
decoupled velocities zeta = Jbar qdot (fixed qdot), per-level powers F_i^T zeta_i, total tau_c^T qdot.
Prints: continuity of tau_c, lambda_2 >= 0 and its values at the switches, the jumps of F and of the per-level powers
at activation and deactivation (levels above the switching level unchanged), and the sign of F_2 versus lambda_2.
"""
import numpy as np
import quadprog

rng = np.random.default_rng(2)
n = 7
X = rng.normal(size=(n, n)); M = X @ X.T + n*np.eye(n); Mi = np.linalg.inv(M)
qdd_free = rng.normal(size=n); qdot = rng.normal(size=n)
J1 = rng.normal(size=(2, n)); a1 = rng.normal(size=2)
J2r = rng.normal(size=(1, n))          # task coordinate x_2 = J2r q; the inequality row is J2 = -J2r (upper bound on x_2)
J2 = -J2r
J3 = rng.normal(size=(3, n)); a3 = rng.normal(size=3)


def block_ldl(G, dims):
    idx = np.cumsum([0] + list(dims)); L = np.eye(G.shape[0]); D = np.zeros_like(G); S = G.copy()
    for i in range(len(dims)):
        a, b = idx[i], idx[i + 1]; D[a:b, a:b] = S[a:b, a:b]; Di = np.linalg.inv(S[a:b, a:b])
        L[b:, a:b] = S[b:, a:b] @ Di
        S[b:, b:] = S[b:, b:] - S[b:, a:b] @ Di @ S[a:b, b:]; S[b:, a:b] = 0; S[a:b, b:] = 0
    return L, D, idx


def solve(a2, with2=True):
    if with2:
        C = np.vstack([J1, J3, J2]).T; b = np.concatenate([a1, a3, [a2]]); meq = 5
    else:
        C = np.vstack([J1, J3]).T; b = np.concatenate([a1, a3]); meq = 5
    x, f, _, _, lam, _ = quadprog.solve_qp(M, M @ qdd_free, C, b, meq)
    l1, l3 = lam[:2], lam[2:5]; l2 = lam[5] if with2 else 0.0
    return x, l1, l2, l3


def attribution(x, l1, l2, l3, active):
    rows = [J1, J2, J3] if active else [J1, J3]; dims = [2, 1, 3] if active else [2, 3]
    lam = np.concatenate([l1, [l2], l3]) if active else np.concatenate([l1, l3])
    Js = np.vstack(rows); Th, D, idx = block_ldl(Js @ Mi @ Js.T, dims)
    F = Th.T @ lam; zeta = np.linalg.solve(Th, Js @ qdot)
    lev = [(F[idx[i]:idx[i+1]], F[idx[i]:idx[i+1]] @ zeta[idx[i]:idx[i+1]]) for i in range(len(dims))]
    return lev, F @ zeta


x0, *_ = solve(0.0, with2=False); c0 = (J2 @ x0)[0]
a2 = lambda t: c0 + np.sin(np.pi*t) - 0.5
# ---- sweep (grid avoids the switching instants 1/6 and 5/6 exactly)
ts = np.linspace(0, 1, 3000); rec = []
for t in ts:
    x, l1, l2, l3 = solve(a2(t)); active = l2 > 0
    lev, Ptot = attribution(x, l1, l2, l3, active)
    rec.append(dict(t=t, tau=M @ (x - qdd_free), l2=l2, active=active, lev=lev, P=Ptot, gap=(J2 @ x)[0] - a2(t),
                    res=max(np.abs(J1 @ x - a1).max(), np.abs(J3 @ x - a3).max())))
act = np.array([r['active'] for r in rec]); sw = np.nonzero(act[1:] != act[:-1])[0]
dtau = np.array([np.abs(rec[i+1]['tau'] - rec[i]['tau']).max() for i in range(len(rec) - 1)])
print(f"feasible stack: max residual of the equality tasks {max(r['res'] for r in rec):.1e}; min lambda_2 {min(r['l2'] for r in rec):.1e} (>= 0);"
      f" min gap J_2 qdd - a_2 {min(r['gap'] for r in rec):.1e} (>= 0); max lambda_2 * gap {max(abs(r['l2']*r['gap']) for r in rec):.1e}")
print(f"active for t in ({ts[sw[0]+1]:.4f}, {ts[sw[1]]:.4f}) (switches at 1/6 and 5/6); max |tau_c(t+dt) - tau_c(t)| over the sweep"
      f" {dtau.max():.2e} (dt = {ts[1]-ts[0]:.1e}); across the two switches {dtau[sw[0]]:.2e}, {dtau[sw[1]]:.2e}")
# ---- exactly at a switching instant: same torque, two attributions (row excluded / included with lambda_2 = 0)
for tstar in (1/6, 5/6):
    x, l1, l2, l3 = solve(a2(tstar))
    off, Poff = attribution(x, l1, 0.0, l3, False); on, Pon = attribution(x, l1, 0.0, l3, True)
    print(f"at t = {tstar:.4f} (lambda_2 = {l2:.1e}, gap = {(J2 @ x)[0] - a2(tstar):.1e}): row 2 excluded -> included")
    print(f"   level 1 (above): F_1 {np.round(off[0][0], 4)} -> {np.round(on[0][0], 4)}, power {off[0][1]:+.4f} -> {on[0][1]:+.4f}")
    print(f"   level 2 (switching): F_2 = {on[1][0][0]:+.4f} with lambda_2 = 0, power {on[1][1]:+.4f}")
    print(f"   level 3 (below, last): F_3 {np.round(off[1][0], 4)} -> {np.round(on[2][0], 4)}, power {off[1][1]:+.4f} -> {on[2][1]:+.4f}")
    print(f"   total power {Poff:+.6f} -> {Pon:+.6f}")
# ---- sign of F_2 versus lambda_2 on the active interval
A = [r for r in rec if r['active']]
F2 = np.array([r['lev'][1][0][0] for r in A]); L2 = np.array([r['l2'] for r in A])
print(f"active interval: lambda_2 in [{L2.min():.4f}, {L2.max():.4f}] (>= 0); decoupled F_2 in [{F2.min():+.4f}, {F2.max():+.4f}];"
      f" fraction with F_2 < 0: {np.mean(F2 < 0):.2f}")

# ---- the same sweep with the row orientation reversed (J_2 = +J2r): only the sign of F_2 relative to lambda_2 changes
J2 = J2r
x0, *_ = solve(0.0, with2=False); c0 = (J2 @ x0)[0]
F2b, L2b = [], []
for t in ts:
    x, l1, l2, l3 = solve(c0 + np.sin(np.pi*t) - 0.5)
    if l2 > 0:
        lev, _ = attribution(x, l1, l2, l3, True); F2b.append(lev[1][0][0]); L2b.append(l2)
F2b, L2b = np.array(F2b), np.array(L2b)
print(f"reversed orientation: lambda_2 in [{L2b.min():.4f}, {L2b.max():.4f}]; decoupled F_2 in [{F2b.min():+.4f}, {F2b.max():+.4f}]")
