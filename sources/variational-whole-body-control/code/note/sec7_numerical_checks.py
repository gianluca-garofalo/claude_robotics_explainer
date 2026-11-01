"""Numerical checks for Section 7 (second-order plants)."""
import json
import numpy as np
from scipy.linalg import solve_continuous_are, solve_discrete_are, expm, schur, null_space
from scipy.integrate import solve_ivp, quad

np.set_printoptions(precision=6, suppress=True)
out = {}
A = np.array([[0., 1.], [0., 0.]]); B = np.array([[0.], [1.]])

def closed_form_P(q1, q2, r):
    p12 = np.sqrt(r*q1); p22 = np.sqrt(r*(q2 + 2*np.sqrt(r*q1))); p11 = p12*p22/r
    return np.array([[p11, p12], [p12, p22]])

def Hfun(z, pi, q1, q2, r):
    return pi[0]*z[1] + pi[1]**2/(2*r) - 0.5*(q1*z[0]**2 + q2*z[1]**2)

for (q1, q2, r) in [(1., 0., 1.), (1., 1., 1.)]:
    tag = f"q1={q1:g},q2={q2:g},r={r:g}"
    Q = np.diag([q1, q2]); R = np.array([[r]])
    P = solve_continuous_are(A, B, Q, R)
    Pc = closed_form_P(q1, q2, r)
    K = (B.T @ P) / r
    Acl = A - B @ K
    Ham = np.block([[A, B @ B.T / r], [Q, -A.T]])
    ev = np.linalg.eigvals(Ham)
    # stable invariant subspace via ordered Schur
    T, Z, sdim = schur(Ham, output='real', sort='lhp')
    U1, U2 = Z[:2, :2], Z[2:, :2]
    Pschur = -U2 @ np.linalg.inv(U1)          # pi = -P z on the stable subspace
    care_res = A.T @ P + P @ A - P @ B @ B.T @ P / r + Q
    # trajectory from z0 = (1, 0)
    z0 = np.array([1., 0.])
    f = lambda t, z: Acl @ z
    lfun = lambda z: 0.5*(q1*z[0]**2 + q2*z[1]**2 + r*(K @ z)[0]**2)
    sol = solve_ivp(f, [0, 40], z0, dense_output=True, rtol=1e-12, atol=1e-14)
    Ival, Ierr = quad(lambda t: lfun(sol.sol(t)), 0, 40, limit=400, epsabs=1e-13)
    V0 = 0.5*z0 @ P @ z0
    rows = []
    maxH = 0; maxVdot = 0; maxOst = 0
    for tt in [0, 0.5, 1, 2, 3, 5]:
        z = sol.sol(tt); pi = -P @ z; u = -(K @ z)[0]
        Vt = 0.5*z @ P @ z
        rem, _ = quad(lambda s: lfun(sol.sol(s)), tt, 40, limit=400, epsabs=1e-13)
        Hval = Hfun(z, pi, q1, q2, r)
        Vdot = (P @ z) @ (Acl @ z)
        # Ostrogradsky: p2 = r qddot, p1 = q2 qdot - r qdddot
        acc = (Acl @ z)[1]; jerk = (Acl @ (Acl @ z))[1]
        p2 = r*acc; p1 = q2*z[1] - r*jerk
        maxH = max(maxH, abs(Hval)); maxVdot = max(maxVdot, abs(Vdot + lfun(z)))
        maxOst = max(maxOst, abs(p1 - pi[0]), abs(p2 - pi[1]))
        rows.append([tt, z[0], z[1], u, pi[0], pi[1], Vt, rem])
    # scaled candidates W = c V: H(z, -c P z) vs (c-1)/2 [c z'PBR^-1B'Pz + z'Qz]
    rng = np.random.default_rng(0)
    scl = []
    for c in [0.5, 1.0, 2.0]:
        errs = []; signs = []
        for _ in range(200):
            z = rng.normal(size=2)
            Hc = Hfun(z, -c*P @ z, q1, q2, r)
            pred = (c - 1)/2*(c*(z @ P @ B @ B.T @ P @ z)/r + z @ Q @ z)
            # direct: Wdot + l under the u selected by W
            uW = -c*(B.T @ P @ z)[0]/r
            Wdot = c*(P @ z) @ (A @ z + B[:, 0]*uW)
            lW = 0.5*(z @ Q @ z + r*uW**2)
            errs.append(max(abs(Hc - pred), abs(Wdot + lW + Hc)))
            signs.append(np.sign(Hc))
        scl.append((c, max(errs), sorted(set(signs))))
    out[tag] = dict(P_scipy=P.tolist(), P_closed=Pc.tolist(), P_schur=Pschur.tolist(),
                    K=K.tolist(), cl_eig=np.linalg.eigvals(Acl).tolist().__repr__(),
                    ham_eig=sorted(ev, key=lambda x: (x.real, x.imag)).__repr__(),
                    care_res=float(np.abs(care_res).max()),
                    closed_vs_scipy=float(np.abs(P - Pc).max()),
                    schur_vs_scipy=float(np.abs(P - Pschur).max()),
                    V0=V0, integral=Ival, integral_minus_V0=Ival - V0,
                    max_abs_H=maxH, max_abs_Vdot_plus_l=maxVdot, max_ostro=maxOst,
                    scaled=scl, rows=rows)
    print("\n=====", tag)
    print("P (scipy):\n", P, "\nP closed form:\n", Pc, "\n|P-Pc|max", np.abs(P - Pc).max(),
          " |P-Pschur|max", np.abs(P - Pschur).max(), " CARE res", np.abs(care_res).max())
    print("K", K, " closed-loop eig", np.linalg.eigvals(Acl), " Ham eig", np.sort_complex(ev))
    print("V(z0)", V0, " int_0^40 l dt", Ival, " diff", Ival - V0)
    print("max|H(z,-gradV)| on traj", maxH, " max|Vdot+l|", maxVdot, " max|Ostro - pi|", maxOst)
    print("scaled candidates (c, max err of formula & identity, signs of H):", scl)
    print(" t     q        v        u        pi_q     pi_v     V        int_t^inf l")
    for rr in rows:
        print(" ".join(f"{x:8.5f}" for x in rr))

