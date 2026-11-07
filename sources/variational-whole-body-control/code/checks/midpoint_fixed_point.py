"""Check for Section 6.3 of the note ("Exactness is a fixed point"), bullet "Midpoint rule", and its row in
Section 19.1: the midpoint rule has the continuous-time Riccati weight as a fixed point of its Bellman operator.

Setup: L = 1/2 q'Qq + 1/2 v'Rv, qdot = v; midpoint rule L_d(q,q') = h L(q_half, (q'-q)/h), q_half = (q+q')/2;
P = the continuous-time Riccati weight, P R^-1 P = Q; W = 1/2 q'Pq.

Prints:
 (a) symbolic residual (sympy, general symmetric 2x2 Q, R, X, arbitrary q, q') of the identity
         L_d(q,q') + W(q') - W(q) = h [ L(q_half, v) + grad W(q_half).v ]
     written as h [ 1/2 |v + R^-1 X q_half|_R^2 - H(q_half, -X q_half) ], and of the chord-slope identity
     W(q') - W(q) = h grad W(q_half).v                                  (claim: exactly 0)
 (b) 3-D example with QR != RQ (fixed seed), h in {0.05, 0.3, 1, 3}:
     |T_mid(P) - P| (so V_1 = W for every h), |step - Cayley map|, |step - expm(-h R^-1 P)| (nonzero: the step is
     not the exact sample of the LQR flow), and |T_rect(P) - P| for the rectangle rule (nonzero)
                                                                        (claim: residuals <= 3e-14)
     plus convergence of the iterated midpoint map to P from 0 and from 10P (illustration only).
 (c) X = cP: smallest eigenvalue of cP - T_mid(cP) at h = 0.3 (V_1 <= W iff c >= 1; supplementary).
 (e) supplementary, not stated in the note: scalar trapezoidal-rule fixed point sqrt(m k + h^2 k^2/4) and the scalar
     midpoint map, whose fixed point is sqrt(m k).
 (f) scalar numbers m = k = 1, h = 0.1, q = 1 (Cayley step 0.904762 against exp(-h) = 0.904837, V_1(1) = W(1) = 0.5).
Standalone: numpy, scipy, sympy. Runs in a few seconds.
"""
import numpy as np
import sympy as sp
from scipy.linalg import expm, sqrtm

# (a) symbolic identity, general symmetric 2x2 Q, R, X, arbitrary q, q'
h = sp.symbols('h', positive=True)
def symm(name):
    a, b, c = sp.symbols(f'{name}11 {name}12 {name}22')
    return sp.Matrix([[a, b], [b, c]])
Q, R, X = symm('Q'), symm('R'), symm('X')
q = sp.Matrix(sp.symbols('q1 q2'))
qp = sp.Matrix(sp.symbols('p1 p2'))
qh = (q + qp) / 2
v = (qp - q) / h
Ld = h * ((qh.T * Q * qh)[0] / 2 + (v.T * R * v)[0] / 2)
W = lambda x: (x.T * X * x)[0] / 2
Rinv = R.inv()
w = v + Rinv * X * qh
Hval = ((X * qh).T * Rinv * (X * qh))[0] / 2 - (qh.T * Q * qh)[0] / 2   # H(qh, -X qh), eq. (26)
rhs = h * ((w.T * R * w)[0] / 2 - Hval)
res = sp.simplify(sp.together(Ld + W(qp) - W(q) - rhs))
print('(a) symbolic residual of the midpoint identity:', res)
# chord-slope identity
res2 = sp.simplify(W(qp) - W(q) - h * ((X * qh).T * v)[0])
print('    chord-slope residual W(q\')-W(q) - h grad W(q_half).v:', res2)

# (b) numerical 3-D example
rng = np.random.default_rng(7)
def spd(n):
    A = rng.normal(size=(n, n))
    return A @ A.T + 0.5 * np.eye(n)
n = 3
Qn, Rn = spd(n), spd(n)
print('\n(b) ||QR-RQ|| =', np.linalg.norm(Qn @ Rn - Rn @ Qn))
Rh = np.real(sqrtm(Rn)); Rhi = np.linalg.inv(Rh)
P = Rh @ np.real(sqrtm(Rhi @ Qn @ Rhi)) @ Rh
P = (P + P.T) / 2
print('    residual P R^-1 P - Q =', np.linalg.norm(P @ np.linalg.solve(Rn, P) - Qn))

def T_mid(Xm, hh):
    A = Rn / hh + hh * Qn / 4
    B = -Rn / hh + hh * Qn / 4
    T = A - B @ np.linalg.solve(A + Xm, B)
    K = -np.linalg.solve(A + Xm, B)      # minimizer q' = K q
    return (T + T.T) / 2, K

def T_rect(Xm, hh):
    Rh_ = Rn / hh
    T = hh * Qn + Rh_ - Rh_ @ np.linalg.solve(Rh_ + Xm, Rh_)
    return (T + T.T) / 2

