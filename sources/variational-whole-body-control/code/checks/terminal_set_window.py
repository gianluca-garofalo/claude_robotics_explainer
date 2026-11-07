"""Check for the terminal-region statements of Sections 5.2 and 6.3 of the note (with Section 4.6): with a terminal
interval Omega = [-r, r] the window value equals the boundary term only where the path of the rule ends in Omega.

Hilltop with m = kappa = 1 (omega = 1, V(q) = 1/2 sqrt(m kappa) q^2 = 1/2 q^2), boundary term W = V (c = 1),
terminal interval Omega = [-1/2, 1/2].

Part A, Section 5.2, bullet "c = 1" (window theta = 0.1). Prints:
  - the threshold r e^{omega theta} and V_theta - V just inside and just outside it
    (claim: V_theta = V exactly for |q| <= r e^{omega theta}, V_theta > V farther out, endpoint pushed to +-r);
  - V_theta(1) = L_d^E(1, r) + V(r), with L_d^E the closed form (33) at h = theta (the action of the extremal from
    q = 1 to r), checked against bounded minimization over the endpoint and against quadrature of the action
    along the extremal (claim: V_theta(1) = 1.404 against V(1) = 0.5);
  - the first move p/m = -d_1 L_d^E(1, r)/m by (32), checked against m qdot(0) of the extremal
    (claim: -5.04 against the rule's -omega q = -1).

Part B, Section 6.3, example after "With a terminal region": exact discrete Lagrangian L_d^E (33), h = 0.1,
its fixed point W = 1/2 q^2, Omega = [-1/2, 1/2]. Prints:
  - max |B W - W| on a grid of q (claim: W is a fixed point of the Bellman operator, B W = W);
  - V_N(1) for N = 1..9, computed exactly as the convex quadratic program over the chain q_1..q_N with the
    terminal bound |q_N| <= r (KKT multiplier printed), cross-checked by the principle of optimality against
    the continuous window of length N h, and the endpoint e^{-N h} of the chain of minimizing steps of B W
    (claim: V_1(1) = 1.404; V_N(1) = W(1) = 0.5 only from N = 7, the first N with e^{-N h} <= 1/2).

Standalone: numpy, scipy. Runs in about a second.
"""
import numpy as np
from scipy.integrate import quad
from scipy.optimize import minimize_scalar

m = kappa = 1.0
omega = np.sqrt(kappa / m)
Pc = np.sqrt(m * kappa)
r = 0.5
V = lambda q: 0.5 * Pc * q * q                       # V = V_infty, here also the boundary term W (c = 1)


def LdE(q, qp, h):                                   # (33): exact action of the extremal from q to qp in time h
    return Pc / (2 * np.sinh(omega * h)) * ((q * q + qp * qp) * np.cosh(omega * h) - 2 * q * qp)


def d1LdE(q, qp, h):
    return Pc / np.sinh(omega * h) * (q * np.cosh(omega * h) - qp)


def V_window(q, theta):                              # min over the endpoint in Omega of L_d^E(q, q_f; theta) + V(q_f)
    res = minimize_scalar(lambda qf: LdE(q, qf, theta) + V(qf), bounds=(-r, r), method="bounded",
                          options={"xatol": 1e-13})
    return res.fun, res.x


# ------------------------------------------------------------------------------------------- Part A: Section 5.2
theta = 0.1
print(f"Part A (Section 5.2): m = kappa = 1, r = {r}, theta = {theta}, W = V")
thr = r * np.exp(omega * theta)
for q in (0.3, 0.999 * thr, 1.001 * thr, 1.0, 2.0):
    v, qf = V_window(q, theta)
    print(f"  q = {q:.5f}: V_theta - V = {v - V(q):.2e}, optimal endpoint {qf:+.5f}   (threshold r e^(omega theta) = {thr:.5f})")

Vt1 = LdE(1.0, r, theta) + V(r)
Vt1_min, qf1 = V_window(1.0, theta)


def extremal(t, q0=1.0, qf=r, T=theta):              # solution of m qddot = kappa q from q0 to qf in time T
    return (q0 * np.sinh(omega * (T - t)) + qf * np.sinh(omega * t)) / np.sinh(omega * T)


def extremal_dot(t, q0=1.0, qf=r, T=theta):
    return omega * (-q0 * np.cosh(omega * (T - t)) + qf * np.cosh(omega * t)) / np.sinh(omega * T)


