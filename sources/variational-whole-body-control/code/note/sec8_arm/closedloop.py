"""Closed-loop receding-horizon simulation; records V_N and checks the descent inequality."""
import numpy as np, sys, time, pickle
from scipy.optimize import minimize
from mpc import *

def solve_scaled(z0, N, x0, scale):
    bounds = [(-TAU_MAX[0], TAU_MAX[0]), (-TAU_MAX[1], TAU_MAX[1])]*N
    f = lambda x: tuple(np.array(v)/scale for v in cost_grad(x, z0, N))
    cons = [{'type': 'ineq', 'fun': lambda x: term_con(x, z0, N)/C_OMEGA, 'jac': lambda x: term_con_grad(x, z0, N)/C_OMEGA}]
    return minimize(f, x0, jac=True, method='SLSQP', bounds=bounds, constraints=cons,
                    options={'maxiter': 1000, 'ftol': 1e-13})

def run_mpc(z0, N, steps, x_init=None):
    z = z0.copy(); x = x_init
    rec = dict(z=[z.copy()], tau=[], V=[], l=[], fallback=0, active=0, termW=[], nit=[])
    for k in range(steps):
        if x is None:
            x = ref_tail(z, N).ravel()
        Jc = cost_grad(x, z, N)[0]; feas_c = term_con(x, z, N) >= -1e-12
        r = solve_scaled(z, N, x, max(Jc, 1e-300))
        J = cost_grad(r.x, z, N)[0]; feas = term_con(r.x, z, N) >= -1e-10
        if not feas and k == 0:
            raise RuntimeError(f'infeasible at k=0: {r.message}')
        if (not feas) or (feas_c and J > Jc):
            rec['fallback'] += 1; xs = x; J = Jc
        else:
            xs = r.x
        tau = xs[:2]
        zz = rollout(z, xs.reshape(N, 2))
        rec['termW'].append(f_W(zz[N])); rec['active'] += int(abs(f_W(zz[N]) - C_OMEGA) < 1e-6)
        rec['nit'].append(r.nit)
        u = tau - gvec(qd + z[:2])
        rec['V'].append(J); rec['l'].append(d.ell(z, u)); rec['tau'].append(tau)
        z = np.asarray(f_G(z, tau, H_STEP), float).ravel(); rec['z'].append(z.copy())
        # warm start: shift and append one reference step at the predicted terminal state
        x = np.concatenate([xs[2:], ref_tail(zz[N], 1).ravel()])
    for key in ['z', 'tau', 'V', 'l', 'termW']: rec[key] = np.array(rec[key])
    return rec

def run_pd(z0, steps):
    z = z0.copy(); rec = dict(z=[z.copy()], tau=[], l=[], W=[])
    for k in range(steps):
        tau = np.clip(tau_ref(z), -TAU_MAX, TAU_MAX); u = tau - gvec(qd + z[:2])
        rec['tau'].append(tau); rec['l'].append(d.ell(z, u)); rec['W'].append(d.W(z))
        z = np.asarray(f_G(z, tau, H_STEP), float).ravel(); rec['z'].append(z.copy())
    for key in rec: rec[key] = np.array(rec[key])
    return rec

def report(name, rec, h=H_STEP):
    s = f'{name}: J_cl = sum h l = {h*rec["l"].sum():.6f}'
    if 'V' in rec:
        V, l = rec['V'], rec['l']
        viol = V[1:] - V[:-1] + h*l[:-1]
        rel = viol/(h*l[:-1])
        s += (f'; V_N(z0) = {V[0]:.6f}; max[V+ - V + h l] = {viol.max():.3e} (rel to h l: {rel.max():.3e}); '
              f'max step ratio (V+-V)/(-h l) min = {np.min((V[:-1]-V[1:])/(h*l[:-1])):.4f}; '
              f'fallbacks = {rec["fallback"]}; terminal constraint active at {rec["active"]} steps; '
              f'max|tau1|={np.abs(rec["tau"][:,0]).max():.2f} max|tau2|={np.abs(rec["tau"][:,1]).max():.2f}; '
              f'final |z| = {np.linalg.norm(rec["z"][-1]):.2e}; V_N final = {V[-1]:.3e}; mean nit = {np.mean(rec["nit"]):.1f}')
    else:
        s += (f'; max|tau1|={np.abs(rec["tau"][:,0]).max():.2f} max|tau2|={np.abs(rec["tau"][:,1]).max():.2f}; '
              f'final |z| = {np.linalg.norm(rec["z"][-1]):.2e}; W(z0)={rec["W"][0]:.6f}')
    print(s); sys.stdout.flush()

if __name__ == '__main__':
    exp = sys.argv[1]; Ns = [int(n) for n in sys.argv[2].split(',')]
    steps = int(sys.argv[3]) if len(sys.argv) > 3 else 500
    q0 = {'A': (1.0, -0.95), 'B': (0.9, -0.85)}[exp]
    z0 = np.array([q0[0]-qd[0], q0[1]-qd[1], 0.0, 0.0])
    print('experiment', exp, 'q0', q0, 'W(z0)', d.W(z0))
    res = {}
    pd = run_pd(z0, steps); report('PD+g', pd); res['PD'] = pd
    for N in Ns:
        t0 = time.time(); rec = run_mpc(z0, N, steps); rec['time'] = time.time()-t0
        report(f'N={N} ({rec["time"]:.0f}s)', rec); res[N] = rec
    pickle.dump(res, open(f'cl_{exp}_{sys.argv[2].replace(",", "_")}.pkl', 'wb'))
