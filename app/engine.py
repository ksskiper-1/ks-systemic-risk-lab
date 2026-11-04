"""KS Resilience Lab - engine per Research Protocol v1.2 (sections 02-05)."""
import numpy as np
_trapz = getattr(np, 'trapezoid', None) or np.trapz   # NumPy <2.0 compatibility
EPS=1e-12; SMAX=0.15; DS=0.0005
SGRID=np.arange(0,SMAX+1e-12,DS)       # 301 points
RHO=0.02; GFRAC=0.03

def rng(base,topo,rep,stream):
    return np.random.default_rng(np.random.SeedSequence([base,topo,rep,stream]))

def gen_net(topo,rep,N=25,alpha=0.5,core_ratio=None,base=0,kappa_fixed=None):
    """topo 0=Distributed, 1=Concentrated. Streams: 0 structure, 1 weights, 2 capital (same for both topologies)."""
    Atot=2500.0
    if topo==1 and core_ratio:
        Ap=Atot/(core_ratio*5+N-5); A=np.full(N,Ap); A[:5]=core_ratio*Ap
    else: A=np.full(N,Atot/N)
    rc=rng(base,9,rep,2)
    kappa=rc.uniform(0.04,0.10,N) if kappa_fixed is None else np.full(N,kappa_fixed)
    Kb=kappa*A
    if topo==1 and core_ratio:   # exact capital-preserving normalisation (sect. 04)
        Kb=Kb*(kappa.sum()*Atot/N)/(kappa*A).sum()
    rs=rng(base,topo,rep,0); rw=rng(base,topo,rep,1)
    E=np.zeros((N,N))
    for i in range(N):
        if topo==0:
            m=min(max(1,rs.poisson(3)),N-1)
            others=[j for j in range(N) if j!=i]
            tg=rs.choice(others,m,replace=False)
        else:
            if i<5:
                tg=np.array([j for j in range(5) if j!=i]+list(rs.choice(np.arange(5,N),3,replace=False)))
            else:
                tg=rs.choice(5,2,replace=False)
        w=rw.dirichlet(np.ones(len(tg)))
        E[i,tg]=alpha*A[i]*w
    return E,A,Kb

def casc_batch(E,K,R,L0):
    direct=L0>=K-EPS; D=direct.copy()
    while True:
        L=L0+(1-R)*(D.astype(float)@E.T)
        Dn=D|(L>=K-EPS)
        if (Dn==D).all(): break
        D=Dn
    return D.sum(1)-direct.sum(1)

def order_by_liab(E): return np.argsort(-E.sum(0),kind='stable')   # L_j=sum_i E_ij, ties -> lower index

def casc_support(E,K0,R,L0,G,order):
    K=K0.astype(float).copy(); direct=L0>=K0-EPS; D=direct.copy(); Gl=G
    while True:
        L=L0+(1-R)*(E@D.astype(float))
        new=(L>=K-EPS)&~D
        if not new.any(): break
        for j in order:
            if new[j] and not direct[j]:
                need=L[j]-K[j]+1e-9
                if need<=Gl: K[j]+=need; Gl-=need; new[j]=False
        D|=new
    return int(D.sum()-direct.sum())

def secondary(E,K0,R,L0,G=0.0,order=None,support=False):
    """L0: (m,N) rows of initial losses -> secondary defaults per row"""
    if not support: return casc_batch(E,K0,R,L0)
    return np.array([casc_support(E,K0,R,l,G,order) for l in L0])

def mech_setup(mech,Kb,A,rho=None,Gabs=None):
    rho=RHO if rho is None else rho
    if mech=='none': return Kb,0.0,False
    if mech=='res': return Kb+rho*A,0.0,False
    return Kb,(GFRAC*Kb.sum() if Gabs is None else Gabs),True

def metrics(E,A,Kb,mech,R=0.4,theta=0.10,rho=None,Gabs=None):
    N=len(A); w=A/A.sum()
    K,G,sup=mech_setup(mech,Kb,A,rho,Gabs); order=order_by_liab(E)
    k=K/A
    # single-bank: step curve, C1(i) independent of s
    L0=np.diag(K)                       # shock exactly sufficient to default i
    c1=secondary(E,K,R,L0,G,order,sup)/N
    A1=float((w*c1*np.maximum(0,SMAX-k)).sum())
    sstar=np.where(c1>theta,k,1.0); FS=float((w*(sstar<1)).sum()); KSTI=float((w*sstar).sum())
    # general shock
    Cg=np.zeros(len(SGRID)); act=SGRID>=k.min()-1e-12
    S=SGRID[act]; L0g=S[:,None]*A[None,:]
    sec=secondary(E,K,R,L0g,G,order,sup); Cg[act]=sec/N
    A2=float(_trapz(Cg,dx=DS))
    Ct=np.zeros(len(SGRID)); Ct[act]=(sec+(L0g>=K-EPS).sum(1))/N
    A2t=float(_trapz(Ct,dx=DS))
    idx=lambda s:int(round(s/DS))
    hit=np.where(Cg>theta)[0]; ssys=float(SGRID[hit[0]]) if len(hit) else np.nan
    return dict(A1=A1,A2=A2,A2t=A2t,C06=Cg[idx(.06)],C08=Cg[idx(.08)],C10=Cg[idx(.10)],ssys=ssys,FS=FS,KSTI=KSTI,c1=c1,Cg=Cg)
