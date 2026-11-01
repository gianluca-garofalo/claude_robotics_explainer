"""Numerical checks for the whole-body-control companion document.

Every number quoted in the companion is printed by this script (fixed seed).
Notation follows the document: M inertia, J_i task Jacobians stacked in priority
order as A, Lambda task inertia, L D L^T block factorization of A M^-1 A^T,
Jbar = L^-1 A extended (null-space) Jacobians, F decoupled task forces,
lambda stacked Gauss multipliers.
"""
import numpy as np

np.set_printoptions(precision=4, suppress=True)
rng = np.random.default_rng(7)


def spd(n, scale=1.0):
    X = rng.normal(size=(n, n))
    return scale * (X @ X.T) + n * np.eye(n)


def block_ldl(G, dims):
    """Block LDL^T of an SPD matrix G with block sizes dims (L unit lower)."""
    idx = np.cumsum([0] + list(dims))
    r = len(dims)
    L = np.eye(G.shape[0])
    D = np.zeros_like(G)
    S = G.copy()
    for i in range(r):
        a, b = idx[i], idx[i + 1]
        D[a:b, a:b] = S[a:b, a:b]
        Dinv = np.linalg.inv(S[a:b, a:b])
        for j in range(i + 1, r):
            c, d = idx[j], idx[j + 1]
            L[c:d, a:b] = S[c:d, a:b] @ Dinv
        # Schur complement update of the trailing block
        S[b:, b:] = S[b:, b:] - S[b:, a:b] @ Dinv @ S[a:b, b:]
        S[b:, a:b] = 0
        S[a:b, b:] = 0
    return L, D, idx


def dyn_consistent_extended(Js, Minv):
    """Literature definition: Jbar_i = J_i (I - A_<i^{M+} A_<i), A_<i = stacked higher tasks."""
    n = Minv.shape[0]
    out = []
    for i, Ji in enumerate(Js):
        if i == 0:
            out.append(Ji.copy())
            continue
        Aa = np.vstack(Js[:i])
        Apinv = Minv @ Aa.T @ np.linalg.inv(Aa @ Minv @ Aa.T)  # M-weighted pseudo-inverse
        out.append(Ji @ (np.eye(n) - Apinv @ Aa))
    return out


def header(s):
    print("\n" + "=" * 70 + "\n" + s + "\n" + "=" * 70)


n = 7
dims = [2, 3, 2]                      # sum = n: square stack (inertial decoupling exact)
M = spd(n)
Minv = np.linalg.inv(M)
Js = [rng.normal(size=(d, n)) for d in dims]
A = np.vstack(Js)
qd = rng.normal(size=n)

# ---------------------------------------------------------------- 1. Gauss = OSC
header("1. Gauss's principle with a task constraint = operational-space control")
J = Js[0]
Lam = np.linalg.inv(J @ Minv @ J.T)
qdd0 = rng.normal(size=n)             # free (unconstrained) acceleration M^-1 (tau0 - b)
a = rng.normal(size=dims[0])          # imposed task acceleration (minus Jdot qdot)
# KKT of min 1/2 |qdd - qdd0|_M^2  s.t.  J qdd = a
K = np.block([[M, -J.T], [J, np.zeros((dims[0], dims[0]))]])
sol = np.linalg.solve(K, np.concatenate([M @ qdd0, a]))
qdd, lam = sol[:n], sol[n:]
lam_khatib = Lam @ (a - J @ qdd0)
print("|lambda_KKT - Lambda (a - J qdd0)| =", np.abs(lam - lam_khatib).max())
gauss = 0.5 * (qdd - qdd0) @ M @ (qdd - qdd0)
print("Gauss value              =", gauss)
print("1/2 |a - J qdd0|^2_Lambda =", 0.5 * (a - J @ qdd0) @ Lam @ (a - J @ qdd0))
print("1/2 tau_c^T M^-1 tau_c    =", 0.5 * (J.T @ lam) @ Minv @ (J.T @ lam))
# impressed force keeps the natural inertia: xdd - xdd0 = Lambda^-1 F
F_imp = rng.normal(size=dims[0])
xdd_shift = J @ (Minv @ (J.T @ F_imp))
print("impressed: |J M^-1 J^T F - Lambda^-1 F| =", np.abs(xdd_shift - np.linalg.solve(Lam, F_imp)).max())

