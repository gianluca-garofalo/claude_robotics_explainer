"""Cross-check the hand-written two-link arm model of Section 8 against Pinocchio.

Builds the same arm (point masses at the link tips, revolute joints about z, gravity along -y)
with Pinocchio and compares M(q), C(q, qdot), g(q) and the skew-symmetry of Mdot - 2C.
"""
import numpy as np
import pinocchio as pin
from model import Mmat, Cmat, gvec, l1, l2, m1, m2, g0

model = pin.Model()
j1 = model.addJoint(0, pin.JointModelRZ(), pin.SE3.Identity(), "joint1")
model.appendBodyToJoint(j1, pin.Inertia(m1, np.array([l1, 0.0, 0.0]), np.zeros((3, 3))), pin.SE3.Identity())
j2 = model.addJoint(j1, pin.JointModelRZ(), pin.SE3(np.eye(3), np.array([l1, 0.0, 0.0])), "joint2")
model.appendBodyToJoint(j2, pin.Inertia(m2, np.array([l2, 0.0, 0.0]), np.zeros((3, 3))), pin.SE3.Identity())
model.gravity.linear = np.array([0.0, -g0, 0.0])
data = model.createData()

rng = np.random.default_rng(0)
errM = errC = errG = errSkew = 0.0
for _ in range(1000):
    q = rng.uniform(-np.pi, np.pi, 2)
    v = rng.normal(size=2) * 3
    M_pin = pin.crba(model, data, q); M_pin = np.triu(M_pin) + np.triu(M_pin, 1).T
    C_pin = pin.computeCoriolisMatrix(model, data, q, v)
    g_pin = pin.computeGeneralizedGravity(model, data, q)
    errM = max(errM, np.abs(M_pin - Mmat(q)).max())
    errC = max(errC, np.abs(C_pin - Cmat(q, v)).max())
    errG = max(errG, np.abs(g_pin - gvec(q)).max())
    # Mdot along v by central difference, then skew-symmetry of Mdot - 2C
    eps = 1e-6
    Mdot = (Mmat(q + eps * v) - Mmat(q - eps * v)) / (2 * eps)
    S = Mdot - 2 * Cmat(q, v)
    errSkew = max(errSkew, np.abs(S + S.T).max())

print(f"Pinocchio {pin.__version__}: max |M - M_pin| = {errM:.2e}, max |C - C_pin| = {errC:.2e}, "
      f"max |g - g_pin| = {errG:.2e}, max |(Mdot-2C) + (Mdot-2C)^T| = {errSkew:.2e}  (1000 random states)")
