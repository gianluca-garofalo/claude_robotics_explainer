import numpy as np, matplotlib
matplotlib.use("svg")
import matplotlib.pyplot as plt
plt.rcParams.update({"font.family":"serif","font.size":11,"svg.fonttype":"path","mathtext.fontset":"cm","text.color":"#1e293b","axes.edgecolor":"#64748b","axes.labelcolor":"#1e293b","xtick.color":"#64748b","ytick.color":"#64748b"})
fig,ax=plt.subplots(figsize=(6.2,5.2))
x=np.linspace(-2,2,401); X,P=np.meshgrid(x,x); H=0.5*P**2-0.5*X**2
ax.contour(X,P,H,levels=[-1.2,-0.6,-0.2,0.2,0.6,1.2],colors="#cbd5e1",linewidths=0.9)
ax.streamplot(X,P,P,X,color="#94a3b8",density=0.7,linewidth=0.6,arrowsize=0.8)
ax.plot(x,-x,color="#22c55e",lw=2.6,label=r"stable manifold $p=-\sqrt{m\kappa}\,q$  ($H=0$)")
ax.plot(x,x,color="#f59e0b",lw=2,ls="--",label=r"unstable manifold $p=+\sqrt{m\kappa}\,q$")
for x0 in (1.6,-1.6):
    ax.annotate("",xy=(x0*0.45,-x0*0.45),xytext=(x0*0.8,-x0*0.8),arrowprops=dict(arrowstyle="-|>",color="#15803d",lw=2))
ax.plot([1.6],[-1.6],"o",color="#3b82f6",ms=7); ax.text(1.62,-1.42,r"$(q_0,\,p_0)$",color="#3b82f6")
ax.plot([0],[0],"o",color="#0f172a",ms=6); ax.text(0.08,0.12,"rest point",fontsize=9.5)
ax.set_xlabel(r"configuration $q$"); ax.set_ylabel(r"momentum $p$")
ax.set_xlim(-2,2); ax.set_ylim(-2,2); ax.set_aspect("equal")
ax.legend(loc="upper left",fontsize=9,frameon=True,framealpha=0.95)
for s in ("top","right"): ax.spines[s].set_visible(False)
fig.tight_layout(); fig.savefig("fig3_phase_portrait.svg",transparent=True)
