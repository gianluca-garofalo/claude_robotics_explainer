"""Check for Section 11.5 of the note ("Torque limits") and its row in Section 19.1: the torque-limit level
Wbar_tau of the reference law PD+g on the two-link arm, i.e. the least W at which the reference torque (80) reaches
a face tau_i = +-tau_max,i of the box |tau_1| <= 50 N m, |tau_2| <= 30 N m.

Model: M(q), g(q) of the two-link arm (73) with the parameters of Sections 11.1 and 11.4 (l = 0.5, 0.4 m;
m = 2, 1.5 kg; q_d = (pi/4, -pi/4); Gamma = 2 I; K_D = R^-1 = diag(20, 10)); s = v + Gamma e;
W = 1/2 s'M(q)s + 1/2 e'K_e e (77) with K_e = Gamma K_D - Gamma M_0 Gamma; tau = g(q) - K_D s (80).

Prints:
 1. M_0, K_e and g(q_d) (claim: g_2(q_d) = 5.89 N m; W >= 9.4 |e|^2, i.e. lambda_min(K_e)/2 >= 9.4).
 2. The bound at e = 0: v_2 = -(30 - g_2(q_d))/(K_D)_22 (claim -2.41), v_1 = -(M_0)_12 v_2/(M_0)_11 (claim 0.71),
    W = 1/2 [(M_0)_22 - (M_0)_12^2/(M_0)_11] v_2^2 (claim 0.312).
 3. Face by face: on tau_i = +-tau_max,i, s_i is fixed by e and the free s_j is eliminated in closed form, leaving a
    function of e alone; grid on the disk that contains every state with W <= 4, then Nelder-Mead polish.
    Claims: 0.310 on tau_2 = +30 at e = (0.0007, 0.013), v = (0.71, -2.44); 0.682, 0.867, 3.81 on tau_2 = -30,
    tau_1 = +50, tau_1 = -50; margin of Wbar = 0.3 about 3%.
    For each face it also prints whether the other torque is inside its limit at the minimizer, and the least W
    on the face of the box itself (other torque clipped to its limit), which differs from the plane value only
    where the plane minimizer lies outside the box.
 4. Cross-check: multistart SLSQP over z in 4-D on the face tau_2 = +30 (claim: agrees).
 5. Plain ray search, 2e5 random rays per seed, first violation found by bisection, no refinement, 8 seeds
    (claim: returns 0.31-0.37 depending on the seed; always >= Wbar_tau).
Standalone: numpy, scipy. Runs in about one minute.
"""
import numpy as np
from scipy.optimize import minimize

l1, l2, m1, m2, g0 = 0.5, 0.4, 2.0, 1.5, 9.81
qd = np.array([np.pi / 4, -np.pi / 4])
Gam = 2.0 * np.eye(2)
R = np.diag([0.05, 0.1])
KD = np.linalg.inv(R)
KP = KD @ Gam
tmax = np.array([50.0, 30.0])


def Mq(q):
    c2 = np.cos(q[1])
    a = m1 * l1**2 + m2 * (l1**2 + l2**2 + 2 * l1 * l2 * c2)
    b = m2 * (l2**2 + l1 * l2 * c2)
    d = m2 * l2**2
    return np.array([[a, b], [b, d]])


def gq(q):
    c1, c12 = np.cos(q[0]), np.cos(q[0] + q[1])
    return g0 * np.array([(m1 + m2) * l1 * c1 + m2 * l2 * c12, m2 * l2 * c12])


M0 = Mq(qd)
Ke = Gam @ KD - Gam @ M0 @ Gam
print("M0 =", M0.round(4))
print("Ke =", Ke.round(3), "eig", np.linalg.eigvalsh(Ke).round(3))
print("g(qd) =", gq(qd).round(4))


def W(z):
    e, v = z[:2], z[2:]
    s = v + Gam @ e
    return 0.5 * s @ Mq(qd + e) @ s + 0.5 * e @ Ke @ e


def tau(z):
    e, v = z[:2], z[2:]
    s = v + Gam @ e
    return gq(qd + e) - KD @ s


