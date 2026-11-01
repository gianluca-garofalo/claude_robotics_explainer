import numpy as np, pickle, re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from model import qd

BLUE, GREEN, AMBER, TEXT, GREY = '#3b82f6', '#22c55e', '#f59e0b', '#1e293b', '#64748b'
plt.rcParams.update({'font.family': 'serif', 'svg.fonttype': 'path', 'mathtext.fontset': 'cm',
                     'text.color': TEXT, 'axes.labelcolor': TEXT, 'axes.edgecolor': GREY,
                     'xtick.color': GREY, 'ytick.color': GREY, 'font.size': 10.5,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'svg.hashsalt': 'robot', 'legend.frameon': False})
h = 0.005
A = {}
for N in [10, 20, 40]:
    A.update(pickle.load(open(f'cl_A_{N}.pkl', 'rb')))


def finish(fig, name, prefix, label):
    fig.savefig(name, format='svg', transparent=True, metadata={'Date': None, 'Creator': None, 'Format': None, 'Type': None})
    s = open(name).read()
    s = re.sub(r'<\?xml.*?\?>\s*', '', s)
    s = re.sub(r'<!DOCTYPE.*?>\s*', '', s, flags=re.S)
    s = re.sub(r'<metadata>.*?</metadata>\s*', '', s, flags=re.S)
    s = re.sub(r'(<svg[^>]*?)\s(width|height)="[^"]*"', r'\1', s, count=1)
    s = re.sub(r'(<svg[^>]*?)\s(width|height)="[^"]*"', r'\1', s, count=1)
    s = s.replace('<svg ', f'<svg role="img" aria-label="{label}" style="width:100%;max-width:640px;height:auto" ', 1)
    # make ids unique within the host page
    s = re.sub(r'id="([^"]+)"', lambda m: f'id="{prefix}{m.group(1)}"', s)
    s = re.sub(r'href="#([^"]+)"', lambda m: f'href="#{prefix}{m.group(1)}"', s)
    s = re.sub(r'url\(#([^)]+)\)', lambda m: f'url(#{prefix}{m.group(1)})', s)
    open(name, 'w').write(s)


# ---------------- Figure a: joint angles and torques -----------------
fig, ax = plt.subplots(2, 2, figsize=(7.0, 5.0))
t = np.arange(501)*h
styles = [('PD', r'PD$+g$ (infinitesimal window)', GREEN, '--'), (10, r'$N=10$', AMBER, '-'), (40, r'$N=40$', BLUE, '-')]
for key, lab, col, ls in styles:
    r = A[key]
    z = r['z']; tau = r['tau']
    for j in range(2):
        ax[0, j].plot(t, qd[j] + z[:, j], color=col, ls=ls, lw=1.6, label=lab)
        ax[1, j].plot(t[:-1], tau[:, j], color=col, ls=ls, lw=1.6, label=lab)
for j in range(2):
    ax[0, j].axhline(qd[j], color=GREY, lw=0.8, ls=':')
    ax[0, j].set_ylabel(rf'$q_{j+1}$ [rad]')
    ax[1, j].set_ylabel(rf'$\tau_{j+1}$ [N m]')
    ax[0, j].set_xlabel(r'$t$ [s]')
    ax[1, j].set_xlabel(r'$t$ [s] (first 0.3 s)')
    ax[0, j].set_xlim(0, 2.5)
    ax[1, j].set_xlim(0, 0.3)
ax[1, 0].axhline(50, color=GREY, lw=0.8, ls=':'); ax[1, 0].axhline(-50, color=GREY, lw=0.8, ls=':')
ax[1, 1].axhline(30, color=GREY, lw=0.8, ls=':'); ax[1, 1].axhline(-30, color=GREY, lw=0.8, ls=':')
hd, lb = ax[0, 0].get_legend_handles_labels()
fig.legend(hd, lb, loc='upper center', ncol=3, fontsize=9.5)
fig.tight_layout(rect=(0, 0, 1, 0.93))
finish(fig, 'fig_a.svg', 'rfa-', 'Joint angles and torques of the two-link arm under PD plus gravity and the receding-window scheme with N = 10 and N = 40')

# ---------------- Figure b: remaining action vs realized tail cost; descent ratio ---------
fig, ax = plt.subplots(1, 2, figsize=(7.0, 3.0))
for key, lab, col in [(10, r'$N=10$', AMBER), (40, r'$N=40$', BLUE)]:
    r = A[key]
    V, l = r['V'], r['l']
    hl = h*l[:-1]
    tail = np.append(np.cumsum(hl[::-1])[::-1], 0.0) + V[-1]   # sum_{k<=j<K-1} h l_j + V_N(z_{K-1})
    tt = np.arange(len(V))*h
    ax[0].semilogy(tt, V, color=col, lw=1.8, label=rf'$V_N(z_k)$, {lab}')
    ax[0].semilogy(tt, tail, color=col, lw=1.2, ls='--', label=r'paid from $k$ on, ' + lab)
    ratio = (V[:-1] - V[1:])/(h*l[:-1])
    ax[1].plot(tt[:-1], ratio, color=col, lw=1.4, label=lab)
pd = A['PD']
ax[0].semilogy(np.arange(len(pd['W']))*h, pd['W'], color=GREEN, lw=1.2, ls=':', label=r'$W(z_k)$, PD$+g$')
ax[0].set_xlabel(r'$t$ [s]'); ax[0].set_ylabel('action')
ax[0].legend(fontsize=8, loc='lower left')
ax[1].axhline(1.0, color=GREY, lw=0.9, ls=':')
ax[1].set_xlabel(r'$t$ [s]'); ax[1].set_ylabel(r'$[V_N(z_k)-V_N(z_{k+1})]\,/\,h\ell_k$')
ax[1].legend(fontsize=9, loc='upper right')
fig.tight_layout()
finish(fig, 'fig_b.svg', 'rfb-', 'Remaining action along the closed loop compared with the action actually paid, and the per-step descent ratio')
print('done')
