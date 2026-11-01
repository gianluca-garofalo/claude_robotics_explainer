import numpy as np, sys
from scipy.optimize import minimize
from mpc import *

def minW(z0, N):
    def f(x):
        tau = x.reshape(N, 2); zz = rollout(z0, tau)
        return f_W(zz[N]), -term_con_grad(x, z0, N)
    best = np.inf
    for x0 in [ref_tail(z0, N).ravel(), np.zeros(2*N) + np.tile(gvec(qd+z0[:2]), N)]:
        r = minimize(f, x0, jac=True, method='SLSQP', bounds=[(-TAU_MAX[0], TAU_MAX[0]), (-TAU_MAX[1], TAU_MAX[1])]*N,
                     options={'maxiter': 1000, 'ftol': 1e-14})
        best = min(best, r.fun)
    return best

if __name__ == '__main__':
 for q0 in [(1.0, -0.95), (0.95, -0.9), (1.2, -1.2), (0.3, 0.3)]:
     z0 = np.array([q0[0]-qd[0], q0[1]-qd[1], 0, 0])
     print('q0', q0, 'W(z0)=', d.W(z0), 'tau_ref(z0)=', tau_ref(z0))
     for N in [1, 5, 10, 20, 40, 60]:
         print('   N', N, 'min W(z_N) =', minW(z0, N))
     sys.stdout.flush()
