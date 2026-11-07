"""Numbers of episode 1, computed here from the closed forms of the scalar example and cross-checked against the
companion logs when they are present (no scene class: render_video.sh skips this file).

Example (explainer: running example (3), rectangle rule (4), recursion (6), window problem (5)):
    L = 1/2 m v^2 + 1/2 kappa q^2 with m = kappa = 1, step h, rectangle rule
    L_d(q, q') = m/(2h) (q' - q)^2 + h/2 kappa q^2,  boundary term W = c * 1/2 q^2,  start q0.
For a quadratic V_{k}(q) = 1/2 P_k q^2 the recursion V_{k+1} = min_q' {L_d + V_k} is the scalar Riccati map
    P_{k+1} = P_k / (1 + h P_k) + h,  successor q' = q / (1 + h P_k)   (m = kappa = 1),
which is exactly what code/merged/window_split.py iterates and code/note/sec4_3_one_step_example.py minimizes
numerically. The inputs below are the example's parameters (as stated in both scripts); every derived number is
computed, and checked against code/logs/ to six decimals when those logs exist.
"""
import os
import re

M = KAPPA = 1.0      # mass and stiffness of the running example
H = 0.1              # step length
C = 1.2              # boundary weight: W = C * 1/2 q^2 (the rectangle-rule pair that passes the one-step test)
Q0 = 1.0             # start
WINDOWS = (1, 2, 5, 10, 20)

_LOGS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "code", "logs")


def Ld(q, qn):
    """Rectangle-rule discrete Lagrangian of the example."""
    return M / (2 * H) * (qn - q) ** 2 + H / 2 * KAPPA * q * q


def W(q):
    return C * 0.5 * q * q


def riccati(n):
    """[P_0, ..., P_n] of V_k = 1/2 P_k q^2, starting from W."""
    ps = [C]
    for _ in range(n):
        ps.append(ps[-1] / (1 + H * ps[-1]) + H)
    return ps


def V(n, q):
    return 0.5 * riccati(n)[n] * q * q


def successor(q, p_next):
    """Minimizer q' of L_d(q, q') + 1/2 p_next q'^2."""
    return q / (1 + H * p_next)


def split(n, q=Q0):
    """(V_n(q), window part, tail part W(q_n)) along the optimal n-step path."""
    ps = riccati(n)
    x, window = q, 0.0
    for j in range(n):
        xn = successor(x, ps[n - j - 1])
        window += Ld(x, xn)
        x = xn
    return 0.5 * ps[n] * q * q, window, W(x)


# One step of the one-window scheme from Q0
Q1 = successor(Q0, riccati(0)[0])
V1_Q0, W_Q0 = V(1, Q0), W(Q0)
LD_STEP = Ld(Q0, Q1)
DROP = V(1, Q1) - V(1, Q0)                     # negative: the remaining action falls
SPLITS = {n: split(n) for n in WINDOWS}
P_D = (H + (H * H + 4) ** 0.5) / 2              # fixed point of the Riccati map: the true remaining action is P_d/2


def closed_loop(steps, q=Q0):
    """The one-step-window scheme from q, step after step: [(q_k, V_1(q_k), L_d(q_k, q_k+1), V_1(q_k+1) - V_1(q_k))].
    The hook's meter shows V_1 (what is left to pay) and each step's cost L_d; the drop is never smaller."""
    out = []
    for _ in range(steps):
        qn = successor(q, riccati(0)[0])
        out.append((q, V(1, q), Ld(q, qn), V(1, qn) - V(1, q)))
        q = qn
    return out


def v1_with(c, q=Q0):
    """(V_1(q), W(q)) of the one-step window with the boundary weight c (W = c * 1/2 q^2): the one-step test."""
    p1 = c / (1 + H * c) + H
    return 0.5 * p1 * q * q, c * 0.5 * q * q


V1_TEXTBOOK, W_TEXTBOOK = v1_with(1.0)          # the textbook weight W = 1/2 q^2: the test fails by a hair
LOOP = closed_loop(16)
assert all(-d >= c for _, _, c, d in LOOP)      # the one-step test at work: every drop covers the step's cost


def _check():
    """Compare with the companion logs (six decimals), when they exist; raise on any mismatch."""
    f = os.path.join(_LOGS, "note__sec4_3_one_step_example.py.log")
    if os.path.exists(f):
        txt = open(f, encoding="utf-8").read()
        block = txt.split(f"rect {C}")[1]
        m = re.search(r"q=([-\d.]+) q\+=([-\d.]+) V1=([-\d.]+) W=([-\d.]+) Ld=([-\d.]+) dV=([-\d.]+)", block)
        got = [float(g) for g in m.groups()]
        want = [Q0, Q1, V1_Q0, W_Q0, LD_STEP, DROP]
        assert all(abs(a - b) < 2e-6 for a, b in zip(got, want)), (got, want)
        rows = re.findall(r"q=([-\d.]+) q\+=([-\d.]+) V1=([-\d.]+) W=[-\d.]+ Ld=([-\d.]+) dV=([-\d.]+)", block)[:4]
        for (q, qn, v1, ld, dv), mine in zip(rows, LOOP):    # the four logged closed-loop steps
            assert all(abs(float(a) - b) < 2e-6 for a, b in zip((q, v1, ld, dv), mine)), (q, mine)
        m = re.search(r"V1=([-\d.]+) W=([-\d.]+)", txt.split("rect 1.0")[1])
        assert abs(float(m.group(1)) - V1_TEXTBOOK) < 2e-6 and abs(float(m.group(2)) - W_TEXTBOOK) < 2e-6, m.groups()
    f = os.path.join(_LOGS, "merged__window_split.py.log")
    if os.path.exists(f):
        txt = open(f, encoding="utf-8").read()
        block = txt.split("(b) rectangle")[1]
        rows = {int(a): (float(b), float(c), float(d)) for a, b, c, d in
                re.findall(r"^\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", block, re.M)}
        for n in WINDOWS:
            assert all(abs(a - b) < 2e-6 for a, b in zip(rows[n], SPLITS[n])), (n, rows[n], SPLITS[n])
        pd = float(re.search(r"P_d/2 = ([\d.]+)", txt).group(1))
        assert abs(pd - P_D / 2) < 1e-9, (pd, P_D / 2)


_check()
