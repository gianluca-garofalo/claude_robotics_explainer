import sympy as sp, numpy as np, scipy.linalg as sl
from scipy.optimize import minimize_scalar

# ---- 5.3 symbolic
x,x0,t,m,k,p,h,q,qq=sp.symbols('x x0 t m k p h q qq',positive=True)
w=sp.sqrt(k/m)
V=sp.Rational(1,2)*sp.sqrt(m*k)*x**2
H=lambda X,P: P**2/(2*m)-k*X**2/2
print('HJ:',sp.simplify(H(x,-sp.diff(V,x))))
xt=x0*sp.exp(-w*t); L=m*sp.diff(xt,t)**2/2+k*xt**2/2
print('int L:',sp.simplify(sp.integrate(L,(t,0,sp.oo))-V.subs(x,x0)))
print('eig:',sp.Matrix([[0,1/m],[k,0]]).eigenvals())
print('p on extremal + V\':',sp.simplify(m*sp.diff(xt,t)+sp.diff(V,x).subs(x,xt)))
# time-to-go value with W=0: V_tau = 1/2 sqrt(mk) tanh(w tau) x^2 ; check dV/dtau = -H(x,-V')
tau=sp.symbols('tau',positive=True)
Vt=sp.Rational(1,2)*sp.sqrt(m*k)*sp.tanh(w*tau)*x**2
print('time-to-go: dV/dtau + H =',sp.simplify(sp.diff(Vt,tau)+H(x,-sp.diff(Vt,x))))
# exact discrete Lagrangian
Sd=sp.sqrt(m*k)/(2*sp.sinh(w*h))*((q**2+qq**2)*sp.cosh(w*h)-2*q*qq)
J=Sd+sp.Rational(1,2)*sp.sqrt(m*k)*qq**2
qs=sp.solve(sp.diff(J,qq),qq)[0]
print('exact Ld: q* =',sp.simplify(qs.rewrite(sp.exp)), ' V1-W =',sp.simplify((J.subs(qq,qs)-sp.Rational(1,2)*sp.sqrt(m*k)*q**2).rewrite(sp.exp)))
print('D2Ld+W\' at q*:',sp.simplify(sp.diff(Sd,qq).subs(qq,qs)+sp.sqrt(m*k)*qs))

# ---- numerics, m=k=1, h
def run(mm,kk,hh,q0=1.0,steps=6):
    om=np.sqrt(kk/mm); P=np.sqrt(mm*kk)
    Ldr=lambda a,b: 0.5*mm*(b-a)**2/hh+0.5*hh*kk*a**2
    Lde=lambda a,b: P/(2*np.sinh(om*hh))*((a*a+b*b)*np.cosh(om*hh)-2*a*b)
    # DARE for rectangle: x+=x+h u, cost h(1/2 m u^2+1/2 k x^2)
    Pd=sl.solve_discrete_are(np.array([[1.]]),np.array([[hh]]),np.array([[hh*kk]]),np.array([[hh*mm]]))[0,0]
    print(f'\nm={mm},k={kk},h={hh}: P_CARE={P:.6f}, P_DARE(rect)={Pd:.6f}')
    for name,Ld in [('exact',Lde),('rect',Ldr)]:
        W=lambda z:0.5*P*z*z
        qk=q0; rows=[]
        for i in range(steps):
            r=minimize_scalar(lambda b:Ld(qk,b)+W(b),bracket=(-2,2),tol=1e-14)
            V1=r.fun; qn=r.x
            rows.append((i,qk,qn,V1,W(qk),Ld(qk,qn)))
            qk=qn
        print(name,' exact-flow ratio e^{-wh}=',np.exp(-om*hh))
        for i,a,b,v1,wq,ld in rows: print(f'  k={i} q={a:.6f} q+={b:.6f} ratio={b/a:.6f} V1={v1:.6f} W(q)={wq:.6f} Ld={ld:.6f}')
        V1s=[r[3] for r in rows]; print('  V1 diffs:',np.round(np.diff(V1s),6),' -Ld:',np.round([-r[5] for r in rows[:-1]],6))
    # Assumption 2 with W=c*P/2 q^2 for rect L_d and linear phi_f(q)=rho q: min over rho of c/2 P (rho^2-1)+Ldr(1,rho)
    for c in [1.0,1.05,1.2,Pd/P]:
        g=lambda rho: 0.5*c*P*(rho**2-1)+Ldr(1.0,rho)
        r=minimize_scalar(g,bracket=(0,1)); print(f'  rect, W=c*CARE c={c:.4f}: min_rho [dW+Ld]={r.fun:.6f} (need <=0) at rho={r.x:.4f}')
    g=lambda rho: 0.5*P*(rho**2-1)+Lde(1.0,rho); r=minimize_scalar(g,bracket=(0,1))
    print(f'  exact Ld, W=CARE: min_rho={r.fun:.2e} at rho={r.x:.6f}')
run(1,1,0.1); run(1,1,0.5)

# ---- Section 4 with V=c V*, 3-D
rng=np.random.default_rng(0)
A=rng.normal(size=(3,3));Q=A@A.T+np.eye(3);B=rng.normal(size=(3,3));R=B@B.T+np.eye(3)
P=sl.solve_continuous_are(np.zeros((3,3)),np.eye(3),Q,R)
print('\nCARE residual PR^-1P-Q:',np.abs(P@np.linalg.solve(R,P)-Q).max())
Ham=np.block([[np.zeros((3,3)),np.linalg.inv(R)],[Q,np.zeros((3,3))]])
ev,EV=np.linalg.eig(Ham); S=EV[:,ev.real<0]; print('stable subspace p=-Pq residual:',np.abs(S[3:]+P@S[:3]).max())
qv=rng.normal(size=3)
for c in [0.5,0.9,1,1.3,2]:
    gV=c*P@qv; pv=-gV; v=np.linalg.solve(R,pv)
    Lv=0.5*v@R@v+0.5*qv@Q@qv; Hv=0.5*pv@np.linalg.solve(R,pv)-0.5*qv@Q@qv
    print(f' c={c}: Vdot={gV@v:.4f} -L-H={-Lv-Hv:.4f} H={Hv:.4f} Vdot<=-L:{gV@v<=-Lv+1e-12} Vdot<0:{gV@v<0}')
# nonuniqueness of PR^-1P=Q (A=0,B=I): sign flips
Rh=sl.sqrtm(R).real; Ri=np.linalg.inv(Rh); M=Ri@Q@Ri; e,U=np.linalg.eigh(M)
for s in [(1,1,1),(1,1,-1),(-1,-1,-1)]:
    Ps=Rh@U@np.diag(np.array(s)*np.sqrt(e))@U.T@Rh
    print(' sign',s,'residual',np.abs(Ps@np.linalg.solve(R,Ps)-Q).max(),'eig(P)',np.round(np.linalg.eigvalsh(Ps),3))
