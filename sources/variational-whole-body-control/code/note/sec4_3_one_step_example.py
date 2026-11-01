import numpy as np
m=k=1.0; h=0.1; w=np.sqrt(k/m)
def Ld_rect(q,qp): return m/(2*h)*(qp-q)**2 + h/2*k*q**2
def Ld_ex(q,qp):
    s=np.sinh(w*h); c=np.cosh(w*h); return np.sqrt(m*k)/(2*s)*((q*q+qp*qp)*c-2*q*qp)
def step(Ld,c,q):
    # quadratic in qp: minimize numerically via closed form using derivative
    from scipy.optimize import minimize_scalar
    r=minimize_scalar(lambda qp: Ld(q,qp)+0.5*c*qp**2, bounds=(-2,2), method='bounded', options={'xatol':1e-12})
    return r.x, r.fun
for name,Ld,c in [("exact",Ld_ex,1.0),("rect",Ld_rect,1.0),("rect",Ld_rect,1.2)]:
    q=1.0; print(name,c)
    for i in range(4):
        qp,V=step(Ld,c,q); qpp,Vp=step(Ld,c,qp)
        print(f"  q={q:.6f} q+={qp:.6f} V1={V:.6f} W={0.5*c*q*q:.6f} Ld={Ld(q,qp):.6f} dV={Vp-V:.6f} ok={Vp-V<=-Ld(q,qp)+1e-12}")
        q=qp
