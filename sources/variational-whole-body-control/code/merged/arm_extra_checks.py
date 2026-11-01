"""Two numbers of the manipulator example that are not printed by note/sec8_arm/*.py.

(a) Exact adjoint gradients of the single-shooting cost and of the terminal constraint
    (note/sec8_arm/mpc.py) against central finite differences (N = 10, random torque sequences).
(b) 'One step is the discrete PD law': closed loop with N = 1 from q0 = (0.9, -0.85) at rest;
    largest gap between its torque and the PD+g torque (pdg) at the visited states, and the
    shrinking of the joint-2 gap when the one-step problem is re-solved with h/2, h/4, h/8.
Run time: about one minute.
"""
import os, sys
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'note', 'sec8_arm'))
import numpy as np                                         # noqa: E402
from mpc import cost_grad, term_con, term_con_grad, tau_ref, solve, H_STEP, qd, TAU_MAX, d   # noqa: E402
from closedloop import run_mpc                             # noqa: E402
from model import gvec                                     # noqa: E402

rng = np.random.default_rng(0)
# ---------------------------------------------------------------- (a)
N = 10; worst_c = worst_t = 0.0
for trial in range(5):
    z0 = np.concatenate([rng.normal(scale=0.2, size=2), rng.normal(scale=0.5, size=2)])
    x = rng.normal(scale=5.0, size=2*N)
    J, g = cost_grad(x, z0, N); gt = term_con_grad(x, z0, N)
    eps = 1e-6; gfd = np.zeros_like(x); tfd = np.zeros_like(x)
    for i in range(len(x)):
        e = np.zeros_like(x); e[i] = eps
        gfd[i] = (cost_grad(x + e, z0, N)[0] - cost_grad(x - e, z0, N)[0])/(2*eps)
        tfd[i] = (term_con(x + e, z0, N) - term_con(x - e, z0, N))/(2*eps)
    worst_c = max(worst_c, np.abs(g - gfd).max()); worst_t = max(worst_t, np.abs(gt - tfd).max())
print(f"(a) adjoint vs finite differences, N = {N}: cost gradient {worst_c:.1e}, terminal-constraint gradient {worst_t:.1e}")

# ---------------------------------------------------------------- (b)
q0 = (0.9, -0.85); z0 = np.array([q0[0] - qd[0], q0[1] - qd[1], 0.0, 0.0])
rec = run_mpc(z0, 1, 500)
Z = rec['z'][:-1]; T1 = rec['tau']
Tpd = np.array([tau_ref(z) for z in Z])              # unsaturated PD+g torque at the visited states
gap = np.abs(T1 - Tpd)
k1, k2 = gap[:, 0].argmax(), gap[:, 1].argmax()
print(f"(b) N = 1: closed-loop action {H_STEP*np.sum(rec['l']):.6f}; max torque gap to PD+g: "
      f"joint 1 {gap[k1, 0]:.3f} N m at t = {k1*H_STEP:.3f} s, joint 2 {gap[k2, 1]:.3f} N m at t = {k2*H_STEP:.3f} s")
late = gap[int(0.05/H_STEP):].max(axis=0)
print(f"    largest gaps after t = 0.05 s: {late[0]:.3f}, {late[1]:.3f} N m")
z = Z[k2]
for div in [1, 2, 4, 8]:
    h = H_STEP/div
    x0 = np.clip(tau_ref(z), -TAU_MAX, TAU_MAX)
    r = solve(z, 1, x0, h=h, maxiter=500, ftol=1e-14)
    print(f"    re-solve at the state of the largest joint-2 gap with h/{div}: joint-2 gap = {abs(r.x[1] - tau_ref(z)[1]):.3f} N m"
          f" (joint 1: {abs(r.x[0] - tau_ref(z)[0]):.3f})")
