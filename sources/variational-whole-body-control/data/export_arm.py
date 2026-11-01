"""Convert the closed-loop pickles of closedloop.py into the arrays the arm scenes read.

  arm_A.npz  start A, q0 = (1.0, -0.95): N = 10, 20 and 40, and the PD + gravity baseline
  arm_B.npz  start B, q0 = (0.9, -0.85): N = 1, 10 and 40, and the PD + gravity baseline

The pickles come from ../code/note/sec8_arm/closedloop.py (an unmodified copy of the companion code), run in its own
folder (500 steps of h = 5 ms), where it writes them:
    python3 closedloop.py A 10 && python3 closedloop.py A 40   # cl_A_10.pkl, cl_A_40.pkl (the first export)
    python3 closedloop.py A 20                                  # cl_A_20.pkl (2026-10-31, 942 s)
    python3 closedloop.py B 1,10,40                             # cl_B_1_10_40.pkl (2026-10-31, about 26 min)
then, from this folder, `python3 export_arm.py [PICKLE_DIR]` (default ../code/note/sec8_arm). The pickles are not kept:
delete them from the code folder afterwards. The arrays of an existing arm_*.npz whose pickle is absent stay as they
are, so a new run adds to the file and never drops an earlier one (the PD + gravity baseline is the same in every
pickle of a start). The console output of the 2026-10-31 runs is kept in closedloop_A20.log and closedloop_B.log;
the values printed below are recomputed from the trajectories and match those logs.
"""
import glob
import os
import pickle
import sys

import numpy as np

here = os.path.dirname(os.path.abspath(__file__))
arm = os.path.join(here, "..", "code", "note", "sec8_arm")
sys.path.insert(0, arm)                                   # pickles reference numpy only, but keep model importable
from model import qd, TAU_MAX                             # noqa: E402

H = 0.005                                                 # H_STEP of mpc.py
src = sys.argv[1] if len(sys.argv) > 1 else arm


def run_arrays(rec, N):
    V, l = rec["V"], rec["l"]
    return {f"n{N}_z": rec["z"], f"n{N}_tau": rec["tau"], f"n{N}_V": V, f"n{N}_l": l,
            f"n{N}_defect": V[1:] - V[:-1] + H * l[:-1],          # must be <= 0 (the descent inequality)
            f"n{N}_ratio": (V[:-1] - V[1:]) / (H * l[:-1]),        # must be >= 1
            f"n{N}_Scl": H * l.sum()}


for start in ("A", "B"):
    path = os.path.join(here, f"arm_{start}.npz")
    pickles = sorted(glob.glob(os.path.join(src, f"cl_{start}_*.pkl")))
    if not pickles:
        continue
    out = dict(np.load(path, allow_pickle=False)) if os.path.exists(path) else {}
    out.update(h=H, qd=qd, tau_max=TAU_MAX)
    for pk in pickles:
        with open(pk, "rb") as fh:
            res = pickle.load(fh)
        for N in sorted(k for k in res if isinstance(k, int)):
            out.update(run_arrays(res[N], N))
        pd = res["PD"]
        out.update(pd_z=pd["z"], pd_tau=pd["tau"], pd_W=pd["W"], pd_l=pd["l"], pd_Scl=H * pd["l"].sum())
    np.savez_compressed(path, **out)
    print(f"arm_{start}.npz (pickles: {', '.join(os.path.basename(p) for p in pickles)})")
    for N in sorted(int(k[1:-4]) for k in out if k.startswith("n") and k.endswith("_Scl")):
        print(f"  N={N}: V_N(z0)={out[f'n{N}_V'][0]:.4f}  S_cl={out[f'n{N}_Scl']:.4f}  "
              f"max(dV+hl)={out[f'n{N}_defect'].max():.2e}  min ratio={out[f'n{N}_ratio'].min():.3f}  "
              f"peak|tau|={np.abs(out[f'n{N}_tau']).max(0).round(1)}  V_end={out[f'n{N}_V'][-1]:.2e}")
    print(f"  PD+g: S_cl={out['pd_Scl']:.4f}  W(z0)={out['pd_W'][0]:.4f}  "
          f"peak|tau|={np.abs(out['pd_tau']).max(0).round(1)}")