action = quad(lambda t: 0.5 * m * extremal_dot(t) ** 2 + 0.5 * kappa * extremal(t) ** 2, 0, theta,
              epsabs=0.0, epsrel=1e-12)[0]
print(f"  V_theta(1) = L_d^E(1, r) + V(r) = {Vt1:.6f}  [bounded minimization {Vt1_min:.6f} at q_f = {qf1:.6f}; "
      f"quadrature of the action {action + V(r):.6f}]   V(1) = {V(1.0):.6f}   (claims 1.404, 0.5)")
p0 = -d1LdE(1.0, r, theta)
print(f"  first move p/m = -d_1 L_d^E(1, r)/m = {p0 / m:.6f}  [m qdot(0) of the extremal / m = {extremal_dot(0.0):.6f}]"
      f"   rule -omega q = {-omega * 1.0:.6f}   (claims -5.04, -1)")

# ------------------------------------------------------------------------------------------- Part B: Section 6.3
h = 0.1
print(f"\nPart B (Section 6.3): L_d^E, h = {h}, W = 1/2 q^2, Omega = [-{r}, {r}], q = 1")
a, b = Pc * np.cosh(omega * h) / (2 * np.sinh(omega * h)), Pc / np.sinh(omega * h)   # L_d^E = a(q^2+q'^2) - b q q'
qs = np.linspace(-3, 3, 61)
BW = np.array([minimize_scalar(lambda qp: LdE(q, qp, h) + V(qp), bounds=(-10, 10), method="bounded",
                               options={"xatol": 1e-13}).fun for q in qs])
print(f"  max |B W - W| over q in [-3, 3] = {np.max(np.abs(BW - V(qs))):.1e}; minimizer of B W at q = 1: "
      f"{b / (2 * a + Pc):.6f} = e^(-h) = {np.exp(-omega * h):.6f}")


def V_chain(q0, N):
    """Exact V_N(q0): minimize sum_j L_d^E(q_j, q_{j+1}) + W(q_N) over q_1..q_N with |q_N| <= r (convex QP)."""
    Hm = np.zeros((N, N))
    g = np.zeros(N)
    for j in range(N):                               # term L_d^E(q_j, q_{j+1}), unknowns x_k = q_{k+1}
        if j == 0:
            Hm[0, 0] += 2 * a
            g[0] += -b * q0
        else:
            Hm[j - 1, j - 1] += 2 * a
            Hm[j, j] += 2 * a
            Hm[j - 1, j] -= b
            Hm[j, j - 1] -= b
    Hm[N - 1, N - 1] += Pc                           # W(q_N)
    const = a * q0 * q0
    f = lambda x: 0.5 * x @ Hm @ x + g @ x + const
    x = np.linalg.solve(Hm, -g)
    mu = 0.0
    if abs(x[-1]) > r:                               # terminal bound active: fix q_N = +-r, solve for the rest
        qN = np.sign(x[-1]) * r
        x = np.zeros(N)
        x[-1] = qN
        if N > 1:
            x[:-1] = np.linalg.solve(Hm[:-1, :-1], -(g[:-1] + Hm[:-1, -1] * qN))
        mu = -np.sign(qN) * (Hm[-1] @ x + g[-1])     # KKT: grad_N f + mu sign(q_N) = 0, mu >= 0
    return f(x), x, mu


first_exact = None
for N in range(1, 10):
    vN, x, mu = V_chain(1.0, N)
    vc = V_window(1.0, N * h)[0]                     # principle of optimality: same as the window of length N h
    if first_exact is None and abs(vN - V(1.0)) < 1e-12:
        first_exact = N
    print(f"  N = {N}: V_N(1) = {vN:.6f}  (continuous window N h: {vc:.6f})  V_N(1) - W(1) = {vN - V(1.0):.2e}  "
          f"q_N = {x[-1]:+.5f}  mu = {mu:.4f}  e^(-N h) = {np.exp(-N * h):.4f}")
first_exp = next(N for N in range(1, 100) if np.exp(-N * h) <= 0.5)
print(f"  V_1(1) = {V_chain(1.0, 1)[0]:.6f} (claim 1.404); first N with V_N(1) = W(1): {first_exact}; "
      f"first N with e^(-N h) <= 1/2: {first_exp}   (claim: both 7)")