# ---------------------------------------------------------------- 2. LDL^T = Gram-Schmidt
header("2. Hierarchy as block Gram-Schmidt in the M^-1 metric")
G = A @ Minv @ A.T
L, D, idx = block_ldl(G, dims)
print("|G - L D L^T| =", np.abs(G - L @ D @ L.T).max())
Jbar = np.linalg.solve(L, A)
Jbar_lit = np.vstack(dyn_consistent_extended(Js, Minv))
print("|L^-1 A - Jbar (dynamically consistent, literature)| =", np.abs(Jbar - Jbar_lit).max())
Gb = Jbar @ Minv @ Jbar.T
off = Gb.copy()
for i in range(len(dims)):
    off[idx[i]:idx[i + 1], idx[i]:idx[i + 1]] = 0
print("off-diagonal blocks of Jbar M^-1 Jbar^T:", np.abs(off).max())
v = Jbar @ qd
xd = A @ qd
print("|xdot - L v| =", np.abs(xd - L @ v).max())
T_kin = 0.5 * qd @ M @ qd
T_dec = sum(0.5 * v[idx[i]:idx[i + 1]] @ np.linalg.inv(D[idx[i]:idx[i + 1], idx[i]:idx[i + 1]]) @ v[idx[i]:idx[i + 1]]
            for i in range(len(dims)))
print("kinetic energy 1/2 qd^T M qd =", T_kin, "  sum 1/2 v_i^T Lambdabar_i v_i =", T_dec)

# ---------------------------------------------------------------- 3. duals and forces
header("3. Stacked multipliers vs decoupled task forces: F = L^T lambda")
lam_s = rng.normal(size=sum(dims))   # multipliers of the stacked task constraints
tau_c = A.T @ lam_s
F = L.T @ lam_s
print("|tau_c - Jbar^T F| =", np.abs(tau_c - Jbar.T @ F).max())
eff = 0.5 * tau_c @ Minv @ tau_c
eff_dec = sum(0.5 * F[idx[i]:idx[i + 1]] @ D[idx[i]:idx[i + 1], idx[i]:idx[i + 1]] @ F[idx[i]:idx[i + 1]]
              for i in range(len(dims)))
print("Gauss effort 1/2 tau^T M^-1 tau =", eff, "  sum 1/2 F_i^T Lambdabar_i^-1 F_i =", eff_dec)
print("last level: |F_r - lambda_r| =", np.abs(F[idx[-2]:] - lam_s[idx[-2]:]).max())
# Same torque, priority order reversed: the force attributed to task 1 changes
order = [2, 1, 0]
A_rev = np.vstack([Js[k] for k in order])
dims_rev = [dims[k] for k in order]
L_rev, D_rev, idx_rev = block_ldl(A_rev @ Minv @ A_rev.T, dims_rev)
lam_rev = np.concatenate([lam_s[idx[k]:idx[k + 1]] for k in order])
F_rev = L_rev.T @ lam_rev
print("task 1 force, task 1 first :", F[idx[0]:idx[1]])
print("task 1 force, task 1 last  :", F_rev[idx_rev[2]:idx_rev[3]], " (= its multiplier", lam_s[idx[0]:idx[1]], ")")

