"""Exact small-z limit of the discrete condition (4): needed inflation c_W = lambda_max(h L, P - Ad^T P Ad)."""
import numpy as np, scipy.linalg as sla
from model import *
from condcheck import designs
d = designs()['good']
M0 = Mmat(qd); Lam, KD = d.Lam, d.Rinv
P = np.block([[Lam@M0@Lam + d.Ke, Lam@M0], [M0@Lam, M0]])     # Hessian of W at 0
# linear closed loop u = -KD s = -KD(Lam e + v) ; M0 vdot = u
Kz = np.hstack([-KD@Lam, -KD])
for h in [0.01, 0.005, 0.0025, 0.001]:
    Bv = h*np.linalg.solve(M0, Kz)        # v+ = v + Bv z
    Av = np.hstack([np.zeros((2, 2)), np.eye(2)]) + Bv
    Ae = np.hstack([np.eye(2), np.zeros((2, 2))]) + h*Av
    Ad = np.vstack([Ae, Av])
    Lz = np.block([[d.Qe, 0*M0], [0*M0, d.Qv]]) + Kz.T@d.R@Kz
    Dm = P - Ad.T@P@Ad
    ev = np.linalg.eigvalsh(Dm)
    lam = sla.eigh(h*Lz, Dm, eigvals_only=True)
    print(f'h={h}: P - Ad^T P Ad > 0? min eig {ev.min():.3e};  needed c_W (quadratic limit) = {lam.max():.5f};'
          f' spectral radius Ad = {max(abs(np.linalg.eigvals(Ad))):.5f}')
# continuous closed-loop eigenvalues (fast mode)
Acl = np.block([[np.zeros((2, 2)), np.eye(2)], [np.linalg.solve(M0, Kz)]])
print('continuous closed-loop eigenvalues:', np.sort(np.linalg.eigvals(Acl)))
P_ = P; print('W Hessian P eig', np.linalg.eigvalsh(P_))