# Closed form at e = 0
g2 = gq(qd)[1]
v2 = -(30 - g2) / KD[1, 1]
schur = M0[1, 1] - M0[0, 1] ** 2 / M0[0, 0]
v1 = -M0[0, 1] / M0[0, 0] * v2
z_e0 = np.array([0, 0, v1, v2])
print("\ne=0 bound: v2=%.5f v1=%.5f schur=%.6f  W=%.6f  tau=%s" % (v2, v1, schur, 0.5 * schur * v2**2, tau(z_e0).round(4)))
print("check W(z_e0) =", W(z_e0))
for k in [1.02, 1.044, 1.08]:
    print("  scaled by", k, ": W=%.4f tau=%s" % (W(k * z_e0), tau(k * z_e0).round(3)))


# Reduced face problem: on face tau_i = sigma*tmax_i, s_i fixed in terms of e; eliminate other s component.
def face_W(e, i, sigma):
    q = qd + e
    M = Mq(q)
    si = (gq(q)[i] - sigma * tmax[i]) / KD[i, i]
    j = 1 - i
    sch = M[i, i] - M[i, j] ** 2 / M[j, j]
    return 0.5 * sch * si**2 + 0.5 * e @ Ke @ e


def face_state(e, i, sigma):
    q = qd + e
    M = Mq(q)
    s = np.zeros(2)
    s[i] = (gq(q)[i] - sigma * tmax[i]) / KD[i, i]
    j = 1 - i
    s[j] = -M[i, j] / M[j, j] * s[i]
    v = s - Gam @ e
    return np.concatenate([e, v])


def boxface_W(e, i, sigma):
    """Least W over s_j on the face of the box: s_j minimizes the convex quadratic in s_j subject to |tau_j| <= tau_max,j."""
    q = qd + e
    M = Mq(q)
    j = 1 - i
    s = np.zeros(2)
    s[i] = (gq(q)[i] - sigma * tmax[i]) / KD[i, i]
    s[j] = -M[i, j] / M[j, j] * s[i]
    tj = np.clip(gq(q)[j] - KD[j, j] * s[j], -tmax[j], tmax[j])
    s[j] = (gq(q)[j] - tj) / KD[j, j]
    return 0.5 * s @ M @ s + 0.5 * e @ Ke @ e


lam_min = np.linalg.eigvalsh(Ke)[0]
rad = np.sqrt(2 * 4.0 / lam_min)  # disk containing every state with W <= 4
print("\nlambda_min(Ke)/2=%.4f (claim >= 9.4);" % (lam_min / 2))
print("lambda_min(Ke)=%.4f; |e| bound for W<=0.312: %.4f; for W<=4: %.4f" % (lam_min, np.sqrt(2 * 0.312 / lam_min), rad))

results = {}
for i in (0, 1):
    for sigma in (+1, -1):
        # grid over the disk
        n = 401
        xs = np.linspace(-rad, rad, n)
        best = (np.inf, None)
        for a in xs:
            for b in xs:
                if a * a + b * b > rad * rad:
                    continue
                e = np.array([a, b])
                val = face_W(e, i, sigma)
                if val < best[0]:
                    best = (val, e)
        res = minimize(lambda e: face_W(e, i, sigma), best[1], method="Nelder-Mead",
                       options=dict(xatol=1e-12, fatol=1e-14, maxiter=20000))
        z = face_state(res.x, i, sigma)
        results[(i, sigma)] = (res.fun, z)
        inside = abs(tau(z)[1 - i]) <= tmax[1 - i]
        print("face tau_%d = %+g: grid %.6f -> polished %.6f at e=%s, v=%s; W(z)=%.6f, tau=%s; other torque inside box: %s"
              % (i + 1, sigma * tmax[i], best[0], res.fun, np.array2string(res.x, precision=6), z[2:].round(4), W(z),
                 tau(z).round(4), inside))
        if not inside:
            bb = (np.inf, None)
            for a in xs:
                for b in xs:
                    if a * a + b * b <= rad * rad:
                        val = boxface_W(np.array([a, b]), i, sigma)
                        if val < bb[0]:
                            bb = (val, np.array([a, b]))
            rb = minimize(lambda e: boxface_W(e, i, sigma), bb[1], method="Nelder-Mead",
                          options=dict(xatol=1e-12, fatol=1e-14, maxiter=20000))
            print("    plane minimizer is outside the box; least W on the face of the box itself: %.6f at e=%s"
                  % (rb.fun, np.array2string(rb.x, precision=5)))

