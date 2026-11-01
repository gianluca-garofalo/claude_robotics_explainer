"""Long-window optimal values V_N(z0) (approximating the infinite-window optimum) from the PD warm start."""
import numpy as np, sys
from closedloop import solve_scaled
from mpc import *
for lab, q0 in [('B', (0.9, -0.85)), ('A', (1.0, -0.95))]:
    z0 = np.array([q0[0]-qd[0], q0[1]-qd[1], 0, 0])
    for N in [100, 200, 400]:
        x = ref_tail(z0, N).ravel()
        Jc = cost_grad(x, z0, N)[0]
        r = solve_scaled(z0, N, x, Jc)
        J = cost_grad(r.x, z0, N)[0]
        zz = rollout(z0, r.x.reshape(N, 2))
        print(lab, 'N', N, 'PD-warm-start cost', Jc, 'optimum', J, 'W(z_N)', f_W(zz[N]), 'stage part', J - f_W(zz[N]), r.message, r.nit); sys.stdout.flush()