# ---------------------------------------------------------------- 4. power
header("4. Power: total invariant, per-level not")
P_tot_dec = F @ v
P_tot_task = lam_s @ xd
print("F^T v =", P_tot_dec, "  lambda^T xdot =", P_tot_task, "  tau_c^T qdot =", tau_c @ qd)
per = [F[idx[i]:idx[i + 1]] @ v[idx[i]:idx[i + 1]] for i in range(len(dims))]
v_rev = np.linalg.solve(L_rev, A_rev) @ qd
per_rev = [F_rev[idx_rev[i]:idx_rev[i + 1]] @ v_rev[idx_rev[i]:idx_rev[i + 1]] for i in range(len(dims))]
print("per-level power, order (1,2,3):", np.round(per, 4))
print("per-level power, order (3,2,1):", np.round(per_rev, 4), " (listed as tasks 3,2,1)")
print("totals:", sum(per), sum(per_rev))

# ---------------------------------------------------------------- 5. leak identity
header("5. Leak: a force on task i written with J_i^T spreads over levels j <= i")
i = 2
f = rng.normal(size=dims[i])
lhs = Js[i].T @ f
rhs = sum(Jbar[idx[j]:idx[j + 1]].T @ (L[idx[i]:idx[i + 1], idx[j]:idx[j + 1]].T @ f) for j in range(i + 1))
print("|J_3^T f - sum_j Jbar_j^T L_3j^T f| =", np.abs(lhs - rhs).max())
print("components on levels 1,2,3:",
      [float(np.linalg.norm(L[idx[i]:idx[i + 1], idx[j]:idx[j + 1]].T @ f)) for j in range(i + 1)])

# ---------------------------------------------------------------- 6. energy-type W: damping only
header("6. One-step rule with an energy-type boundary term gives damping only")
# W = 1/2 qd^T M qd + U(q);  Wdot = qd^T (tau - g + grad U)  (skew-symmetry of Mdot - 2C)
R = spd(n, 0.1)
tau_ff = rng.normal(size=n)
# minimize 1/2 (tau - tau_ff)^T R (tau - tau_ff) + qd^T tau  over tau
tau_star = tau_ff - np.linalg.solve(R, qd)
grad = R @ (tau_star - tau_ff) + qd
print("stationarity residual:", np.abs(grad).max(), " -> tau* = tau_ff - R^-1 qdot (no position feedback beyond tau_ff)")

# ---------------------------------------------------------------- 7. active-set switch
header("7. An inequality task becoming active on top: same torque, new attribution")
n2 = 7
J0 = rng.normal(size=(1, n2))          # inequality task (active from now on), highest priority
J1 = rng.normal(size=(2, n2))
J2 = rng.normal(size=(3, n2))
before = [J1, J2]; after = [J0, J1, J2]
lam12 = rng.normal(size=5)
A_b = np.vstack(before); A_a = np.vstack(after)
lam_after = np.concatenate([[0.0], lam12])   # inequality multiplier is zero at activation
print("torque continuous: |A_b^T lam - A_a^T [0, lam]| =", np.abs(A_b.T @ lam12 - A_a.T @ lam_after).max())
Lb, Db, ib = block_ldl(A_b @ Minv @ A_b.T, [2, 3])
La, Da, ia = block_ldl(A_a @ Minv @ A_a.T, [1, 2, 3])
Fb = Lb.T @ lam12; Fa = La.T @ lam_after
vb = np.linalg.solve(Lb, A_b) @ qd; va = np.linalg.solve(La, A_a) @ qd
print("F_task1 before:", Fb[0:2], "  after:", Fa[1:3])
print("F_task2 before:", Fb[2:5], "  after:", Fa[3:6], " (last level: unchanged)")
print("F_ineq after  :", Fa[0:1], " (nonzero although its multiplier is zero)")
pb = [Fb[0:2] @ vb[0:2], Fb[2:5] @ vb[2:5]]
pa = [Fa[0:1] @ va[0:1], Fa[1:3] @ va[1:3], Fa[3:6] @ va[3:6]]
print("per-level power before (task1, task2):", np.round(pb, 4), " total", round(sum(pb), 6))
print("per-level power after (ineq, task1, task2):", np.round(pa, 4), " total", round(sum(pa), 6))
