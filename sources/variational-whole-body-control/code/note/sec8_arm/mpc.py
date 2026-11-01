"""Receding-horizon solver: single shooting in the torques, SLSQP, exact adjoint gradients (sympy codegen)."""
import numpy as np
import sympy as sp
from scipy.optimize import minimize
from model import *
from condcheck import designs

d = designs()['good']
H_STEP = 0.005
C_OMEGA = 0.3      # terminal level  Omega = {W <= C_OMEGA}
C_W = 1.0          # terminal-cost scale

# ---------- symbolic step map G(z, tau) and stage cost lt(z, tau) ----------
zs = sp.symbols('e1 e2 w1 w2', real=True); ts = sp.symbols('t1 t2', real=True)
hs = sp.Symbol('h', positive=True)
Z = sp.Matrix(zs); T = sp.Matrix(ts)
q = sp.Matrix([qd[0] + zs[0], qd[1] + zs[1]]); v = sp.Matrix(zs[2:])
c2 = sp.cos(q[1]); sn2 = sp.sin(q[1])
Ms = sp.Matrix([[m1*l1**2 + m2*(l1**2 + l2**2 + 2*l1*l2*c2), m2*(l2**2 + l1*l2*c2)],
                [m2*(l2**2 + l1*l2*c2), m2*l2**2]])
hh = m2*l1*l2*sn2
Cs = sp.Matrix([[-hh*v[1], -hh*(v[0]+v[1])], [hh*v[0], 0]])
gs = sp.Matrix([(m1+m2)*g0*l1*sp.cos(q[0]) + m2*g0*l2*sp.cos(q[0]+q[1]), m2*g0*l2*sp.cos(q[0]+q[1])])
U = T - gs
acc = Ms.LUsolve(U - Cs*v)
vn = v + hs*acc
en = sp.Matrix(zs[:2]) + hs*vn
G = sp.Matrix([en, vn])
Qe, Qv, R = [sp.Matrix(x) for x in (d.Qe, d.Qv, d.R)]
e_ = sp.Matrix(zs[:2])
lt = ((e_.T*Qe*e_)[0] + (v.T*Qv*v)[0] + (U.T*R*U)[0])/2
Lam, Ke = sp.Matrix(d.Lam), sp.Matrix(d.Ke)
s_ = v + Lam*e_
Ws = (s_.T*Ms*s_)[0]/2 + (e_.T*Ke*e_)[0]/2
args = (zs, ts, hs)
f_G = sp.lambdify(args, G, 'numpy')
f_Gz = sp.lambdify(args, G.jacobian(Z), 'numpy')
f_Gt = sp.lambdify(args, G.jacobian(T), 'numpy')
f_l = sp.lambdify(args, lt, 'numpy')
f_lz = sp.lambdify(args, sp.Matrix([lt]).jacobian(Z), 'numpy')
f_lt = sp.lambdify(args, sp.Matrix([lt]).jacobian(T), 'numpy')
f_W = sp.lambdify((zs,), Ws, 'numpy')
f_Wz = sp.lambdify((zs,), sp.Matrix([Ws]).jacobian(Z), 'numpy')


def rollout(z0, tau, h=H_STEP):
    N = len(tau)
    zs_ = np.zeros((N+1, 4)); zs_[0] = z0
    for k in range(N):
        zs_[k+1] = np.asarray(f_G(zs_[k], tau[k], h), float).ravel()
    return zs_


def cost_grad(x, z0, N, h=H_STEP, cW=C_W):
    tau = x.reshape(N, 2)
    zz = rollout(z0, tau, h)
    J = sum(h*f_l(zz[k], tau[k], h) for k in range(N)) + cW*f_W(zz[N])
    lam = cW*np.asarray(f_Wz(zz[N]), float).ravel()
    g = np.zeros((N, 2))
    for k in range(N-1, -1, -1):
        Gz = np.asarray(f_Gz(zz[k], tau[k], h), float); Gt = np.asarray(f_Gt(zz[k], tau[k], h), float)
        g[k] = h*np.asarray(f_lt(zz[k], tau[k], h), float).ravel() + Gt.T@lam
        lam = h*np.asarray(f_lz(zz[k], tau[k], h), float).ravel() + Gz.T@lam
    return J, g.ravel()


def term_con(x, z0, N, h=H_STEP):
    tau = x.reshape(N, 2)
    zz = rollout(z0, tau, h)
    return C_OMEGA - f_W(zz[N])


def term_con_grad(x, z0, N, h=H_STEP):
    tau = x.reshape(N, 2)
    zz = rollout(z0, tau, h)
    lam = -np.asarray(f_Wz(zz[N]), float).ravel()
    g = np.zeros((N, 2))
    for k in range(N-1, -1, -1):
        Gz = np.asarray(f_Gz(zz[k], tau[k], h), float); Gt = np.asarray(f_Gt(zz[k], tau[k], h), float)
        g[k] = Gt.T@lam
        lam = Gz.T@lam
    return g.ravel()


def tau_ref(z):
    return gvec(qd + z[:2]) + d.uref(z)


def solve(z0, N, x0, h=H_STEP, maxiter=500, ftol=1e-12):
    bounds = [(-TAU_MAX[0], TAU_MAX[0]), (-TAU_MAX[1], TAU_MAX[1])]*N
    cons = [{'type': 'ineq', 'fun': term_con, 'jac': term_con_grad, 'args': (z0, N, h)}]
    r = minimize(cost_grad, x0, args=(z0, N, h), jac=True, method='SLSQP', bounds=bounds, constraints=cons,
                 options={'maxiter': maxiter, 'ftol': ftol})
    return r


def ref_tail(z, n, h=H_STEP):
    """n steps of the reference law (saturated only for safety; inside Omega it is unsaturated)."""
    taus = []
    for _ in range(n):
        t = np.clip(tau_ref(z), -TAU_MAX, TAU_MAX); taus.append(t)
        z = np.asarray(f_G(z, t, h), float).ravel()
    return np.array(taus)
