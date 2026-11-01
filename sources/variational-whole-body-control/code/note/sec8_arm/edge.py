import numpy as np
from condcheck import designs, M0, KD, Lam
ds = designs()
lam = 2.0
# SL proof check (Q=0): Hessian eigenvalues
from model import Design
for Q0 in [True]:
    dd = Design(Lam, 2*Lam@KD, 0*KD, 0*KD, ds['good'].R)
    from condcheck import quad_D
    A, H = quad_D(dd); print('SL with Q=0: eig Hessian D', np.linalg.eigvalsh(0.5*(A+A.T)))
    # Schur argument: K_D - 2 lam M0  vs  K_D + 2 lam M0 + lam^2 M0 K_D^-1 M0
    print('gap eig', np.linalg.eigvalsh((KD + 2*lam*M0 + lam**2*M0@np.linalg.inv(KD)@M0) - (KD - 2*lam*M0)))
# SL direction of ascent
dd = ds['SL']; A, H = quad_D(dd); w, V = np.linalg.eigh(0.5*(A+A.T)); vmax = V[:, -1]
print('SL: top eigvec', vmax, ' D(r v) for r=1e-3,1e-2,1e-1:', [dd.D(r*vmax) for r in [1e-3, 1e-2, 1e-1]],
      ' W:', [dd.W(r*vmax) for r in [1e-3, 1e-2, 1e-1]])
# edge: cubic coefficient max over directions
de = ds['edge']; rng = np.random.default_rng(0)
dirs = rng.normal(size=(200000, 4)); dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
r = 1e-3
kap = (de.D(r*dirs) - de.D(-r*dirs))/(2*r**3)
k = np.argmax(kap); print('edge: max cubic coeff', kap[k], 'dir', dirs[k])
for rr in [1e-3, 1e-2, 1e-1]:
    print('   r', rr, 'D(+)', de.D(rr*dirs[k]), 'D(-)', de.D(-rr*dirs[k]), 'W', de.W(rr*dirs[k]))
