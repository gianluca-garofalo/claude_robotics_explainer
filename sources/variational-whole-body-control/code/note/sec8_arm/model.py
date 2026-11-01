"""Two-link planar arm (point masses at link tips, vertical plane), vectorized numpy model."""
import numpy as np

l1, l2, m1, m2, g0 = 0.5, 0.4, 2.0, 1.5, 9.81
qd = np.array([np.pi/4, -np.pi/4])
TAU_MAX = np.array([50.0, 30.0])


def Mmat(q):
    q = np.asarray(q, float)
    c2 = np.cos(q[..., 1])
    M11 = m1*l1**2 + m2*(l1**2 + l2**2 + 2*l1*l2*c2)
    M12 = m2*(l2**2 + l1*l2*c2)
    M22 = m2*l2**2*np.ones_like(c2)
    return np.stack([np.stack([M11, M12], -1), np.stack([M12, M22], -1)], -2)


def Cmat(q, v):
    h = m2*l1*l2*np.sin(q[..., 1])
    z = np.zeros_like(h)
    return np.stack([np.stack([-h*v[..., 1], -h*(v[..., 0]+v[..., 1])], -1),
                     np.stack([h*v[..., 0], z], -1)], -2)


def gvec(q):
    g1 = (m1+m2)*g0*l1*np.cos(q[..., 0]) + m2*g0*l2*np.cos(q[..., 0]+q[..., 1])
    g2 = m2*g0*l2*np.cos(q[..., 0]+q[..., 1])
    return np.stack([g1, g2], -1)


def mv(A, x):
    return np.einsum('...ij,...j->...i', A, x)


def dot(a, b):
    return np.einsum('...i,...i->...', a, b)


class Design:
    """Lambda, K_e, Q_e, Q_v, R (all 2x2)."""
    def __init__(self, Lam, Ke, Qe, Qv, R, name=''):
        self.Lam, self.Ke, self.Qe, self.Qv, self.R = map(np.asarray, (Lam, Ke, Qe, Qv, R))
        self.Rinv = np.linalg.inv(self.R)
        self.name = name

    # z = (e1, e2, edot1, edot2)
    def s(self, z):
        return z[..., 2:] + mv(self.Lam, z[..., :2])

    def W(self, z):
        e, v = z[..., :2], z[..., 2:]
        s = self.s(z)
        return 0.5*dot(s, mv(Mmat(qd+e), s)) + 0.5*dot(e, mv(self.Ke, e))

    def lx(self, z):
        e, v = z[..., :2], z[..., 2:]
        return 0.5*dot(e, mv(self.Qe, e)) + 0.5*dot(v, mv(self.Qv, v))

    def ell(self, z, u):
        return self.lx(z) + 0.5*dot(u, mv(self.R, u))

    def a(self, z):
        e, v = z[..., :2], z[..., 2:]
        q = qd + e
        return mv(Cmat(q, v), mv(self.Lam, e)) + mv(Mmat(q), mv(self.Lam, v))

    def Wdot(self, z, u):
        e, v = z[..., :2], z[..., 2:]
        s = self.s(z)
        return dot(s, u) + dot(s, self.a(z)) + dot(e, mv(self.Ke, v))

    def uref(self, z):
        return -mv(self.Rinv, self.s(z))

    def D(self, z):
        e, v = z[..., :2], z[..., 2:]
        s = self.s(z)
        return self.lx(z) - 0.5*dot(s, mv(self.Rinv, s)) + dot(s, self.a(z)) + dot(e, mv(self.Ke, v))


def step(z, u, h):
    """Semi-implicit (symplectic) Euler for M qdd + C qd = u  (u = tau - g)."""
    e, v = z[..., :2], z[..., 2:]
    q = qd + e
    acc = np.linalg.solve(Mmat(q), (u - mv(Cmat(q, v), v))[..., None])[..., 0]
    v1 = v + h*acc
    e1 = e + h*v1
    return np.concatenate([e1, v1], -1)


def rhs(z, u):
    e, v = z[..., :2], z[..., 2:]
    q = qd + e
    acc = np.linalg.solve(Mmat(q), (u - mv(Cmat(q, v), v))[..., None])[..., 0]
    return np.concatenate([v, acc], -1)
