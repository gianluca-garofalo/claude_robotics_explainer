# Companion code

The scripts that reproduce the numbers, checks and figures of `../explainer.html` and of the video series made from it, kept at the paths the explainer's Verification Status section
(Section 18) uses, relative to this folder: the complete companion code, every file copied unmodified except
`note/sec7_symbolic_checks.py`, whose check of the $u$-equation was corrected on 2026-10-31 (it compared with $-H_u$
instead of $+H_u$; the log now prints 0), and `merged/fig_bases.py`, whose Figure 7 labels the torque $\tau_x$ instead
of $\tau_c$ (same drawing and numbers). Series runs copy
this folder unchanged, and every number on screen must come from it.

Requirements: Python 3.11+ with `numpy`, `scipy`, `sympy`, `matplotlib`, `quadprog` (`merged/ineq_arm.py`). Run all
listed checks (`checks.toml`) from the repository root:

```bash
.venv/bin/python tools/run_code_checks.py sources/variational-whole-body-control
```

or one script from its own folder, e.g. `cd code/note && python3 sec4_3_one_step_example.py`. The outputs of the
last full run are in `logs/` (one log per script and `summary.json`). The two-link-arm scripts in `note/sec8_arm/` take
seconds to minutes; `closedloop.py` runs a short case in the manifest and minutes for the full runs.

Three things are run by hand:

- the full 500-step closed-loop runs of Section 10.6, `python3 closedloop.py A 10,20,40` and
  `python3 closedloop.py B 1,10,40` in `note/sec8_arm/` (up to about 25 minutes each); their console output is kept in
  `../data/` (`closedloop_A10_40.log`, `closedloop_A20.log`, `closedloop_B.log`);
- `note/sec8_arm/figs.py` draws Figures 5 and 6 from the `cl_*.pkl` files that the full `closedloop.py` runs write in
  its folder (then `python3 figs.py`; minutes);
- `note/sec8_arm/pinocchio_crosscheck.py` compares the hand-written arm model with Pinocchio (`pip install pin`), which
  the project does not install.

## Map to `explainer.html`

