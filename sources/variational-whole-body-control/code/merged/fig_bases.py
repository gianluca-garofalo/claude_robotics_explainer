"""Figure 'One torque, two bases' (hierarchy section) and the numbers in its caption.

Two-link arm of the manipulator example at its target posture q_d = (pi/4, -pi/4).
Task 1 (higher priority): hand height y, Jacobian J_1 = dy/dq.  Task 2: elbow angle q_2, J_2 = (0, 1).
A constraint torque tau_c is produced by the stacked multipliers lambda = (2 N, 0.4 N m):
    tau_c = J_1^T lambda_1 + J_2^T lambda_2 = J_1^T F_1 + Jbar_2^T F_2,
with Jbar_2 = J_2 - Theta_21 J_1 (Gram-Schmidt in the M^-1 metric) and F = Theta^T lambda.
The drawing labels the torque tau_x, the task-channel torque of the document (Section 12.3); in this constraint
view tau_x = tau_c.
Writes fig_bases.svg (inline in the document) and prints every number quoted.
"""
import os
import numpy as np

l1, l2, m1, m2 = 0.5, 0.4, 2.0, 1.5
q = np.array([np.pi/4, -np.pi/4])
c2 = np.cos(q[1])
M = np.array([[m1*l1**2 + m2*(l1**2 + l2**2 + 2*l1*l2*c2), m2*(l2**2 + l1*l2*c2)],
              [m2*(l2**2 + l1*l2*c2), m2*l2**2]])
Mi = np.linalg.inv(M)
J1 = np.array([l1*np.cos(q[0]) + l2*np.cos(q[0] + q[1]), l2*np.cos(q[0] + q[1])])   # d(hand height)/dq
J2 = np.array([0.0, 1.0])                                                         # elbow angle
lam = np.array([2.0, 0.4])

Th21 = (J2 @ Mi @ J1)/(J1 @ Mi @ J1)
Jb2 = J2 - Th21*J1
F1, F2 = lam[0] + Th21*lam[1], lam[1]
tau = J1*lam[0] + J2*lam[1]
print("M(q_d) =", np.round(M, 4).tolist())
print("J_1 =", np.round(J1, 4), " J_2 =", J2)
print("Theta_21 = %.6f (1/l_2 = %.6f)" % (Th21, 1/l2))
print("Jbar_2 =", np.round(Jb2, 4), "  J_1 M^-1 Jbar_2^T =", f"{J1 @ Mi @ Jb2:.1e}")
print("tau_c =", np.round(tau, 4), "  check J1 F1 + Jbar2 F2 =", np.round(J1*F1 + Jb2*F2, 4))
print("lambda = (%.3f, %.3f)   F = (%.3f, %.3f)" % (lam[0], lam[1], F1, F2))
# F_1 is Newton's law for task 1: Lambda_1 times the task-1 acceleration that tau_c produces
Lam1 = 1/(J1 @ Mi @ J1)
print("Lambda_1 J_1 M^-1 tau_c = %.6f  (= F_1)" % (Lam1*(J1 @ Mi @ tau)))
# reversed order (elbow first): the hand-height task is last and carries its multiplier
Th12 = (J1 @ Mi @ J2)/(J2 @ Mi @ J2)
print("order 2 > 1: F_2' = lambda_2 + Theta'_21 lambda_1 = %.4f, F_1' = lambda_1 = %.4f" % (lam[1] + Th12*lam[0], lam[0]))
# power for a sample velocity
qd = np.array([0.5, -1.0])
xd = np.array([J1 @ qd, J2 @ qd]); zeta = np.array([J1 @ qd, Jb2 @ qd])
print("qdot =", qd, " stacked powers", np.round(lam*xd, 4), " decoupled powers", np.round(np.array([F1, F2])*zeta, 4),
      " totals %.4f %.4f %.4f" % ((lam*xd).sum(), F1*zeta[0] + F2*zeta[1], tau @ qd))

