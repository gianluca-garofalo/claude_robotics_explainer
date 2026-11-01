import numpy as np
exec(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'redteam_check_A_B.py')).read().split('# ---------- Case 1')[0])
rng = np.random.default_rng(1)
# order (in)dependence: feasible stacked tasks -> lexicographic acc-level solution is order independent;
# compliance law tau = sum Jbar_i^T F_i(x_i, xdot_i) is not.
dims = [2, 3, 2]; Js = [rng.standard_normal((d, n)) for d in dims]
qd = rng.standard_normal(n); xt = [rng.standard_normal(d) for d in dims]
def compliance_qdd(order):
    J_o = [Js[k] for k in order]; Jb = ext_jacobians_lit(J_o); tau = np.zeros(n)
    for k, Jbk in zip(order, Jb):
        F = -10 * xt[k] - 2 * Js[k] @ qd          # physical stiffness/damping, no inertia shaping
        tau += Jbk.T @ F
    return Mi @ tau
print("compliance: |qdd(order 123) - qdd(order 312)| =", np.abs(compliance_qdd([0,1,2]) - compliance_qdd([2,0,1])).max())
def stacked_qdd(order, bs):
    A = np.vstack([Js[k] for k in order]); b = np.concatenate([bs[k] for k in order])
    return np.linalg.solve(A, b)
bs = [rng.standard_normal(d) for d in dims]
print("acc-level feasible: |qdd(123)-qdd(312)| =", np.abs(stacked_qdd([0,1,2], bs) - stacked_qdd([2,0,1], bs)).max())

# inequality at top: J1 qdd <= b1 (1 row), then equality tasks of dims 3, 3; Gauss in M metric
J1 = rng.standard_normal((1, n)); J2 = rng.standard_normal((3, n)); J3 = rng.standard_normal((3, n))
qdd0 = rng.standard_normal(n); b2 = rng.standard_normal(3); b3 = rng.standard_normal(3)
def solve(b1):
    # unconstrained (inactive) solution of eq tasks 2,3 (dims 6 < 7, Gauss picks last dof)
    def gauss(A, b):
        K = np.block([[M, A.T], [A, np.zeros((len(b), len(b)))]])
        s = np.linalg.solve(K, np.concatenate([M @ qdd0, b])); return s[:n], -s[n:]
    x, lam = gauss(np.vstack([J2, J3]), np.concatenate([b2, b3]))
    if (J1 @ x)[0] <= b1:
        A = np.vstack([J2, J3]); dms = [3, 3]; active = False
    else:
        A = np.vstack([J1, J2, J3]); dms = [1, 3, 3]; active = True
        x, lam = gauss(A, np.concatenate([[b1], b2, b3]))
    L, D = block_ldl(A @ Mi @ A.T, dms); Jb = np.linalg.solve(L, A) if A.shape[0] == n else np.linalg.lstsq(L, A, rcond=None)[0]
    tau = A.T @ lam; F = L.T @ lam
    F2 = F[:3] if not active else F[1:4]
    return x, tau, F2, active, lam
xi = solve(1e6)[0]; bc = (J1 @ xi)[0]
for b1 in [bc + 1e-6, bc - 1e-6]:
    x, tau, F2, act, lam = solve(b1)
    print(f"b1=bc{b1-bc:+.0e} active={act} tau[:3]={tau[:3]} F_task2={F2} lam1={lam[0] if act else 0:.2e}")
