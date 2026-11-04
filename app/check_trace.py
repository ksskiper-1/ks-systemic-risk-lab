import numpy as np
from engine import *
from cascade_trace import trace
bad=0; n=0
for rep in range(6):
    for topo in (0,1):
        E,A,Kb=gen_net(topo,rep,base=2026)
        for mech in ('none','res','sup'):
            K,G,sup=mech_setup(mech,Kb,A); order=order_by_liab(E)
            for s in (0.03,0.05,0.07,0.09,0.12,0.15):
                L0=(s*A)
                a=secondary(E,K,0.4,L0[None,:],G,order,sup)[0]
                b=trace(E,K,0.4,L0,G,order,sup)['secondary']; n+=1; bad+=(a!=b)
            for i in range(25):
                L0=np.zeros(25); L0[i]=0.1*A[i]
                a=secondary(E,K,0.4,L0[None,:],G,order,sup)[0]
                b=trace(E,K,0.4,L0,G,order,sup)['secondary']; n+=1; bad+=(a!=b)
print("trace vs engine mismatches:",bad,"/",n); fails=bad

# --- инвариант колец: банк, чья доля потерь >=1 на шаге t, на шаге t+1 либо падает, либо спасён
bad=0; n=0
for rep in range(8):
    for topo in (0,1):
        E,A,Kb=gen_net(topo,rep,base=2026)
        for mech in ('none','res','sup'):
            K,G,sup=mech_setup(mech,Kb,A); order=order_by_liab(E)
            for s in (0.05,0.07,0.1):
                for L0 in (s*A, np.eye(25)[rep]*K[rep]*1.0):
                    t=trace(E,K,0.4,L0,G,order,sup); assert len(t['ratios'])==len(t['steps'])
                    D=set(t['steps'][0])
                    for w in range(1,len(t['steps'])):
                        brink={i for i in range(25) if i not in D and t['ratios'][w-1][i]>=1-1e-9}
                        got=set(t['steps'][w])|set(t['rescued'][w]); n+=1; bad+=(brink!=got); D|=set(t['steps'][w])
print("ring invariant violations:",bad,"/",n)
import sys; sys.exit(1 if (fails or bad) else 0)
