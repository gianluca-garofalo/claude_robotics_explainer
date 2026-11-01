import numpy as np, scipy.linalg as sl
np.set_printoptions(precision=3, suppress=True)
rng = np.random.default_rng(0)
n = 7
X = rng.standard_normal((n, n)); M = X @ X.T + n * np.eye(n); Mi = np.linalg.inv(M)

def dc_pinv(J):  # dynamically consistent inverse
    return Mi @ J.T @ np.linalg.pinv(J @ Mi @ J.T)

def ext_jacobians_lit(Js):
    """Literature: Jbar_i = J_i N_{i-1}^T, N^T = I - Jaug# Jaug (Ott/Dietrich/Garofalo)."""
    out = []
    for i, J in enumerate(Js):
        if i == 0: out.append(J.copy()); continue
        Ja = np.vstack(Js[:i]); NT = np.eye(n) - dc_pinv(Ja) @ Ja
        out.append(J @ NT)
    return out

def block_ldl(G, dims, tol=1e-10):
    """block LDL^T, pinv for singular pivots"""
    idx = np.cumsum([0] + dims); r = len(dims); m = idx[-1]
    L = np.eye(m); D = np.zeros((m, m)); S = G.copy()
    for k in range(r):
        a, b = idx[k], idx[k+1]
        Dk = S[a:b, a:b].copy(); D[a:b, a:b] = Dk
        Dkp = np.linalg.pinv(Dk, rcond=tol, hermitian=True)
        L[b:, a:b] = S[b:, a:b] @ Dkp
        S[b:, b:] -= L[b:, a:b] @ Dk @ L[b:, a:b].T
    return L, D

def blocks(Mat, dims):
    idx = np.cumsum([0] + dims); return [Mat[idx[k]:idx[k+1]] for k in range(len(dims))]

# ---------- Case 1: full rank, dims 2,3,2 (sum = 7 = n) ----------
dims = [2, 3, 2]
Js = [rng.standard_normal((d, n)) for d in dims]; A = np.vstack(Js)
L, D = block_ldl(A @ Mi @ A.T, dims)
Jbar = np.linalg.solve(L, A)
lit = ext_jacobians_lit(Js)
print("A1 |L^-1 A - Jbar_lit| per level:", [np.abs(a - b).max() for a, b in zip(blocks(Jbar, dims), lit)])
idx = np.cumsum([0]+dims)
print("A1 |D_i - Jbar_i M^-1 Jbar_i^T|:", [np.abs(D[idx[k]:idx[k+1], idx[k]:idx[k+1]] - lit[k] @ Mi @ lit[k].T).max() for k in range(3)])
print("A1 offdiag of Jbar M^-1 Jbar^T:", np.abs(Jbar @ Mi @ Jbar.T - D).max())
# Gauss stacked: min 1/2|qdd - qdd0|_M s.t. A qdd = b
qdd0 = rng.standard_normal(n); b = rng.standard_normal(n)
K = np.block([[M, A.T], [A, np.zeros((n, n))]])
sol = np.linalg.solve(K, np.concatenate([M @ qdd0, b])); qdd = sol[:n]; lam = -sol[n:]
tau = M @ (qdd - qdd0)  # constraint torque
print("A1 tau - A^T lam:", np.abs(tau - A.T @ lam).max())
F = np.linalg.solve(Jbar.T, tau)
print("A1 F - L^T lam:", np.abs(F - L.T @ lam).max(), "| F_last - lam_last:", np.abs(F[-2:] - lam[-2:]).max(),
      "| F_1 - lam_1:", np.abs(F[:2] - lam[:2]).max())
eff = 0.5 * tau @ Mi @ tau; sep = sum(0.5 * f @ Dk @ f for f, Dk in zip(blocks(F, dims), [D[idx[k]:idx[k+1], idx[k]:idx[k+1]] for k in range(3)]))
print("A1 effort separation residual:", abs(eff - sep))
# order dependence of 'force on task 1': permute order
perm = [Js[1], Js[2], Js[0]]; A2 = np.vstack(perm); d2 = [3, 2, 2]
L2, D2 = block_ldl(A2 @ Mi @ A2.T, d2); Jb2 = np.linalg.solve(L2, A2); F2 = np.linalg.solve(Jb2.T, tau)
print("A1 decoupled force on task1: first-priority", F[:2], " last-priority", F2[-2:], " lam1", lam[:2])
# leak identity J_i^T g = sum_{j<=i} Jbar_j^T L_ij^T g
g = rng.standard_normal(2); Lb = [[L[idx[i]:idx[i+1], idx[j]:idx[j+1]] for j in range(3)] for i in range(3)]
Jbl = blocks(Jbar, dims)
print("A1 leak identity resid:", np.abs(Js[2].T @ g - sum(Jbl[j].T @ Lb[2][j].T @ g for j in range(3))).max())
# one-step rule with R=M^-1: tau* = -dV/dqdot ; F* = -dV/dv with v = Jbar qdot
P = rng.standard_normal((2*n, 2*n)); P = P @ P.T  # random quadratic V(q,qd)=1/2 z^T P z
z = rng.standard_normal(2*n); dVdqd = (P @ z)[n:]
taus = -dVdqd  # argmin 1/2 tau^T M^-1 tau + dVdqd^T M^-1 tau
Fs = np.linalg.solve(Jbar.T, taus); dVdv = np.linalg.solve(Jbar.T, dVdqd)  # chain rule qd = Jbar^-1 v
print("A1 F* + dV/dv:", np.abs(Fs + dVdv).max(), "(quasi-velocity partial at fixed q, no integrability needed)")

