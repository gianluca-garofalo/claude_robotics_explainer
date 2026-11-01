import sympy as sp, numpy as np, scipy.integrate as si, scipy.linalg as sl
m, k, d, T = sp.symbols('m k delta T', positive=True); x, v, tau = sp.symbols('x v tau', real=True)
# --- C: 1-DOF, V = 1/2 m v^2 + 1/2 k x^2, stage cost (T/2) tau^2/m (Gauss with time scale T), tau held (ZOH)
xe = x + v*d + tau*d**2/(2*m); ve = v + tau*d/m
J = d*T*tau**2/(2*m) + m*ve**2/2 + k*xe**2/2
t_exact = sp.solve(sp.diff(J, tau), tau)[0]
print("C exact ZOH  tau* =", sp.simplify(t_exact))
print("C O(delta) truncation:", sp.simplify(sp.series(t_exact, d, 0, 2).removeO()))
print("   claimed: -(m v + (delta/2) k x)/(delta + T)  series:", sp.simplify(sp.series(-(m*v + d*k*x/2)/(d+T), d, 0, 2).removeO()))
# impulse-type hold: velocity jumps at t=0 by tau*d/m, then coasts: x(d) = x + (v + tau d/m) d
xe2 = x + (v + tau*d/m)*d
J2 = d*T*tau**2/(2*m) + m*ve**2/2 + k*xe2**2/2
t2 = sp.solve(sp.diff(J2, tau), tau)[0]
print("C impulse hold tau* O(delta):", sp.simplify(sp.series(t2, d, 0, 2).removeO()))
# optimal time-varying u on [0,d] (LQ, terminal cost V, stage (T/2) u^2/m): Riccati, first-instant torque
Ac = np.array([[0, 1], [0, 0.]]); mm, kk, TT = 2.0, 30.0, 0.1; B = np.array([[0], [1/mm]]); Rr = TT/mm
PV = np.diag([kk, mm])
def ric(t, p):
    P = p.reshape(2, 2); return (Ac.T@P + P@Ac - P@B@B.T@P/Rr).ravel()
for dd in [1e-3, 1e-2, 5e-2]:
    sol = si.solve_ivp(ric, [0, dd], PV.ravel(), rtol=1e-12, atol=1e-12)   # backward time = forward in tau-to-go
    P0 = sol.y[:, -1].reshape(2, 2); K0 = (B.T@P0/Rr).ravel()     # u(0) = -K0 z
    # ZOH optimum gains at same params
    tz = sp.lambdify((x, v), t_exact.subs({m: mm, k: kk, d: dd, T: TT}))
    kz = -(tz(1, 0) - tz(0, 0)); dz = -(tz(0, 1) - tz(0, 0))
    print(f"C delta={dd:5.0e}: optimal u(0): stiff={K0[0]:.4f} damp={K0[1]:.4f} | ZOH: stiff={kz:.4f} damp={dz:.4f} | k*d/(d+T)={kk*dd/(dd+TT):.4f}")

# --- F: multiple shooting, 1-DOF, N=3 nodes, two transcriptions; compare tau0 with velocity-defect multiplier
def ms(transcription, N=3, h=0.05, mm=2.0, kk=30.0, TT=0.1, z0=(0.3, -0.2)):
    # vars: tau_0..N-1, x_1..N, v_1..N ; cost sum h*T/(2m) tau^2 + V(x_N,v_N); equality defects
    nv = 3*N; H = np.zeros((nv, nv));
    it = lambda i: i; ix = lambda i: N + i - 1; iv = lambda i: 2*N + i - 1
    for i in range(N): H[it(i), it(i)] = h*TT/mm
    H[ix(N), ix(N)] = kk; H[iv(N), iv(N)] = mm
    Aeq = []; beq = []
    for i in range(N):
        rowx = np.zeros(nv); rowv = np.zeros(nv); cx = 0; cv = 0
        # previous state
        def add(row, j, c, xv):   # coefficient c for x_j (xv=0) or v_j (xv=1); j=0 known
            nonlocal cx, cv
        xprev = (None if i == 0 else ix(i)); vprev = (None if i == 0 else iv(i))
        # velocity defect: v_{i+1} - v_i - h tau_i/m = 0
        rowv[iv(i+1)] = 1; rowv[it(i)] = -h/mm
        if vprev is None: cv += z0[1]
        else: rowv[vprev] = -1
        # position defect
        rowx[ix(i+1)] = 1
        if transcription == 'zoh':          # exact: x+ = x + h v + h^2/(2m) tau
            rowx[it(i)] = -h**2/(2*mm)
            if vprev is None: cx += h*z0[1]
            else: rowx[vprev] = -h
        else:                               # symplectic Euler: x+ = x + h v+
            rowx[iv(i+1)] = -h
        if xprev is None: cx += z0[0]
        else: rowx[xprev] = -1
        Aeq += [rowx, rowv]; beq += [cx, cv]
    Aeq = np.array(Aeq); beq = np.array(beq); ne = len(beq)
    K = np.block([[H, Aeq.T], [Aeq, np.zeros((ne, ne))]])
    sol = np.linalg.solve(K, np.concatenate([np.zeros(nv), beq]))
    w = sol[:nv]; mu = sol[nv:]   # H w + Aeq^T mu = 0 ; mu = multipliers (= nabla V convention, pi = -mu)
    mu_x1, mu_v1 = mu[0], mu[1]
    return w[0], mu_x1, mu_v1
for tr in ['zoh', 'symp']:
    t0, mx, mvv = ms(tr); h = 0.05; mm = 2.0; TT = 0.1
    # stationarity: (h T/m) tau0 + coeffs = 0 ; pi_v1 = -mu_v1 ; claim tau0 = R^-1 M^-1 pi_v * (scaling)
    pred_v_only = -(h/mm)*(-1)*0
    print(f"F {tr}: tau0={t0:.5f}, from vel-multiplier only: {(-mvv*(-h/mm))/(-(h*TT/mm)) :.5f}, "
          f"pos-multiplier share: {(-mx*(-h**2/(2*mm)) if tr=='zoh' else 0)/(-(h*TT/mm)):.5f}")
