"""Symbolic checks for the hilltop example and its exact discrete Lagrangian not printed elsewhere.

L = 1/2 m qdot^2 + 1/2 kappa q^2, omega = sqrt(kappa/m), W = V = 1/2 sqrt(m kappa) q^2.
(1) Jacobi field y = sinh(omega t): y'' = omega^2 y, y(0) = 0 (no conjugate point); oscillator: sin has a zero at pi/omega.
(2) The closed form of L_d^E equals the action of the extremal joining q and q' in time h.
(3) One step with L_d^E and W = V: grad V_1(q) = d_1 L_d^E(q, q*) and p' = d_2 L_d^E(q, q*) = -grad W(q*).
"""
import sympy as sp

t, m, k, h, q, qp = sp.symbols('t m kappa h q qp', positive=True)
w = sp.sqrt(k/m)
# (1)
y = sp.sinh(w*t)
print("(1) y'' - omega^2 y =", sp.simplify(sp.diff(y, t, 2) - w**2*y), " y(0) =", y.subs(t, 0),
      "| oscillator sin(omega t) at t = pi/omega:", sp.simplify(sp.sin(w*t).subs(t, sp.pi/w)))
# (2)
qt = (q*sp.sinh(w*(h - t)) + qp*sp.sinh(w*t))/sp.sinh(w*h)
print("    extremal check m q'' - kappa q =", sp.simplify(m*sp.diff(qt, t, 2) - k*qt))
# integrate in exponential form with omega as a symbol (fast), then substitute omega = sqrt(kappa/m)
om = sp.symbols('omega', positive=True)
qe = ((q*sp.sinh(om*(h - t)) + qp*sp.sinh(om*t))/sp.sinh(om*h)).rewrite(sp.exp)
Lag = sp.expand(sp.Rational(1, 2)*m*sp.diff(qe, t)**2 + sp.Rational(1, 2)*m*om**2*qe**2)   # kappa = m omega^2
S = sp.integrate(Lag, (t, 0, h), conds="none")
LdE_om = m*om/(2*sp.sinh(om*h))*((q**2 + qp**2)*sp.cosh(om*h) - 2*q*qp)                     # sqrt(m kappa) = m omega
print("(2) action of extremal - closed form L_d^E =", sp.simplify(sp.expand((S - LdE_om).rewrite(sp.exp))))
LdE = sp.sqrt(m*k)/(2*sp.sinh(w*h))*((q**2 + qp**2)*sp.cosh(w*h) - 2*q*qp)
# (3)
W = lambda x: sp.Rational(1, 2)*sp.sqrt(m*k)*x**2
qs = sp.solve(sp.diff(LdE + W(qp), qp), qp)[0]
V1 = (LdE + W(qp)).subs(qp, qs)
print("(3) V_1 - W(q) =", sp.simplify((V1 - W(q)).rewrite(sp.exp)),
      "| grad V_1 - d_1 L_d^E(q,q*) =", sp.simplify((sp.diff(V1, q) - sp.diff(LdE, q).subs(qp, qs)).rewrite(sp.exp)),
      "| d_2 L_d^E(q,q*) + grad W(q*) =", sp.simplify((sp.diff(LdE, qp).subs(qp, qs) + sp.diff(W(qp), qp).subs(qp, qs)).rewrite(sp.exp)))
