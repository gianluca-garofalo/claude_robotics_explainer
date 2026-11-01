import numpy as np, scipy.linalg as sl
rng=np.random.default_rng(1); n=3; h=0.1
A=rng.normal(size=(n,n)); Q=A@A.T+np.eye(n); B=rng.normal(size=(n,n)); R=B@B.T+np.eye(n)
P=sl.solve_continuous_are(np.zeros((n,n)),np.eye(n),Q,R); Rh=R/h
def gain(X): return np.linalg.solve(Rh+X,Rh)
def T(X):
    K=gain(X); I=np.eye(n); return (K-I).T@Rh@(K-I)+K.T@X@K+h*Q
def Ld(q,qp): return 0.5*(qp-q)@Rh@(qp-q)+0.5*h*q@Q@q
X=P.copy()
for _ in range(5000): X=T(X)
cst=np.linalg.eigvals(np.linalg.solve(P,X)).real.max(); print("c*=%.4f"%cst)
for c in [cst,1.5,3.0]:
  for N in [1,2,3,5,8]:
    Vs=[c*P]
    for j in range(N): Vs.append(T(Vs[-1]))
    VN=Vs[N]; K=gain(Vs[N-1]); worst=-np.inf
    for trial in range(20):
      q=rng.normal(size=n)
      for k in range(30):
        qp=K@q; gap=(qp@VN@qp-q@VN@q)/2+Ld(q,qp); worst=max(worst,gap/(q@q)); q=qp
    print(f"c={c:.3f} N={N}: max (dV+Ld)/|q|^2 = {worst:.2e}", "OK" if worst<=1e-12 else "VIOLATED")
