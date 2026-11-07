"""Checks added with the restructured note (Sections 5.2, 9.1 and 16.1).

1. Finite window on the hilltop with W = c V (Section 5.2):
       V_theta(q) = 1/2 sqrt(m kappa) (c + tanh(w theta)) / (1 + c tanh(w theta)) q^2
   solves  dV/dtheta = -H(q, -dV/dq),  V_0 = c V,  and is monotone in theta with the sign of (1 - c).
2. Discrete "torque = velocity momentum" with Gauss's weight, one degree of freedom:
       zero-order hold:   T0 tau_0 = pi_v + (h/2) pi_q
       symplectic Euler:  T0 tau_0 = pi_v +  h    pi_q        with pi = -grad V_{N-1}(z_1),
   the end-of-step position-momentum term as a percentage of T0 tau_0, and, at every node j, with
   pi_j = -grad V_{N-j}(z_j):
       symplectic Euler:  T0 tau_j = pi_{v,j}                 (node where the torque is applied)
       zero-order hold:   T0 tau_j = (pi_{v,j} + pi_{v,j+1})/2 (mean over the step).
3. First-instant stiffness of a 10 ms window: optimal time-varying torque (Riccati ODE) versus
   zero-order hold (closed form k d / (2 (T0 + d + k d^3 / (4 m)))).

Setup of 2-3 (Sections 9.1 and 16.1): mass M = 2 kg, W = 1/2 M v^2 + 1/2 K_e q^2 with K_e = 30 N/m, stage cost
(T0/2) tau^2/M (Gauss's weight) with T0 = 0.1 s and nothing else, window theta = 10 ms, start at rest at q = 1.
In the code below m stands for M and k for K_e.
"""
import numpy as np
from scipy.integrate import solve_ivp

# ---------------------------------------------------------------- 1. finite window, W = c V
m_h, k_h = 1.0, 1.0
w = np.sqrt(k_h / m_h)
P_inf = np.sqrt(m_h * k_h)
worst = 0.0
for c in (0.0, 0.5, 1.0, 1.2, 3.0):
    # Riccati ODE in time-to-go: P' = kappa - P^2/m, P(0) = c sqrt(m kappa)
    sol = solve_ivp(lambda th, P: [k_h - P[0] ** 2 / m_h], [0, 4.0], [c * P_inf],
                    rtol=1e-12, atol=1e-14, dense_output=True)
    th = np.linspace(0, 4.0, 401)
    closed = P_inf * (c + np.tanh(w * th)) / (1 + c * np.tanh(w * th))
    err = np.max(np.abs(sol.sol(th)[0] - closed))
    worst = max(worst, err)
    slope = np.sign(np.round(np.diff(closed).mean(), 12))
    print(f"c={c:3.1f}: max |numerical - closed form| = {err:.1e}; "
          f"monotone {'up' if slope > 0 else 'down' if slope < 0 else 'flat'} in theta; "
          f"P(0)={closed[0]:.4f} -> P(4)={closed[-1]:.4f}")
print(f"worst agreement {worst:.1e}  (claim: <= 1e-10)\n")

# ---------------------------------------------------------------- 2. torque = momentum in discrete time
m, k, T0 = 2.0, 30.0, 0.1
def first_step(h, N, scheme):
    A = np.array([[1.0, h], [0.0, 1.0]])
    B = np.array([[h * h / (2 * m) if scheme == 'zoh' else h * h / m], [h / m]])
    R = h * T0 / m                                        # stage cost h (T0/2) tau^2 / m
    P = [np.diag([k, m])]                                 # V_0 = W
    for _ in range(N):                                    # backward discrete Riccati recursion
        Pn = P[-1]
        S = R + (B.T @ Pn @ B)[0, 0]
        P.append(A.T @ Pn @ A - (A.T @ Pn @ B) @ (B.T @ Pn @ A) / S)
    Pn = P[N - 1]                                         # V_{N-1} at the first successor
    K = (B.T @ Pn @ A) / (R + (B.T @ Pn @ B)[0, 0])
    z0 = np.array([1.0, 0.0])
    tau = -(K @ z0)[0]
    z1 = A @ z0 + B[:, 0] * tau
    pi = -Pn @ z1                                         # pi_1 = -grad V_{N-1}(z_1)
    coef = h / 2 if scheme == 'zoh' else h
    resid = T0 * tau - (pi[1] + coef * pi[0])
    return tau, coef * pi[0] / (T0 * tau), resid