Kc = np.linalg.solve(Rn, P)   # R^-1 P
worst_b = np.linalg.norm(P @ np.linalg.solve(Rn, P) - Qn)
for hh in [0.05, 0.3, 1.0, 3.0]:
    T, K = T_mid(P, hh)
    worst_b = max(worst_b, np.linalg.norm(T - P), np.linalg.norm(K - np.linalg.solve(np.eye(n) + hh / 2 * Kc, np.eye(n) - hh / 2 * Kc)))
    cay = np.linalg.solve(np.eye(n) + hh / 2 * Kc, np.eye(n) - hh / 2 * Kc)
    print(f'    h={hh}: |T_mid(P)-P|={np.linalg.norm(T-P):.1e}, |step-Cayley|={np.linalg.norm(K-cay):.1e}, '
          f'|step-expm|={np.linalg.norm(K-expm(-hh*Kc)):.1e}, |T_rect(P)-P|={np.linalg.norm(T_rect(P,hh)-P):.3f}')
print(f'    largest residual in (b): {worst_b:.1e}   (claim: identity exact; residuals <= 3e-14)')

# iterate T_mid from 0 and from 10P (uniqueness of the PD fixed point, illustrated)
for X0 in [np.zeros((n, n)), 10 * P]:
    Xk = X0.copy()
    for _ in range(4000):
        Xk, _ = T_mid(Xk, 0.3)
    print('    iterate T_mid (h=0.3) from', 'zero' if not X0.any() else '10P', '-> |X-P| =', f'{np.linalg.norm(Xk-P):.1e}')

# (c) threshold on c
print('\n(c) smallest eigenvalue of cP - T_mid(cP) (h=0.3):')
for c in [0.9, 0.99, 0.999, 1.0, 1.001, 1.01, 1.1, 2.0]:
    T, _ = T_mid(c * P, 0.3)
    print(f'    c={c}: {np.linalg.eigvalsh(c*P - T).min(): .3e}')

# (e) trapezoidal rule, scalar: L_d = m/(2h)(q'-q)^2 + h k/4 (q^2+q'^2)
m, k, hs, Xs = sp.symbols('m kappa h X', positive=True)
Y = Xs + hs * k / 2
T_trap = hs * k / 2 + m * Y / (m + hs * Y)
sol = sp.solve(sp.Eq(T_trap, Xs), Xs)
print('\n(e) trapezoid fixed points:', sol, ' expected sqrt(m k + h^2 k^2/4)')
print('    m=k=1, h=0.1:', [sp.N(s.subs({m: 1, k: 1, hs: sp.Rational(1, 10)})) for s in sol])
# direct numerical check of T_trap by brute-force minimisation
def Ttrap_num(Xv, mm=1.0, kk=1.0, hh=0.1):
    # B(1/2 X q^2) at q=1 via closed-form min over q'
    a = mm / hh; b = hh * kk / 2 + Xv
    qp_ = a / (a + b)
    val = mm / (2 * hh) * (qp_ - 1) ** 2 + hh * kk / 4 * (1 + qp_ ** 2) + Xv / 2 * qp_ ** 2
    return 2 * val
xs = float(np.sqrt(1 + 0.01 / 4))
print('    T_trap(sqrt(1.0025)) - sqrt(1.0025) =', Ttrap_num(xs) - xs, '; T_trap(1)-1 =', Ttrap_num(1.0) - 1)
# midpoint scalar: symbolic T and fixed point
Tm = None
A_ = m / hs + hs * k / 4; B_ = -m / hs + hs * k / 4
Tm = sp.simplify(A_ - B_**2 / (A_ + Xs))
print('    scalar T_mid(X) =', sp.factor(Tm), '; fixed points:', sp.solve(sp.Eq(Tm, Xs), Xs))

# (f) scalar numbers
hh = 0.1
qplus = (1 - hh / 2) / (1 + hh / 2)
Ld1 = 1 / (2 * hh) * (qplus - 1) ** 2 + hh / 2 * ((1 + qplus) / 2) ** 2
print(f'\n(f) m=k=1, h=0.1, q=1: q+ = {qplus:.6f} (exp(-h) = {np.exp(-hh):.6f}), L_d = {Ld1:.6f}, '
      f'W(1)-W(q+) = {0.5 - 0.5*qplus**2:.6f}, V_1(1) = {Ld1 + 0.5*qplus**2:.6f}')
# L_d^mid vs L_d^E at (1, 0.95)
w_ = 1.0
LdE = 1 / (2 * np.sinh(w_ * hh)) * ((1 + 0.95**2) * np.cosh(w_ * hh) - 2 * 0.95)
Ldm = 1 / (2 * hh) * 0.05**2 + hh / 2 * 0.975**2
print(f'    L_d^E(1,0.95) = {LdE:.6f}, L_d^mid(1,0.95) = {Ldm:.6f}')