Wtau = min(v[0] for v in results.values())
print("\nWbar_tau = %.6f (claim 0.310); margin of Wbar=0.3: %.2f%% (claim about 3%%)" % (Wtau, 100 * (Wtau - 0.3) / Wtau))

# Cross-check: multistart SLSQP in full 4-D on the face tau_2 = +30
rng = np.random.default_rng(0)
bestfull = np.inf
for k in range(200):
    z0 = rng.normal(size=4) * np.array([0.1, 0.1, 1.5, 1.5])
    cons = [dict(type="eq", fun=lambda z: tau(z)[1] - 30.0)]
    r = minimize(W, z0, method="SLSQP", constraints=cons, options=dict(ftol=1e-14, maxiter=500))
    if r.success and abs(tau(r.x)[1] - 30) < 1e-8 and r.fun < bestfull:
        bestfull, zbest = r.fun, r.x
print("4-D SLSQP on tau_2=+30 face: %.6f at z=%s (claim: agrees with the face reduction)" % (bestfull, np.array2string(zbest, precision=6)))


# 5. Plain ray search without refinement (vectorized): along random directions in z, find the first violation of
#    the box by a coarse scan and bisection, and report the least W among these first violations.
def W_rows(Z):
    e, v = Z[:, :2], Z[:, 2:]
    S_ = v + Gam[0, 0] * e
    c2 = np.cos(qd[1] + e[:, 1])
    a = m1 * l1**2 + m2 * (l1**2 + l2**2 + 2 * l1 * l2 * c2)
    b = m2 * (l2**2 + l1 * l2 * c2)
    d = m2 * l2**2
    return 0.5 * (a * S_[:, 0]**2 + 2 * b * S_[:, 0] * S_[:, 1] + d * S_[:, 1]**2) + 0.5 * np.einsum("ni,ij,nj->n", e, Ke, e)


def viol_rows(Z):
    e, v = Z[:, :2], Z[:, 2:]
    S_ = v + Gam[0, 0] * e
    q1, q2 = qd[0] + e[:, 0], qd[1] + e[:, 1]
    t1 = g0 * ((m1 + m2) * l1 * np.cos(q1) + m2 * l2 * np.cos(q1 + q2)) - KD[0, 0] * S_[:, 0]
    t2 = g0 * m2 * l2 * np.cos(q1 + q2) - KD[1, 1] * S_[:, 1]
    return (np.abs(t1) > tmax[0]) | (np.abs(t2) > tmax[1])


def ray_search(n, seed, rmax=30.0, ncoarse=600, nbis=50):
    rng = np.random.default_rng(seed)
    D = rng.normal(size=(n, 4))
    D /= np.linalg.norm(D, axis=1, keepdims=True)
    found = np.zeros(n, bool)
    lo, hi = np.zeros(n), np.full(n, np.nan)
    for t in np.linspace(0, rmax, ncoarse + 1)[1:]:
        idx = np.where(~found)[0]
        if idx.size == 0:
            break
        vv = viol_rows(t * D[idx])
        hi[idx[vv]] = t
        found[idx[vv]] = True
        lo[idx[~vv]] = t
    a, b, Dk = lo[found], hi[found], D[found]
    for _ in range(nbis):
        mid = 0.5 * (a + b)
        vv = viol_rows(mid[:, None] * Dk)
        b = np.where(vv, mid, b)
        a = np.where(vv, a, mid)
    return W_rows(b[:, None] * Dk).min()


vals = [ray_search(200000, seed) for seed in range(8)]
print("\nray search, 2e5 rays, no refinement, seeds 0-7: min W at first violation =", np.round(vals, 4))
print("range %.4f - %.4f (claim 0.31-0.37); all >= Wbar_tau: %s" % (min(vals), max(vals), all(v >= Wtau for v in vals)))
