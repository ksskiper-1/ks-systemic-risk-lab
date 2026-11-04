"""Прототип версии DebtRank «банк передаёт стресс один раз» (оригинальная схема состояний: нетронут / в стрессе / неактивен).
НЕ входит в contagion.py и протокол. Цель: проверить, насыщается ли и эта версия при параметрах протокола.
W_ij = (1-R) E_ij / K_i, h_i = min(1, h_i + sum_j W_ij h_j [j в стрессе]). Запуск: python results/exploration_once_debtrank.py"""
from common import header
import numpy as np
from engine import gen_net, mech_setup

def debtrank_once(E, K, R, L0):
    W = (1 - R) * E / K[:, None]; h = np.minimum(1.0, L0 / K); h0 = h.copy(); state = np.where(h > 0, 1, 0)
    while (state == 1).any():
        D = (state == 1); hn = np.minimum(1.0, h + W @ (h * D))
        new = (hn > h + 1e-15) & (state == 0); state = np.where(D, 2, state); state = np.where(new, 1, state); h = hn
    return h, h0

NREP = 30
header("DebtRank с однократной передачей", nrep_per_topology=NREP, alpha=0.5, R=0.4, mech="none")
print("шок s | S_total/(ΣK/ΣA) топо0 / топо1 | средняя разность S_ind топо1 - топо0")
for s in (0.005, 0.01, 0.02, 0.05, 0.10):
    r = {0: [], 1: []}; si = {0: [], 1: []}
    for topo in (0, 1):
        for rep in range(NREP):
            E, A, Kb = gen_net(topo, rep, base=2026); K, G, sup = mech_setup('none', Kb, A)
            h, h0 = debtrank_once(E, K, 0.4, s * A); r[topo].append(float((h * K).sum() / A.sum()) / (K.sum() / A.sum())); si[topo].append(float(((h - h0) * K).sum() / A.sum()))
    d = np.mean(np.array(si[1]) - np.array(si[0]))
    print("%.3f | %.3f / %.3f | %+.2e" % (s, np.mean(r[0]), np.mean(r[1]), d))
E, A, Kb = gen_net(0, 0, base=2026); K, G, sup = mech_setup('none', Kb, A); res = []
for i in range(25):
    L0 = np.zeros(25); L0[i] = K[i]; h, h0 = debtrank_once(E, K, 0.4, L0); res.append(((h > 0).sum() - 1, (h >= 1 - 1e-12).sum() - 1))
print("одиночный шок L0_i = K_i (топо0, rep 0): банков со стрессом / полностью упавших, среднее по инициаторам: %.1f / %.1f" % tuple(np.mean(res, axis=0)))
