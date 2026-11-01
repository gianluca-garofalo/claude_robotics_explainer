import numpy as np
exec(open(__import__('os').path.join(__import__('os').path.dirname(__import__('os').path.abspath(__file__)),'redteam_check_A_B.py')).read().split('# ---------- Case 1')[0])
rng=np.random.default_rng(3); dims=[2,3,2]; Js=[rng.standard_normal((d,n)) for d in dims]; A=np.vstack(Js)
qd=rng.standard_normal(n); lam=rng.standard_normal(n)
for order in ([0,1,2],[2,0,1]):
    Ao=np.vstack([Js[k] for k in order]); do=[dims[k] for k in order]
    L,D=block_ldl(Ao@Mi@Ao.T,do); Jb=np.linalg.solve(L,Ao); lo=np.concatenate([lam[sum(dims[:k]):sum(dims[:k+1])] for k in order])
    F=L.T@lo; v=Jb@qd; idx=np.cumsum([0]+do)
    print(order,"total power F.v - lam.xdot:",abs(F@v-lo@(Ao@qd)),"per-level F_i.v_i:",[round(F[idx[i]:idx[i+1]]@v[idx[i]:idx[i+1]],3) for i in range(3)])
