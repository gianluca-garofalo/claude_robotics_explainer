"""Fixture script (tests only): the hilltop, standard library only.

Cost L = 1/2 m v^2 + 1/2 kappa q^2 (kinetic minus the potential of an inverted parabola). The stable extremal is
q(t) = q0 exp(-omega t) with omega = sqrt(kappa / m), and the cost still to pay is V(q) = 1/2 sqrt(m kappa) q^2.
Prints omega, V(q0), the integral of L along the extremal (midpoint rule, 0 to 40 s) and the Hamiltonian at
p = -V'(q), which is zero.
"""
import math

m, kappa, q0 = 1.0, 1.0, 1.0
omega = math.sqrt(kappa / m)
V = 0.5 * math.sqrt(m * kappa) * q0 ** 2

dt, total, t = 1.0e-4, 0.0, 0.0
while t < 40.0:
    tm = t + dt / 2
    q = q0 * math.exp(-omega * tm)
    v = -omega * q
    total += (0.5 * m * v * v + 0.5 * kappa * q * q) * dt
    t += dt

p = -math.sqrt(m * kappa) * q0
H = p * p / (2 * m) - 0.5 * kappa * q0 * q0

print(f"omega = {omega:.6f}")
print(f"V(q0) = {V:.6f}")
print(f"integral of L along the extremal = {total:.6f}")
print(f"H(q0, -V'(q0)) = {abs(H):.1e}")
