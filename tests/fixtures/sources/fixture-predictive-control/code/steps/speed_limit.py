"""Fixture script (tests only): the hilltop with a speed limit |v| <= vbar, standard library only.

With m = kappa = 1 and vbar = 0.4 the clipped law moves at the limit until q reaches q_s = vbar / omega, then follows
the free extremal. Prints the cost of the clipped law from q0 = 1, in closed form and by integration, and how much
more than the unconstrained V(1) it costs.
"""
import math

m, kappa, q0, vbar = 1.0, 1.0, 1.0, 0.4
omega = math.sqrt(kappa / m)
qs = vbar / omega
T = (q0 - qs) / vbar                               # time at the speed limit
closed = 0.5 * m * vbar ** 2 * T + 0.5 * kappa * (q0 ** 3 - qs ** 3) / (3 * vbar) + 0.5 * math.sqrt(m * kappa) * qs ** 2

dt, total, q = 1.0e-5, 0.0, q0
while q > qs:
    total += (0.5 * m * vbar ** 2 + 0.5 * kappa * (q - vbar * dt / 2) ** 2) * dt
    q -= vbar * dt
total += 0.5 * math.sqrt(m * kappa) * qs ** 2

print(f"switch point q_s = {qs:.6f}")
print(f"cost of the clipped law from q0 = 1 = {closed:.6f}")
print(f"cost by integration = {total:.6f}")
print(f"extra cost of the speed limit = {closed - 0.5 * math.sqrt(m * kappa) * q0 ** 2:.6f}")
