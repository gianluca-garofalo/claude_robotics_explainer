"""Fixture script (tests only): one window step on the hilltop and the scaled candidates, standard library only.

With m = kappa = 1 the stable extremal shrinks q by exp(-omega h) per step. With the exact pair (boundary term
W = V and the step's cost computed exactly) the descent V(q+) - V(q) + L_d(q, q+) is zero. For the scaled
candidates W = cV the Hamiltonian H(q, -W') equals 1/2 kappa q^2 (c^2 - 1): the certificate holds for c >= 1.
"""
import math

m, kappa, q, h = 1.0, 1.0, 1.0, 0.1
omega = math.sqrt(kappa / m)


def V(x):
    return 0.5 * math.sqrt(m * kappa) * x * x


q_next = math.exp(-omega * h) * q
step_cost = V(q) - V(q_next)                     # the action of the extremal over one step
print(f"decay factor exp(-omega h) = {math.exp(-omega * h):.6f}")
print(f"V(q+) = {V(q_next):.6f}")
print(f"step cost L_d(q, q+) = {step_cost:.6f}")
print(f"descent defect with the exact pair = {abs(V(q_next) - V(q) + step_cost):.1e}")
for c in (0.5, 1.0, 2.0):
    print(f"c = {c:.1f}: H(q, -cV') = {0.5 * kappa * q * q * (c * c - 1):.6f}")
