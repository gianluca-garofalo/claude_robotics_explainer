"""Symbolic checks for Section 7 (second-order plants)."""
import sympy as sp

t = sp.symbols('t')
print("=== A. Augmented-Lagrangian EL equations == Hamilton's equations of H(z,pi) (scalar q, generic f, l) ===")
q, v, u, pq, pv = [sp.Function(n)(t) for n in ('q', 'v', 'u', 'pq', 'pv')]
f = sp.Function('f')
l = sp.Function('l')
Lt = l(q, v, u) + pq*(q.diff(t) - v) + pv*(v.diff(t) - f(q, v, u))

def EL(L, x):
    return sp.simplify(sp.diff(L, x.diff(t)).diff(t) - sp.diff(L, x))  # d/dt dL/dxdot - dL/dx = 0

elq, elv, elu = EL(Lt, q), EL(Lt, v), EL(Lt, u)
elpq, elpv = EL(Lt, pq), EL(Lt, pv)
# Hamiltonian (note's convention): H = pq v + pv f - l, evaluated at the stationary u
Q, Vv, U, PQ, PV = sp.symbols('Q Vv U PQ PV')
H = PQ*Vv + PV*f(Q, Vv, U) - l(Q, Vv, U)
sub = {q: Q, v: Vv, u: U, pq: PQ, pv: PV}
def s(e): return e.subs({q.diff(t): sp.Symbol('qd'), v.diff(t): sp.Symbol('vd'), pq.diff(t): sp.Symbol('pqd'), pv.diff(t): sp.Symbol('pvd')}).subs(sub)
# EL wrt q: pq' = l_q - f_q pv ; Hamilton: pq' = -H_q
print("EL_q  :", s(elq), "  (=0)  vs  pq' + H_q =", sp.simplify(sp.Symbol('pqd') + sp.diff(H, Q)))
print("EL_v  :", s(elv), "  (=0)  vs  pv' + H_v =", sp.simplify(sp.Symbol('pvd') + sp.diff(H, Vv)))
print("EL_u  :", s(elu), "  (=0)  vs  H_u =", sp.simplify(sp.diff(H, U)))
print("EL_pq :", s(elpq), " EL_pv:", s(elpv))
print("diff EL_q - (pq' + H_q):", sp.simplify(s(elq) - (sp.Symbol('pqd') + sp.diff(H, Q))))
print("diff EL_v - (pv' + H_v):", sp.simplify(s(elv) - (sp.Symbol('pvd') + sp.diff(H, Vv))))
print("diff EL_u - H_u:", sp.simplify(s(elu) - sp.diff(H, U)))  # EL_u = H_u: stationarity in u is H_u = 0

print("\n=== B. Ostrogradsky momenta for f=u, l = lhat(q, qdot, qddot) ===")
x = sp.Function('x')(t)
lh = sp.Function('lh')
a0, a1, a2 = sp.symbols('a0 a1 a2')
lexpr = lh(a0, a1, a2)
rep = {a0: x, a1: x.diff(t), a2: x.diff(t, 2)}
dl0 = sp.diff(lexpr, a0).subs(rep)
dl1 = sp.diff(lexpr, a1).subs(rep)
dl2 = sp.diff(lexpr, a2).subs(rep)
p2 = dl2
p1 = dl1 - dl2.diff(t)
# augmented system with f=u: stationarity in u: l_u = pv ; EL_v: pv' = l_v - pq ; EL_q: pq' = l_q
pv_aug = dl2                      # from EL_u
pq_aug = dl1 - pv_aug.diff(t)     # from EL_v solved for pq
print("pv - p2:", sp.simplify(pv_aug - p2), "  pq - p1:", sp.simplify(pq_aug - p1))
EP = dl0 - dl1.diff(t) + dl2.diff(t, 2)      # Euler-Poisson
print("EL_q (pq' - l_q) + Euler-Poisson:", sp.simplify(pq_aug.diff(t) - dl0 + EP))