# ------------------------------------------------------------------ SVG
X0, Y0, S = 90.0, 330.0, 200.0           # origin (px) and px per N m
def P(v):
    return X0 + S*v[0], Y0 - S*v[1]
def fmt(v):
    x, y = P(v); return f"{x:.1f},{y:.1f}"
blue, amber, ink, grey, light = "#2563eb", "#d97706", "#0f172a", "#94a3b8", "#cbd5e1"
sub = lambda t: f'<tspan baseline-shift="sub" font-size="9">{t}</tspan>'
sup = lambda t: f'<tspan baseline-shift="super" font-size="9">{t}</tspan>'
JT = lambda i: f'J{sub(i)}{sup("T")}'
JbT = f'J&#773;{sub(2)}{sup("T")}'
out = []
w = out.append
w('<svg viewBox="0 0 640 380" role="img" aria-label="One constraint torque written in two bases: the stacked task Jacobians with multipliers lambda, and the dynamically consistent basis of the hierarchy with decoupled forces F. Both decompositions start along the hand-height direction but end along different second directions, so the first coefficients differ." style="width:100%;max-width:640px;height:auto;font-family:inherit">')
w('  <defs>')
for nm, col in [("fb-ab", blue), ("fb-aa", amber), ("fb-ak", ink), ("fb-ag", grey)]:
    w(f'    <marker id="{nm}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>')
w('  </defs>')
# axes
w(f'  <line x1="{X0-30:.0f}" y1="{Y0:.0f}" x2="625" y2="{Y0:.0f}" stroke="{grey}" marker-end="url(#fb-ag)"/>')
w(f'  <line x1="{X0:.0f}" y1="{Y0+30:.0f}" x2="{X0:.0f}" y2="14" stroke="{grey}" marker-end="url(#fb-ag)"/>')
w(f'  <text x="622" y="{Y0+22:.0f}" text-anchor="end" font-size="13" fill="#64748b">&#964;{sub(1)} (shoulder)</text>')
w(f'  <text x="{X0+8:.0f}" y="24" font-size="13" fill="#64748b">&#964;{sub(2)} (elbow)</text>')
# direction line of J1 through the origin, and the second directions through lam1*J1 and F1*J1
A1, B1 = lam[0]*J1, F1*J1
a, b = -0.1, 3.05
w(f'  <line x1="{P(a*J1)[0]:.1f}" y1="{P(a*J1)[1]:.1f}" x2="{P(b*J1)[0]:.1f}" y2="{P(b*J1)[1]:.1f}" stroke="{light}" stroke-width="1"/>')
# arc of the M^-1 level set through F1*J1, around the tangent point (shows M^-1-conjugacy)
r2 = B1 @ Mi @ B1
ev, U = np.linalg.eigh(Mi)
yB = U.T @ B1; t0 = np.arctan2(yB[1]*np.sqrt(ev[1]), yB[0]*np.sqrt(ev[0]))
pts = []
for t in np.linspace(t0 - 0.16, t0 + 0.16, 41):
    y = np.array([np.cos(t)/np.sqrt(ev[0]), np.sin(t)/np.sqrt(ev[1])])*np.sqrt(r2)
    pts.append(fmt(U @ y))
