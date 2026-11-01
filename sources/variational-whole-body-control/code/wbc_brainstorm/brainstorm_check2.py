import sympy as sp
x,v,tau,m,k,d,r=sp.symbols('x v tau m k delta r',real=True)
a=tau/m
xT=x+d*v+d**2*a/2; vT=v+d*a
J=d*r*tau**2/(2*m)+sp.Rational(1,2)*m*vT**2+sp.Rational(1,2)*k*xT**2
ts=sp.solve(sp.diff(J,tau),tau)[0]
print("exact argmin tau:",sp.simplify(ts))
print("series in delta:",sp.series(ts,d,0,3))
# second-order expansion only (drop k*delta^4 term) -> impedance form
J2=sp.series(J,d,0,3).removeO()
ts2=sp.solve(sp.diff(J2,tau),tau)[0]
print("2nd-order-expansion argmin:",sp.simplify(ts2))