# ---------------- discrete multiple shooting KKT ----------------
print("\n===== multiple-shooting KKT (double integrator, q1=q2=r=1)")
q1, q2, r = 1., 1., 1.
Q = np.diag([q1, q2]); R = np.array([[r]])
h = 0.2; Nh = 10
Ad = expm(A*h)
Bd = np.array([[h**2/2], [h]])
Qd, Rd = h*Q, h*R  # rectangle-rule stage cost l_d = h l(z_k,u_k)
Pd = solve_discrete_are(Ad, Bd, Qd, Rd)
Pcare = solve_continuous_are(A, B, Q, R)
def solve_ms(Wmat, z0):
    nz, nu = 2, 1
    # variables: z_1..z_N (2N), u_0..u_{N-1} (N); objective 1/2 x'Gx + g'x ; equality: z_{k+1} - Ad z_k - Bd u_k = 0
    nx = nz*Nh + nu*Nh
    G = np.zeros((nx, nx)); g = np.zeros(nx)
    iz = lambda k: slice(nz*(k-1), nz*k)  # k=1..N
    iu = lambda k: nz*Nh + k              # k=0..N-1
    for k in range(Nh):
        G[iu(k), iu(k)] += Rd[0, 0]
        if k >= 1:
            G[iz(k), iz(k)] += Qd
    G[iz(Nh), iz(Nh)] += Wmat
    const = 0.5*z0 @ Qd @ z0
    C = np.zeros((nz*Nh, nx)); d = np.zeros(nz*Nh)
    for k in range(Nh):
        rows = slice(nz*k, nz*(k+1))
        C[rows, iz(k+1)] = np.eye(nz)        # z_{k+1}
        if k >= 1:
            C[rows, iz(k)] = -Ad             # - Ad z_k
        else:
            d[rows] = Ad @ z0
        C[rows, iu(k)] = -Bd[:, 0]
    # KKT with Lagrangian  J + sum pi_{k+1}.(z_{k+1} - F(z_k,u_k))  -> grad J + C' pi = 0, C x = d
    KKT = np.block([[G, C.T], [C, np.zeros((nz*Nh, nz*Nh))]])
    rhs = np.concatenate([-g, d])
    sol = np.linalg.solve(KKT, rhs)
    x, pi = sol[:nx], sol[nx:].reshape(Nh, nz)   # pi[k] multiplies defect k -> pi_{k+1}
    zs = np.vstack([z0] + [x[iz(k)] for k in range(1, Nh+1)])
    us = np.array([x[iu(k)] for k in range(Nh)])
    J = 0.5*x @ G @ x + const
    return zs, us, pi, J