w(f'  <polyline points="{" ".join(pts)}" fill="none" stroke="{grey}" stroke-width="1.3" stroke-dasharray="4 3"/>')
# stacked decomposition (blue): 0 -> lam1 J1 -> tau
w(f'  <line x1="{X0:.1f}" y1="{Y0:.1f}" x2="{P(A1)[0]:.1f}" y2="{P(A1)[1]:.1f}" stroke="{blue}" stroke-width="2.4" marker-end="url(#fb-ab)"/>')
w(f'  <line x1="{P(A1)[0]:.1f}" y1="{P(A1)[1]:.1f}" x2="{P(tau)[0]:.1f}" y2="{P(tau)[1]:.1f}" stroke="{blue}" stroke-width="2.4" marker-end="url(#fb-ab)"/>')
# decoupled decomposition (amber, dashed): 0 -> F1 J1 -> tau   (first leg drawn slightly offset)
off = np.array([0.0, -0.03])
w(f'  <line x1="{P(off)[0]:.1f}" y1="{P(off)[1]:.1f}" x2="{P(B1+off)[0]:.1f}" y2="{P(B1+off)[1]:.1f}" stroke="{amber}" stroke-width="2.4" stroke-dasharray="7 4" marker-end="url(#fb-aa)"/>')
w(f'  <line x1="{P(B1)[0]:.1f}" y1="{P(B1)[1]:.1f}" x2="{P(tau)[0]+6:.1f}" y2="{P(tau)[1]:.1f}" stroke="{amber}" stroke-width="2.4" stroke-dasharray="7 4" marker-end="url(#fb-aa)"/>')
# resulting torque
w(f'  <line x1="{X0:.1f}" y1="{Y0:.1f}" x2="{P(tau)[0]:.1f}" y2="{P(tau)[1]:.1f}" stroke="{ink}" stroke-width="2.6" marker-end="url(#fb-ak)"/>')
w(f'  <circle cx="{X0:.1f}" cy="{Y0:.1f}" r="3" fill="{ink}"/>')
def lab(v, dx, dy, txt, col=ink, anchor="start", size=13):
    x, y = P(v); w(f'  <text x="{x+dx:.1f}" y="{y+dy:.1f}" text-anchor="{anchor}" font-size="{size}" fill="{col}">{txt}</text>')
lab(tau, -14, -10, f'&#964;{sub("x")}', ink, "end", 15)
lab(A1, -6, 22, f'&#955;{sub(1)}{JT(1)}', "#1e40af", "start")
lab((A1 + tau)/2, -9, 5, f'&#955;{sub(2)}{JT(2)}', "#1e40af", "end")
lab(B1, 10, 16, f'F{sub(1)}{JT(1)}', "#92400e")
lab((B1 + tau)/2, 0, -12, f'F{sub(2)}{JbT}', "#92400e", "middle")
lab(0.62*J1, 10, 22, f'direction of {JT(1)}', "#64748b", "start", 11.5)
lab(B1 + np.array([0.05, 0.07]), 6, -6, f'&#964;{sup("T")}M{sup("&#8722;1")}&#964; = const', "#64748b", "start", 11.5)
# legend (upper left, clear of the drawing)
lx, ly = 118, 46
w(f'  <rect x="{lx-10}" y="{ly-18}" width="232" height="64" rx="4" fill="#ffffff" fill-opacity="0.92" stroke="#e2e8f0"/>')
w(f'  <line x1="{lx}" y1="{ly-4}" x2="{lx+24}" y2="{ly-4}" stroke="{blue}" stroke-width="2.4"/>')
w(f'  <text x="{lx+32}" y="{ly}" font-size="12" fill="{ink}">stacked basis: &#964;{sub("x")} = J{sup("T")}&#955;</text>')
w(f'  <line x1="{lx}" y1="{ly+16}" x2="{lx+24}" y2="{ly+16}" stroke="{amber}" stroke-width="2.4" stroke-dasharray="7 4"/>')
w(f'  <text x="{lx+32}" y="{ly+20}" font-size="12" fill="{ink}">hierarchy 1&#8827;2: &#964;{sub("x")} = J&#773;{sup("T")}F</text>')
w(f'  <line x1="{lx}" y1="{ly+36}" x2="{lx+24}" y2="{ly+36}" stroke="{ink}" stroke-width="2.6"/>')
w(f'  <text x="{lx+32}" y="{ly+40}" font-size="12" fill="{ink}">the same torque &#964;{sub("x")}</text>')
w('</svg>')
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fig_bases.svg'), 'w').write("\n".join(out) + "\n")
print("wrote fig_bases.svg")