# ---------- B: Khatib force ----------
J = Js[0]; Jdqd = rng.standard_normal(2); a = rng.standard_normal(2)
Lam = np.linalg.inv(J @ Mi @ J.T)
K1 = np.block([[M, J.T], [J, np.zeros((2, 2))]])
s1 = np.linalg.solve(K1, np.concatenate([M @ qdd0, a - Jdqd])); q1 = s1[:n]; l1 = -s1[n:]
print("B lam - Lam(a - Jdqd - J qdd0):", np.abs(l1 - Lam @ (a - Jdqd - J @ qdd0)).max())
print("B Gauss value - 1/2|dx|_Lam:", abs(0.5*(q1-qdd0)@M@(q1-qdd0) - 0.5*(a - Jdqd - J@qdd0)@Lam@(a - Jdqd - J@qdd0)))
# CLF-QP min 1/2 tau^T R tau s.t. LfV + LgV tau <= -gam V, LgV = dVdqd^T M^-1
R = np.diag(rng.uniform(0.5, 2, n)); LgV = Mi @ dVdqd; c = 5.0  # pretend LfV+gamV = c > 0
mu = c / (LgV @ np.linalg.solve(R, LgV)); tauc = -mu * np.linalg.solve(R, LgV)
pi_v = -dVdqd
print("B CLF tau - mu R^-1 M^-1 pi_v:", np.abs(tauc - mu * np.linalg.solve(R, Mi @ pi_v)).max())

# ---------- Case 2: rank deficient / conflicting: dims 2,3,3 (sum 8 > 7) and task 2 contains a row of task 1 ----------
J1 = rng.standard_normal((2, n)); J2 = np.vstack([J1[0] + 0*1, rng.standard_normal((2, n))]); J2[0] = J1[0]
J3 = rng.standard_normal((3, n)); Js = [J1, J2, J3]; dims = [2, 3, 3]; A = np.vstack(Js)
L, D = block_ldl(A @ Mi @ A.T, dims); idx = np.cumsum([0]+dims)
Jbar = L @ np.zeros(1) if False else np.linalg.lstsq(L, A, rcond=None)[0]
lit = ext_jacobians_lit(Js)
print("A2 |L^-1A - Jbar_lit| (rank-def):", [np.abs(a - b).max() for a, b in zip(blocks(Jbar, dims), lit)],
      " ranks of Jbar_i:", [np.linalg.matrix_rank(x, 1e-9) for x in lit])
print("A2 eigs D_i:", [np.round(np.linalg.eigvalsh(D[idx[k]:idx[k+1], idx[k]:idx[k+1]]), 4) for k in range(3)])
# lexicographic acc-level problem, residual metric W_i, M-metric regularization at the end
def lexi(Js, bs, Ws, qdd0):
    # nullspace method: x = x0 + Z y
    x = np.zeros(n); Z = np.eye(n)
    for J, bb, W in zip(Js, bs, Ws):
        Wh = sl.sqrtm(W).real; JZ = Wh @ J @ Z
        y = np.linalg.pinv(JZ, rcond=1e-10) @ (Wh @ (bb - J @ x))
        x = x + Z @ y
        Nz = np.eye(Z.shape[1]) - np.linalg.pinv(JZ, rcond=1e-10) @ JZ
        U, s, Vt = np.linalg.svd(Nz); Z = Z @ U[:, s > 0.5]
    # final level: Gauss, min |x - qdd0|_M in remaining nullspace
    if Z.shape[1]:
        y = np.linalg.solve(Z.T @ M @ Z, Z.T @ M @ (qdd0 - x)); x = x + Z @ y
    return x
bs = [rng.standard_normal(d) for d in dims]
xI = lexi(Js, bs, [np.eye(d) for d in dims], qdd0)
LamW = [np.linalg.inv(J @ Mi @ J.T) for J in Js]           # plain task inertia
LamBar = [np.linalg.pinv(D[idx[k]:idx[k+1], idx[k]:idx[k+1]], rcond=1e-10) + 1e-6*np.eye(dims[k]) for k in range(3)]
xL = lexi(Js, bs, LamW, qdd0); xLb = lexi(Js, bs, LamBar, qdd0)
# decoupled controller: v-dot_i via pinv of D_i, F_i = D_i^+ c_i, accumulate
def decoupled(Js, bs, Winv=None):
    x = np.zeros(n); Jbl = blocks(Jbar, dims)
    taus = np.zeros(n); x = qdd0.copy()   # start from free motion; add torques level by level
    # exact: each level corrects its residual using Jbar_i^T F_i, which does not disturb higher levels
    for k, (J, bb) in enumerate(zip(Js, bs)):
        Dk = D[idx[k]:idx[k+1], idx[k]:idx[k+1]]; c = bb - J @ x
        Fk = np.linalg.pinv(Dk, rcond=1e-10) @ c
        x = x + Mi @ Jbl[k].T @ Fk
    return x
xD = decoupled(Js, bs)
for nm, xx in [("lexi W=I", xI), ("lexi W=Lambda_task", xL), ("lexi W=Lambda_bar(reg)", xLb), ("decoupled pinv", xD)]:
    print(f"A2 {nm:24s} task residual norms:", [round(np.linalg.norm(J @ xx - bb), 4) for J, bb in zip(Js, bs)])
print("A2 |decoupled - lexi(W=I)| =", np.abs(xD - xI).max(), " |lexi W=I - W=Lam_task| =", np.abs(xI - xL).max())