z0 = np.array([1., 0.])
for name, Wm in [("W = DARE P_d (matching)", Pd), ("W = CARE P (not matching)", Pcare), ("W = 3 P_d", 3*Pd)]:
    zs, us, pi, J = solve_ms(Wm, z0)
    # backward Riccati recursion for V_j = 1/2 z' P_j z, j steps to go
    Pj = [Wm]
    for _ in range(Nh):
        Pn = Pj[-1]
        Kk = np.linalg.solve(Rd + Bd.T @ Pn @ Bd, Bd.T @ Pn @ Ad)
        Pj.append(Qd + Ad.T @ Pn @ Ad - Ad.T @ Pn @ Bd @ Kk)
    # pi_{k} for k=1..N should equal -P_{N-k} z_k
    err = max(np.abs(pi[k-1] + Pj[Nh-k] @ zs[k]).max() for k in range(1, Nh+1))
    trans = np.abs(pi[Nh-1] + Wm @ zs[Nh]).max()
    # costate recursion pi_k = Ad' pi_{k+1} - Qd z_k, k=1..N-1 ; stationarity Rd u_k = Bd' pi_{k+1}
    rec = max(np.abs(pi[k-1] - (Ad.T @ pi[k] - Qd @ zs[k])).max() for k in range(1, Nh))
    stat = max(abs(Rd[0, 0]*us[k] - Bd[:, 0] @ pi[k]) for k in range(Nh))
    pi0 = Ad.T @ pi[0] - Qd @ zs[0]
    v0err = abs(J - 0.5*z0 @ Pj[Nh] @ z0)
    grad0 = np.abs(pi0 + Pj[Nh] @ z0).max()
    print(f"{name}: max|pi_k + P_(N-k) z_k| = {err:.2e}, |pi_N + grad W| = {trans:.2e}, "
          f"recursion res = {rec:.2e}, stationarity res = {stat:.2e}, |J - V_N(z0)| = {v0err:.2e}, |pi_0 + grad V_N(z0)| = {grad0:.2e}")
    out['ms_' + name] = dict(err=err, trans=trans, rec=rec, stat=stat, J_minus_V=v0err, grad0=grad0)
print("P_d (h=0.2):\n", Pd, "\nP_care:\n", Pcare)
out['Pd'] = Pd.tolist()

# ------------- exact discrete Lagrangian on state pairs, discrete Legendre transforms ------------
print("\n===== exact discrete Lagrangian L_d^E(z,z') (continuous u on [0,h]), q1=q2=r=1, h=0.2")
Ham = np.block([[A, B @ B.T / r], [Q, -A.T]])
Phi = expm(Ham*h)
P11, P12, P21, P22 = Phi[:2, :2], Phi[:2, 2:], Phi[2:, :2], Phi[2:, 2:]
def endpoint_momenta(z, zp):
    pi0 = np.linalg.solve(P12, zp - P11 @ z)
    pih = P21 @ z + P22 @ pi0
    return pi0, pih
def Ld_quad(z, zp):  # direct quadrature of the action of the extremal
    pi0, _ = endpoint_momenta(z, zp)
    g = lambda t: expm(Ham*t) @ np.concatenate([z, pi0])
    def lt(t):
        w = g(t); zz, pp = w[:2], w[2:]
        u = pp[1]/r
        return 0.5*(zz @ Q @ zz + r*u*u)
    return quad(lt, 0, h, epsabs=1e-14, epsrel=1e-13)[0]
