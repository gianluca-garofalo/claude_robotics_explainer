"""Window length moves the split between the computed window and the estimated tail.

Scalar example of Sections 4.3 and 14.2: L = 1/2 v^2 + 1/2 q^2 (m = kappa = 1), step h = 0.1,
start q0 = 1, no constraints.  For each window length N we solve the N-step problem
    V_N(q0) = min sum_{j<N} L_d(q_j, q_{j+1}) + W(q_N)
exactly (scalar Riccati recursion) and split V_N(q0) into the window part (sum of L_d along
the optimal N-step path) and the tail part W(q_N).

  pair (a): exact discrete Lagrangian L_d^E with W = 1/2 q^2  (W equals V_infinity)
  pair (b): rectangle rule  L_d = (q'-q)^2/(2h) + h q^2/2  with W = 1.2 * 1/2 q^2

Expected: in (a) V_N(q0) = 0.5 for every N (only the split moves); in (b) V_N(q0) decreases
with N towards the discrete-Riccati value P_d/2 = 0.525625 (descent of the total, by (4)).
"""
import numpy as np

h, q0 = 0.1, 1.0
w = 1.0                                   # omega = sqrt(kappa/m)


def exact_pair(N):
    # quadratic form of L_d^E: (sqrt(m k)/(2 sinh wh)) [ (q^2+q'^2) cosh wh - 2 q q' ]
    a = np.cosh(w*h)/(2*np.sinh(w*h)); b = -1.0/(2*np.sinh(w*h))
    P = 1.0                                   # W = 1/2 P q^2 with P = 1 (continuous Riccati)
    Ps = [P]
    for _ in range(N):                        # V_{k+1}(q) = min_q' [L_d(q,q') + 1/2 P_k q'^2]
        # L_d = a q^2 + 2 b q q' + a q'^2 ; minimize over q'
        Pk = Ps[-1]
        qq = -2*b/(2*a + Pk)                  # q' = qq * q
        Ps.append(2*(a + 2*b*qq + a*qq**2) + Pk*qq**2)
    return Ps, lambda q, Pk: (-2*b/(2*a + Pk))*q, lambda q, qn: a*q*q + 2*b*q*qn + a*qn*qn


def rect_pair(N, c=1.2):
    P = c*1.0
    Ps = [P]
    for _ in range(N):
        Pk = Ps[-1]
        Ps.append(Pk/(1 + h*Pk) + h)          # V_{k+1}: P_{k+1} = P_k/(1+h P_k) + h
    return Ps, lambda q, Pk: q/(1 + h*Pk), lambda q, qn: (qn - q)**2/(2*h) + h*q*q/2


def split(pair, N):
    Ps, step, Ld = pair(N)
    # optimal N-step path from q0: at stage j (N-j steps to go) use P_{N-j-1} for the successor
    q = q0; window = 0.0
    for j in range(N):
        qn = step(q, Ps[N - j - 1])
        window += Ld(q, qn); q = qn
    tail = 0.5*Ps[0]*q*q
    return 0.5*Ps[N]*q0*q0, window, tail


print("P_d (rectangle rule, h=0.1) =", (h + np.sqrt(h*h + 4))/2, " -> P_d/2 =", (h + np.sqrt(h*h + 4))/4)
for name, pair in [("(a) exact L_d, W = 1/2 q^2", exact_pair), ("(b) rectangle L_d, W = 1.2*1/2 q^2", rect_pair)]:
    print("\n" + name)
    print("   N    V_N(q0)    window    tail     window+tail-V_N")
    for N in [1, 2, 5, 10, 20, 50]:
        V, win, tail = split(pair, N)
        print(f"  {N:3d}  {V:.6f}  {win:.6f}  {tail:.6f}  {win + tail - V:+.1e}")
