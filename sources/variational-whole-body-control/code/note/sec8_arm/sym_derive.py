"""Symbolic derivation / verification for the 2-link example (sympy)."""
import sympy as sp

q1, q2, v1, v2, t = sp.symbols('q1 q2 v1 v2 t', real=True)
l1, l2, m1, m2, g0 = sp.symbols('l1 l2 m1 m2 g0', positive=True)
qd1, qd2 = sp.symbols('qd1 qd2', real=True)
q = sp.Matrix([q1, q2]); v = sp.Matrix([v1, v2])

# point masses at the link tips; gravity along -y
p1 = sp.Matrix([l1*sp.cos(q1), l1*sp.sin(q1)])
p2 = p1 + sp.Matrix([l2*sp.cos(q1+q2), l2*sp.sin(q1+q2)])
J1 = p1.jacobian(q); J2 = p2.jacobian(q)
M = sp.simplify(m1*J1.T*J1 + m2*J2.T*J2)
U = m1*g0*p1[1] + m2*g0*p2[1]
gvec = sp.simplify(sp.Matrix([sp.diff(U, qi) for qi in q]))
# Christoffel C
C = sp.zeros(2, 2)
for k in range(2):
    for j in range(2):
        C[k, j] = sp.simplify(sum(sp.Rational(1, 2)*(sp.diff(M[k, j], q[i]) + sp.diff(M[k, i], q[j])
                                                   - sp.diff(M[i, j], q[k]))*v[i] for i in range(2)))
print('M =', M)
print('C =', C)
print('g =', gvec)
# Expected closed forms
hh = m2*l1*l2*sp.sin(q2)
M_exp = sp.Matrix([[m1*l1**2 + m2*(l1**2 + l2**2 + 2*l1*l2*sp.cos(q2)), m2*(l2**2 + l1*l2*sp.cos(q2))],
                   [m2*(l2**2 + l1*l2*sp.cos(q2)), m2*l2**2]])
C_exp = sp.Matrix([[-hh*v2, -hh*(v1+v2)], [hh*v1, 0]])
g_exp = sp.Matrix([(m1+m2)*g0*l1*sp.cos(q1) + m2*g0*l2*sp.cos(q1+q2), m2*g0*l2*sp.cos(q1+q2)])
print('closed forms match:', sp.simplify(M - M_exp) == sp.zeros(2, 2), sp.simplify(C - C_exp) == sp.zeros(2, 2),
      sp.simplify(gvec - g_exp) == sp.zeros(2, 2)[:, 0])
# Euler-Lagrange check: d/dt dT/dv - dT/dq + dU/dq = M a + C v + g
a1, a2 = sp.symbols('a1 a2', real=True); a = sp.Matrix([a1, a2])
T = (v.T*M*v)[0]/2
EL = sp.Matrix([sum(sp.diff(sp.diff(T, v[i]), q[j])*v[j] + sp.diff(sp.diff(T, v[i]), v[j])*a[j] for j in range(2))
                - sp.diff(T, q[i]) + sp.diff(U, q[i]) for i in range(2)])
print('EL residual zero:', sp.simplify(EL - (M*a + C*v + gvec)) == sp.zeros(2, 1))
# skew symmetry of Mdot - 2C
Mdot = sp.Matrix(2, 2, lambda i, j: sum(sp.diff(M[i, j], q[k])*v[k] for k in range(2)))
N = sp.simplify(Mdot - 2*C)
print('Mdot-2C skew:', sp.simplify(N + N.T) == sp.zeros(2, 2), ' Mdot-2C =', N)

# Wdot along the plant M a + C v = u (u = tau - g)
u1, u2 = sp.symbols('u1 u2', real=True); u = sp.Matrix([u1, u2])
lam1, lam2, k1, k2, k12 = sp.symbols('lam1 lam2 k1 k2 k12', real=True)
Lam = sp.diag(lam1, lam2)
Ke = sp.Matrix([[k1, k12], [k12, k2]])
e = q - sp.Matrix([qd1, qd2]); s = v + Lam*e
W = (s.T*M*s)[0]/2 + (e.T*Ke*e)[0]/2
acc = M.inv()*(u - C*v)
Wdot = sum(sp.diff(W, q[i])*v[i] for i in range(2)) + sum(sp.diff(W, v[i])*acc[i] for i in range(2))
aterm = C*Lam*e + M*Lam*v
Wdot_claim = (s.T*u)[0] + (s.T*aterm)[0] + (e.T*Ke*v)[0]
print('Wdot = s.u + s.(C Lam e + M Lam edot) + e.Ke.edot :', sp.simplify(sp.expand(Wdot - Wdot_claim)) == 0)

# Slotine-Li law u = -KD s - a, Ke = 2 Lam KD (diagonal KD) -> Wdot = -edot KD edot - e Lam KD Lam e
d1, d2 = sp.symbols('d1 d2', positive=True); KD = sp.diag(d1, d2)
Wsl = Wdot_claim.subs({k1: 2*lam1*d1, k2: 2*lam2*d2, k12: 0})
usl = -KD*s - aterm
Wsl = Wsl.subs({u1: usl[0], u2: usl[1]})
print('Slotine-Li identity:', sp.simplify(sp.expand(Wsl - (-(v.T*KD*v)[0] - (e.T*Lam*KD*Lam*e)[0]))) == 0)

# Infinitesimal-window rule: argmin_u [ l + Wdot ], l = 1/2(e Qe e + v Qv v) + 1/2 u R u
r1, r2 = sp.symbols('r1 r2', positive=True); R = sp.diag(r1, r2)
qe1, qe2, qv1, qv2 = sp.symbols('qe1 qe2 qv1 qv2', positive=True)
Qe = sp.diag(qe1, qe2); Qv = sp.diag(qv1, qv2)
lx = (e.T*Qe*e)[0]/2 + (v.T*Qv*v)[0]/2
ell = lx + (u.T*R*u)[0]/2
F = ell + Wdot_claim
sol = sp.solve([sp.diff(F, u1), sp.diff(F, u2)], [u1, u2], dict=True)[0]
ustar = sp.Matrix([sol[u1], sol[u2]])
print('u* = -R^-1 s :', sp.simplify(ustar + R.inv()*s) == sp.zeros(2, 1))
D = sp.simplify(F.subs(sol))
D_claim = lx - (s.T*R.inv()*s)[0]/2 + (s.T*aterm)[0] + (e.T*Ke*v)[0]
print('D = lx - 1/2 s R^-1 s + s.a + e Ke edot :', sp.simplify(sp.expand(D - D_claim)) == 0)

# Second-order Hamiltonian: H(z,pi) = sup_u [pi_q.v + pi_v.f - l], pi = -grad_z W -> H = -D
pq = -sp.Matrix([sp.diff(W, qi) for qi in q]); pv = -sp.Matrix([sp.diff(W, vi) for vi in v])
Hin = (pq.T*v)[0] + (pv.T*acc)[0] - ell
solH = sp.solve([sp.diff(Hin, u1), sp.diff(Hin, u2)], [u1, u2], dict=True)[0]
Hval = Hin.subs(solH)
print('H(z,-grad W) = -D :', sp.simplify(sp.expand(Hval + D_claim)) == 0)
# note pi_v = -M s  (momentum-like)
print('pi_v = -M s :', sp.simplify(pv + M*s) == sp.zeros(2, 1))