z = np.array([0.7, -0.3]); zp = np.array([0.6, -0.5])
pi0, pih = endpoint_momenta(z, zp)
Ld = Ld_quad(z, zp)
eps = 1e-6
D1 = np.array([(Ld_quad(z + eps*e, zp) - Ld_quad(z - eps*e, zp))/(2*eps) for e in np.eye(2)])
D2 = np.array([(Ld_quad(z, zp + eps*e) - Ld_quad(z, zp - eps*e))/(2*eps) for e in np.eye(2)])
print("pi(0) =", pi0, " -D1 L_d =", -D1, "  err", np.abs(pi0 + D1).max())
print("pi(h) =", pih, "  D2 L_d =", D2, "  err", np.abs(pih - D2).max())
print("Euler identity L_d = 1/2(pi_h.z' - pi_0.z):", Ld, 0.5*(pih @ zp - pi0 @ z), " diff", Ld - 0.5*(pih @ zp - pi0 @ z))
out['LdE'] = dict(err_D1=float(np.abs(pi0 + D1).max()), err_D2=float(np.abs(pih - D2).max()))
# one-step exactness with W = CARE: V_1(z) = min_z' L_d^E(z,z') + W(z') equals W(z), z' = e^{Acl h} z
P = Pcare
Kc = B.T @ P / r
zstar = expm((A - B @ Kc)*h) @ z
from scipy.optimize import minimize
res = minimize(lambda zp_: Ld_quad(z, zp_) + 0.5*zp_ @ P @ zp_, zstar + 0.05, method='BFGS', options=dict(gtol=1e-11))
print("one-step exact: argmin", res.x, " e^{Acl h} z", zstar, " V1 - W(z):", res.fun - 0.5*z @ P @ z)
_, pih_star = endpoint_momenta(z, zstar)
print("transversality at z': pi(h) + P z' =", pih_star + P @ zstar)
out['onestep'] = dict(argmin_err=float(np.abs(res.x - zstar).max()), V1_minus_W=float(res.fun - 0.5*z @ P @ z),
                      trans=float(np.abs(pih_star + P @ zstar).max()))
# one-step reachable set with piecewise-constant u is a line: rank of [Bd] is 1 < 2
print("ZOH one-step: z' - Ad z ranges over span(Bd), dim =", np.linalg.matrix_rank(Bd), "< 2 = dim z")

# ---------------- manipulator torque law ----------------
print("\n===== manipulator: H's torque maximiser")
rng = np.random.default_rng(1)
n = 2
Mh = rng.normal(size=(n, n)); M = Mh @ Mh.T + n*np.eye(n)
hvec = rng.normal(size=n); piv = rng.normal(size=n)
Minv = np.linalg.inv(M)
for name, Rm in [("R = I", np.eye(n)), ("R = M^-1 (Gauss)", Minv)]:
    obj = lambda tau: piv @ (Minv @ (tau - hvec)) - 0.5*tau @ Rm @ tau
    tau_formula = np.linalg.solve(Rm, Minv @ piv)
    res = minimize(lambda t_: -obj(t_), np.zeros(n), method='BFGS', options=dict(gtol=1e-12))
    sup_formula = 0.5*piv @ Minv @ np.linalg.solve(Rm, Minv @ piv) - piv @ Minv @ hvec
    print(f"{name}: tau* formula {tau_formula}, numeric {res.x}, err {np.abs(tau_formula - res.x).max():.1e};"
          f" sup formula {sup_formula:.10f} numeric {-res.fun:.10f}")
    out['manip_' + name] = float(np.abs(tau_formula - res.x).max())
# Gauss: 1/2 tau' M^-1 tau == 1/2 (qdd - a_free)' M (qdd - a_free) with a_free = -M^-1 h
tau = rng.normal(size=n); qdd = Minv @ (tau - hvec); afree = -Minv @ hvec
print("Gauss identity residual:", 0.5*tau @ Minv @ tau - 0.5*(qdd - afree) @ M @ (qdd - afree))

json.dump(out, open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)), 'num_results.json'), 'w'), indent=1, default=str)