| Section(s) | Script | What it does | Kind |
|---|---|---|---|
| 4.3 (tables) | `note/sec4_3_one_step_example.py` | One-step rule for $L=\tfrac12 v^2+\tfrac12 q^2$, $h=0.1$: exact discrete Lagrangian with $W=\tfrac12q^2$ (equality $\Delta V_1=-L_d$), rectangle rule with $W=\tfrac12q^2$ (descent fails) and with $W=1.2\cdot\tfrac12q^2$ (descent holds). | numerical |
| 3.3, 4.3, 5.3, 6.3 | `note/sec5_6_symbolic_checks.py` | SymPy checks of the hilltop: Hamilton-Jacobi residual, $\int_0^\infty L\,dt=V(q_0)$, eigenvalues, $p=-V'$, finite-window $V_\vartheta$, exact discrete Lagrangian; $P_{\rm CARE}$ vs $P_{\rm DARE}$ and the threshold $c\ge P_d/P=1.051249$. | exact + numerical |
| Figure 3 | `note/fig3_phase_portrait.py` | Phase portrait of the hilltop saddle; writes `fig3_phase_portrait.svg`. | figure |
| 15.2 | `merged/window_split.py` | Splits $V_N(q_0)$ into window part and tail $W(q_N)$ for $N\in\{1,2,5,10,20,50\}$, for the exact pair and for the rectangle rule with $W=1.2\cdot\tfrac12q^2$. | numerical |
| 3.3, 18 | `merged/riccati_threshold.py` | 3-D example: the smallest eigenvalue of $cP-T(cP)$ changes sign exactly at $c^\ast=\lambda_{\max}(P^{-1}P_d)=1.1055$. | numerical |
| 1.5, 6.3 | `merged/hilltop_extra.py` | SymPy: Jacobi field $\sinh\omega t$; closed form of $L_d^E$ equals the action of the extremal; one step with $L_d^E$ and $W=V$. | exact |
| 12.3, Figure 7 | `merged/fig_bases.py` | Two-link arm at $q_d$: $\Theta_{21}=2.5$, $F=\Theta^\top\lambda=(3,0.4)$ for $\lambda=(2,0.4)$; writes `fig_bases.svg`. | numerical + figure |
| 8.2, 8.3, 9.1, 9.2, 12, 13.2, 14.1 | `wbc/wbc_companion_checks.py` | Fixed-seed checks: Gauss = operational-space control, block LDLᵀ = dynamically consistent hierarchy, $F=L^\top\lambda$ and order dependence, power invariance. | numerical |
| 3.2, 6.5, 18 | `merged/ineq_hilltop.py` | Speed limit on the hilltop: the clipped law and its cost $0.541667$, one-sided derivatives of $V_{\rm con}$ at $q_s$ ($C^2$, not $C^3$), the discrete step with $q-q'\le h\bar v$ ($\mu=0.45$). | numerical |
| 7 | `note/sec7_numerical_checks.py` | Second-order plants: the optimal torque formula against numerical optima for $R=I$ and $R=M^{-1}$, the Gauss identity; writes `num_results.json`. | numerical |
| 7 | `note/sec7_symbolic_checks.py` | SymPy: the Euler–Lagrange equations of the augmented Lagrangian are Hamilton's equations (all three differences print 0), the Hamiltonian of a second-order plant, closed-form Riccati solutions of the double integrator. | exact |
| Figure 4 | `note/fig4_double_integrator.py` | Figure 4: the double-integrator phase plane; writes `fig4_double_integrator.svg`. | figure |
| 10 | `note/sec8_arm/model.py` | Arm model ($M$, $C$, $g$ in closed form), designs, $\ell$, $W$, $s$ (imported by the arm scripts). | module |
| 10.5 | `note/sec8_arm/mpc.py` | Receding-window solver: single shooting, SLSQP, exact adjoint gradients (imported). | module |
| 10.2, 10.3, 10.4 | `note/sec8_arm/sym_derive.py` | SymPy: $\dot W$, the Slotine–Li identity, $u^\ast$, $\mathcal D=-H$, $\pi_v=-Ms$. | exact |
| 10.4 | `note/sec8_arm/condcheck.py` | Eigenvalues of $\mathbf D$ and the positive definiteness of $W$. | numerical |
| 10.4 | `note/sec8_arm/edge.py` | $\mathcal D$ near the edge of the certified level set. | numerical |
| 10.5 | `note/sec8_arm/quadlimit.py` | Quadratic limit of the discrete condition and the closed-loop eigenvalues. | numerical |
| 10.5, 10.6 | `note/sec8_arm/feas.py` | Torque-limit level $c_\tau$ and terminal feasibility for $N=1,5,10$. | sampled |
| 10.5 | `note/sec8_arm/omega_check.py` | The discrete condition on the certified level sets (sampled, refined). | sampled |
| 10.5 | `note/sec8_arm/discrete_check.py` | Thresholds on $c_W$ for $h=0.005$ and $0.01$ s. | sampled |
| 10.5, 10.6 | `note/sec8_arm/closedloop.py` | Closed-loop runs and the descent check; `python3 closedloop.py A 10,20,40` or `B 1,10,40` for the full runs (up to about 25 minutes each, by hand; console output in `../data/`). The manifest runs a short one. | numerical |
| 10.6 | `note/sec8_arm/longh.py` | Long-window reference values $V_{100}$, $V_{200}$, $V_{400}$. | numerical |
| 7.5, 10.7 | `merged/ineq_arm.py` | Torque box on the arm: box-QP minimizer = clip for diagonal $R$; projection $(50,-10.2)$ vs clip $(50,30)$ N m with $R=T_0M^{-1}$; the certificate with the box; KKT along the $N=10$ run (needs `quadprog`). | numerical + sampled |
| 10.6, 18 | `merged/arm_extra_checks.py` | Adjoint gradients against finite differences; the $N=1$ torque gap to PD$+g$ (0.73, 1.03 N m) and its decrease with $h/2,h/4,h/8$. | numerical |
| 8.4, 14.2 | `merged/ineq_gauss.py` | Unilateral constraints in Gauss's principle: Fourier's inequality, the powers of active and inactive contacts. | numerical |
| 8.3 | `merged/duals_check.py` | Multiplier of the Gauss problem equals $T_0\lambda$; momenta of the arm's $W$ in two coordinate systems with the same pairing. | numerical |
| 12.3, 13.2, 18 | `wbc_brainstorm/redteam_check_ineq_order.py` | Order dependence of the torque (prescribed per-level forces versus the stacked constraint view) and an inequality switching at the top. | numerical |
| 12 | `wbc_brainstorm/redteam_check_A_B.py` | Independent check of the LDLᵀ claims against dynamically consistent extended Jacobians, including a conflicting stack. | numerical |
| 13.2, 13.3, 14.2 | `merged/ineq_hierarchy.py` | Inequality tasks: the active interval of $\lambda_2$, the decoupled force and its sign, total power. | numerical |
| 14.1 | `wbc_brainstorm/redteam_check_power.py` | Power invariance across task orders; the per-level powers. | numerical |
| 8.1, 15.1 | `wbc_brainstorm/redteam_check_C_F.py` | Hold dependence of the finite-window law (ZOH, impulse, optimal $u(0)$); transcription dependence of $\tau_0=\pi_v$. | numerical |
| 13.4 | `merged/ineq_soft.py` | Strict versus soft priority with an inequality in conflict: the weighted solution approaches the lexicographic one like $0.1218/w$. | numerical |
| 2, 3.3, 18 | `note/sec10_general_N_descent.py` | 3-D random quadratic Lagrangian with a rectangle-rule $L_d$: the threshold $c^\ast=\lambda_{\max}(P^{-1}P_d)$ and the $N$-step descent inequality for $N\in\{1,2,3,5,8\}$ (20 random starts). | sampled |
| 12 | `wbc_brainstorm/brainstorm_check1.py` | Hierarchy as block Gram–Schmidt / LDLᵀ in the $M^{-1}$ metric: Khatib's force as a Gauss multiplier, $\lambda=L^{-\top}F$, the order dependence of task forces (exploratory). | numerical |
| 8.1 | `wbc_brainstorm/brainstorm_check2.py` | Finite-window (zero-order hold) argmin for a 1-DOF energy-type $W$; series in $\delta$ (exploratory). | exact |
| 10 | `note/sec8_arm/pinocchio_crosscheck.py` | The arm model against Pinocchio (1000 random states); skew-symmetry of $\dot M-2C$. Manual: needs Pinocchio. | numerical |
| Figures 5, 6 | `note/sec8_arm/figs.py` | Figures 5 and 6 from the `cl_*.pkl` files of the full closed-loop runs. Manual. | figure |


"Exact" = symbolic identity; "numerical" = floating-point evaluation with the residual printed;
"sampled" = random or grid search, not a proof.