def every_node(h, N, scheme):
    A = np.array([[1.0, h], [0.0, 1.0]])
    B = np.array([[h * h / (2 * m) if scheme == 'zoh' else h * h / m], [h / m]])
    R = h * T0 / m
    P = [np.diag([k, m])]
    for _ in range(N):
        Pn = P[-1]
        P.append(A.T @ Pn @ A - (A.T @ Pn @ B) @ (B.T @ Pn @ A) / (R + (B.T @ Pn @ B)[0, 0]))
    z, tau = [np.array([1.0, 0.0])], []
    for j in range(N):
        Pn = P[N - j - 1]
        tau.append(-(((B.T @ Pn @ A) / (R + (B.T @ Pn @ B)[0, 0])) @ z[-1])[0])
        z.append(A @ z[-1] + B[:, 0] * tau[-1])
    piv = [-(P[N - j] @ z[j])[1] for j in range(N + 1)]       # pi_{v,j} = -grad_v V_{N-j}(z_j)
    if scheme == 'se':
        resid = max(abs(T0 * tau[j] - piv[j]) for j in range(N))
    else:
        resid = max(abs(T0 * tau[j] - 0.5 * (piv[j] + piv[j + 1])) for j in range(N))
    return resid, piv
for scheme, cases in (('zoh', [(0.010, 1), (0.005, 2), (0.001, 10)]), ('symplectic Euler', [(0.005, 2), (0.001, 10)])):
    for h, N in cases:
        sch = 'zoh' if scheme == 'zoh' else 'se'
        tau, share, resid = first_step(h, N, sch)
        resid_j, piv = every_node(h, N, sch)
        print(f"{scheme:17s} h={h*1e3:4.1f} ms N={N:2d}: tau_0={tau:+.4f} N, end-of-step position-momentum term "
              f"= {100*share:5.1f}% of T0 tau_0, identity residual {abs(resid):.1e}; at every node, residual against "
              f"{'(pi_v,j + pi_v,j+1)/2' if sch == 'zoh' else 'pi_v,j'} {resid_j:.1e}")
        if sch == 'zoh' and N == 1:
            print(f"{'':17s} per unit q_0: -pi_v,0/T0 = {-piv[0]/T0:.4f} N/m, -pi_v,1/T0 = {-piv[1]/T0:.4f} N/m, "
                  f"mean {-(piv[0]+piv[1])/(2*T0):.4f} N/m   (claims 2.864, -0.136, 1.36)")
print()

# ---------------------------------------------------------------- 3. first-instant stiffness, 10 ms window
d = 0.010
def ric(th, P):                                           # time-to-go Riccati ODE, control weight T0/m, B = (0, 1/m)
    P11, P12, P22 = P
    g = 1.0 / (m * T0)
    return [-P12 ** 2 * g, P11 - P12 * P22 * g, 2 * P12 - P22 ** 2 * g]
P12 = solve_ivp(ric, [0, d], [k, 0.0, m], rtol=1e-12, atol=1e-14).y[1, -1]
print(f"time-varying optimum: stiffness P12(d)/T0 = {P12 / T0:.4f} N/m   (claim 2.86)")
print(f"zero-order hold:      stiffness = {k * d / (2 * (T0 + d + k * d ** 3 / (4 * m))):.4f} N/m   (claim 1.36)")
