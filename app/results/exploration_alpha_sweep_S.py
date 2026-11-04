"""Насыщение метрики S в зависимости от α (непрерывная модель с повторной передачей, режим 'none', R = 0,4, общий шок).
Для каждого α: доля S_total при шоке 1% от потолка ΣK/ΣA, A2S по топологиям, средняя абсолютная парная разность A2S.
Запуск: python results/exploration_alpha_sweep_S.py"""
from common import header
import numpy as np
from engine import gen_net, mech_setup
import contagion as C
NREP = 60; ALPHAS = (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.50)
header("S против α", nrep=NREP, alphas=ALPHAS, R=0.4, mech="none", shock_ref="1%")
print("alpha | S_total(1%)/(ΣK/ΣA) топо0 / топо1 | A2S топо0 | A2S топо1 | средняя |разность A2S| по парам | ρ среднее (топо0)")
for al in ALPHAS:
    r = {0: [], 1: []}; a2 = {0: [], 1: []}; rho = []
    for topo in (0, 1):
        for rep in range(NREP):
            E, A, Kb = gen_net(topo, rep, alpha=al, base=2026); K, G, sup = mech_setup('none', Kb, A)
            St, _ = C.induced_S(E, K, A, 0.4, (0.01 * A)[None, :], total=True); r[topo].append(St[0] / (K.sum() / A.sum()))
            a2[topo].append(C.metrics_S(E, A, Kb, 'none')['A2S'])
            if topo == 0: rho.append(max(abs(np.linalg.eigvals(0.6 * E / K[:, None]))))
    d = np.abs(np.array(a2[1]) - np.array(a2[0])).mean()
    print("%.2f  | %.3f / %.3f | %.5f | %.5f | %.1e | %.2f" % (al, np.mean(r[0]), np.mean(r[1]), np.mean(a2[0]), np.mean(a2[1]), d, np.mean(rho)))
