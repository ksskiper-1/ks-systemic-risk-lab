"""Меняет ли поддержка (вливание дефицита, G ≈ 3% базового капитала) метрику S? Сравнение A1S и A2S «без помощи» и «поддержка».
Точное сравнение: печатается максимум абсолютной разности (0,0e+00 означает побитовое совпадение).
Запуск: python results/exploration_support_S.py"""
from common import header
import numpy as np
from engine import gen_net
import contagion as C
NREP = 40
header("S: без помощи против поддержки", nrep_per_topology=NREP, alpha=0.5, R=0.4, target=1.0, mode="linear")
for topo in (0, 1):
    d1 = []; d2 = []; c1 = []; cg = []
    for rep in range(NREP):
        E, A, Kb = gen_net(topo, rep, base=2026)
        a = C.metrics_S(E, A, Kb, 'none'); b = C.metrics_S(E, A, Kb, 'sup')
        d1.append(abs(a['A1S'] - b['A1S'])); d2.append(abs(a['A2S'] - b['A2S'])); c1.append(b['cost1']); cg.append(b['cost_g'])
    print("топо %d: max|ΔA1S| = %.1e, max|ΔA2S| = %.1e | средние затраты: cost1 %.2f, cost_g %.2f (бюджет около 5,3)" % (topo, max(d1), max(d2), np.mean(c1), np.mean(cg)))
