import numpy as np
rng=np.random.default_rng(0)
n=7
A=rng.standard_normal((n,n)); M=A@A.T+n*np.eye(n); Mi=np.linalg.inv(M)
J1=rng.standard_normal((3,n)); J2=rng.standard_normal((2,n)); J3=rng.standard_normal((2,n))
# 1) block-LDL of A M^-1 A^T  <-> dynamically consistent extended Jacobians
Aj=np.vstack([J1,J2,J3]); G=Aj@Mi@Aj.T
L1=np.linalg.inv(J1@Mi@J1.T)
N1=np.eye(n)-Mi@J1.T@L1@J1            # dyn. consistent projector (velocity side)
Jb2=J2@N1
Jaug=np.vstack([J1,J2]); Laug=np.linalg.inv(Jaug@Mi@Jaug.T)
N12=np.eye(n)-Mi@Jaug.T@Laug@Jaug
Jb3=J3@N12
Jb=np.vstack([J1,Jb2,Jb3])
Lam_inv=Jb@Mi@Jb.T
print("offdiag blocks of Jb M^-1 Jb^T:",np.abs(Lam_inv[:3,3:]).max(),np.abs(Lam_inv[3:5,5:]).max())
# block LDL: L = A Jb^{-1}... check Jb = Linv @ Aj with L unit block lower triangular
T=Aj@np.linalg.inv(Jb)
print("A Jb^-1 block lower unit-triangular? upper blocks:",np.abs(T[:3,3:]).max(),np.abs(T[3:5,5:]).max(),
      "diag blocks I:",np.abs(T[:3,:3]-np.eye(3)).max(),np.abs(T[3:5,3:5]-np.eye(2)).max())
# 2) Gauss metric pushed to task space = Lambda (Schur complement)
q0=rng.standard_normal(n); b=rng.standard_normal(3)  # J1 qdd = b
lam=L1@(b-J1@q0); qdd=q0+Mi@J1.T@lam
G_val=0.5*(qdd-q0)@M@(qdd-q0)
print("min Gauss =",G_val," 0.5|b-J q0|^2_Lambda =",0.5*(b-J1@q0)@L1@(b-J1@q0))
print("torque = J^T lam, lam=Lambda(b - J qdd0): Khatib force; check tau^T M^-1 tau = 2G:",(J1.T@lam)@Mi@(J1.T@lam),2*G_val)
# 3) effort separates in decoupled coords: tau = Jb^T F (Jb square? add null-space rows)
# complete Jb to square with a null-space block
Nfull=np.eye(n)-Mi@Aj.T@np.linalg.inv(G)@Aj
U,S,Vt=np.linalg.svd(Nfull); Z=Vt[:n-7] if n>7 else None
F=rng.standard_normal(7); tau=Jb.T@F
blocks=[(0,3),(3,5),(5,7)]
print("tau^T M^-1 tau =",tau@Mi@tau," sum F_i^T Lam_i^-1 F_i =",sum(F[a:b]@Lam_inv[a:b,a:b]@F[a:b] for a,b in blocks))
# 4) Stacked (all-feasible) equality Gauss solution == strict hierarchy (Sentis-style) solution
bs=rng.standard_normal(7)
lam_s=np.linalg.solve(G,bs-Aj@q0); qdd_stack=q0+Mi@Aj.T@lam_s
# hierarchy: decoupled forces F_i = Lam_i (abar_i - Jb_i q0) where abar = Linv b
Lfac=T; abar=np.linalg.solve(Lfac,bs)
Fh=np.concatenate([np.linalg.solve(Lam_inv[a:b,a:b],abar[a:b]-Jb[a:b]@q0) for a,b in blocks])
qdd_h=q0+Mi@Jb.T@Fh
print("stack vs hierarchy qdd:",np.abs(qdd_stack-qdd_h).max(), " multipliers relate lam_s = L^-T F:",np.abs(lam_s-np.linalg.solve(Lfac.T,Fh)).max())
print("--- order dependence of 'task forces' ---")
print("F1 (level-1 decoupled force) :",Fh[:3])
print("lam1 (stacked multiplier)    :",lam_s[:3])
# reverse order: tasks (3,2,1)
Ar=np.vstack([J3,J2,J1]); br=np.concatenate([bs[5:7],bs[3:5],bs[:3]])
Gr=Ar@Mi@Ar.T
# block LDL via explicit recursion
def decouple(Js,bsplit):
    rows=[];F=[];P=np.eye(n);prev=None;Lprev=[]
    Jbs=[]
    for Ji in Js:
        if Jbs:
            Ja=np.vstack(Js[:len(Jbs)]); Na=np.eye(n)-Mi@Ja.T@np.linalg.inv(Ja@Mi@Ja.T)@Ja
            Jbs.append(Ji@Na)
        else: Jbs.append(Ji)
    return Jbs
Jbr=decouple([J3,J2,J1],None); Jbr_=np.vstack(Jbr); Tr=Ar@np.linalg.inv(Jbr_)
abr=np.linalg.solve(Tr,br); Lr=Jbr_@Mi@Jbr_.T
blk=[(0,2),(2,4),(4,7)]
Fr=np.concatenate([np.linalg.solve(Lr[a:b,a:b],abr[a:b]-Jbr_[a:b]@q0) for a,b in blk])
print("reversed-order qdd equal:",np.abs(q0+Mi@Jbr_.T@Fr-qdd_stack).max())
print("task-1 force when task 1 is LAST:",np.linalg.solve(Tr.T,Fr)[4:7], "(stacked multiplier, invariant) vs decoupled Fr[4:7]:",Fr[4:7])
