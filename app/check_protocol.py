"""Воспроизведение основной серии протокола v1.3 без Streamlit: T, 95% ДИ, порог δ, исход. Запуск: python check_protocol.py"""
import json, time
import numpy as np
from engine import gen_net, metrics
from precompute import run, Tof, boot_ci

t0 = time.time()
a1, a2 = [], []
for rep in range(100):                                   # пилот для δ: seed 7777, распределённая сеть, без поддержки
    E, A, Kb = gen_net(0, rep, base=7777); r = metrics(E, A, Kb, 'none'); a1.append(r['A1']); a2.append(r['A2'])
delta = 0.1 * max(np.median(a1), np.median(a2))
o = run(100)                                             # основная серия, seed 2026, 100 сетей
T, d = Tof(o); lo, hi = boot_ci(d, B=10000)
m = d.mean(0); Ds = m[1, 0] - m[0, 0]; Dg = m[1, 1] - m[0, 1]
grid = json.load(open('precomputed.json'))['grid']
sg = np.mean([np.sign(c['T']) == np.sign(T) for c in grid])
excl0 = lo > 0 or hi < 0; big = abs(T) >= delta
print("T = %+.4f  95%% ДИ [%.4f; %.4f]  δ = %.4f" % (T, lo, hi, delta))
print("Δ(один банк) = %+.4f  Δ(общий шок) = %+.4f" % (Ds, Dg))
print("знак T в сетке: %d из %d | ДИ без нуля: %s | |T| >= δ: %s" % (round(sg * len(grid)), len(grid), excl0, big))
print("исход:", "гипотеза поддержана" if (excl0 and big and sg >= .9) else "не поддержана / неустойчиво", "| %.0f с" % (time.time() - t0))
ok = abs(T - 0.0107) < 5e-5 and abs(lo - 0.0085) < 5e-5 and abs(hi - 0.0129) < 5e-5 and abs(delta - 0.0051) < 5e-5 and round(sg * len(grid)) == len(grid)
print("сверка с концепцией:", "совпало" if ok else "НЕ СОВПАЛО")
raise SystemExit(0 if ok else 1)