print("\n=== C. Double integrator, l = 1/2(q1 q^2 + q2 v^2 + r u^2) ===")
q1, q2, r = sp.symbols('q1 q2 r', positive=True)
A = sp.Matrix([[0, 1], [0, 0]]); B = sp.Matrix([0, 1]); Qm = sp.diag(q1, q2)
p12 = sp.sqrt(r*q1); p22 = sp.sqrt(r*(q2 + 2*sp.sqrt(r*q1))); p11 = sp.sqrt(q1*(q2 + 2*sp.sqrt(r*q1)))
P = sp.Matrix([[p11, p12], [p12, p22]])
care = A.T*P + P*A - P*B*B.T*P/r + Qm
print("CARE residual (simplified):", sp.simplify(care))
print("p11 - p12 p22/r =", sp.simplify(p11 - p12*p22/r))
zq, zv = sp.symbols('z_q z_v', real=True)
z = sp.Matrix([zq, zv])
Vz = (z.T*P*z)[0]/2
piq, piv = -sp.diff(Vz, zq), -sp.diff(Vz, zv)
uu = sp.symbols('uu')
Hsup_arg = piq*zv + piv*uu - (q1*zq**2 + q2*zv**2 + r*uu**2)/2
ustar = sp.solve(sp.diff(Hsup_arg, uu), uu)[0]
print("u* =", sp.simplify(ustar), " ; -r^-1 B^T P z =", sp.simplify((-B.T*P*z/r)[0]), " diff:", sp.simplify(ustar + (B.T*P*z/r)[0]))
HJ = sp.simplify(Hsup_arg.subs(uu, ustar))
print("H(z,-grad V) =", HJ)
lstar = (q1*zq**2 + q2*zv**2 + r*ustar**2)/2
Vdot = sp.diff(Vz, zq)*zv + sp.diff(Vz, zv)*ustar
print("Vdot + l =", sp.simplify(Vdot + lstar))
# Hamilton's equations and Hamiltonian matrix in (q, v, pi_q, pi_v)
Hfun = sp.Symbol('PQ')*zv + sp.Symbol('PV')**2/(2*r) - (q1*zq**2 + q2*zv**2)/2
X = [zq, zv, sp.Symbol('PQ'), sp.Symbol('PV')]
rhs = [sp.diff(Hfun, X[2]), sp.diff(Hfun, X[3]), -sp.diff(Hfun, X[0]), -sp.diff(Hfun, X[1])]
Ham = sp.Matrix([[sp.diff(e, xx) for xx in X] for e in rhs])
print("Hamiltonian matrix:", Ham)
blk = sp.Matrix(sp.BlockMatrix([[A, B*B.T/r], [Qm, -A.T]]))
print("equals [[A, BR^-1B^T],[Q,-A^T]]:", sp.simplify(Ham - blk) == sp.zeros(4))
s_ = sp.symbols('s')
print("char poly:", sp.factor(sp.expand((s_*sp.eye(4) - Ham).det())))
# Graph pi = -P z invariant:  Ham [I; -P] = [I; -P] (A - B K)
K = B.T*P/r
G = sp.Matrix.vstack(sp.eye(2), -P)
print("invariance residual Ham G - G Acl:", sp.simplify(Ham*G - G*(A - B*K)))
print("closed-loop char poly:", sp.factor((s_*sp.eye(2) - (A - B*K)).det()))
# Ostrogradsky momenta along closed loop
lh2 = lambda a0_, a1_, a2_: (q1*a0_**2 + q2*a1_**2 + r*a2_**2)/2
acc = (-(K*z))[0]                    # qddot as function of state
jerk = sp.diff(acc, zq)*zv + sp.diff(acc, zv)*acc   # d/dt qddot along flow
P2 = r*acc
P1 = q2*zv - r*jerk
print("p2 - pi_v:", sp.simplify(P2 - piv), "   p1 - pi_q:", sp.simplify(P1 - piq))
# H on Ostrogradsky form, linear in p1
print("H is linear in PQ:", sp.diff(Hfun, sp.Symbol('PQ'), 2) == 0)
for vals in [{q1: 1, q2: 0, r: 1}, {q1: 1, q2: 1, r: 1}]:
    print("  values", vals, " P =", sp.nsimplify(P.subs(vals)), " K =", sp.nsimplify(K.subs(vals)),
          " cl eig:", [sp.nsimplify(e) for e in (A - B*K).subs(vals).eigenvals()],
          " Ham eig:", [sp.simplify(e) for e in Ham.subs(vals).eigenvals()])
