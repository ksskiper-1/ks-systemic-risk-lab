"""Предрасчёт для раздела «Проверка гипотезы»: сетка чувствительности 27 ячеек и дополнение по α.
Повторяет run_main.py (протокол v1.3, base seed 2026). Запуск: python precompute.py  (около 2-3 минут)."""
import numpy as np, json, time
from engine import *
BASE = 2026; MECH = ('none', 'res', 'sup')

def run(n, alpha=0.5, R=0.4, Gabs=None):
    out = np.zeros((n, 2, 3, 2))
    for rep in range(n):
        for topo in (0, 1):
            E, A, Kb = gen_net(topo, rep, alpha=alpha, base=BASE)
            for mi, m in enumerate(MECH):
                r = metrics(E, A, Kb, m, R=R, Gabs=Gabs); out[rep, topo, mi] = [r['A1'], r['A2']]
    return out

def Tof(o):
    d = o[:, :, 2, :] - o[:, :, 0, :]; m = d.mean(0)
    Ds = m[1, 0] - m[0, 0]; Dg = m[1, 1] - m[0, 1]; return Ds - Dg, d

def boot_ci(d, B=10000, seed=2026):
    r = np.random.default_rng(seed); n = d.shape[0]
    i0 = r.integers(0, n, (B, n)); i1 = r.integers(0, n, (B, n))
    M0 = d[:, 0, :][i0].mean(1); M1 = d[:, 1, :][i1].mean(1); Dd = M1 - M0; T = Dd[:, 0] - Dd[:, 1]
    return [float(x) for x in np.percentile(T, [2.5, 97.5])]

if __name__ == '__main__':
    t0 = time.time(); grid = []
    for al in (0.3, 0.5, 0.6):
        for Rr in (0.2, 0.4, 0.6):
            for gn, g in (('G0', None), ('G25', 25.0), ('G50', 50.0)):
                T, _ = Tof(run(200, alpha=al, R=Rr, Gabs=g)); grid.append(dict(G=gn, R=Rr, alpha=al, T=float(T)))
        print("grid alpha", al, "t=%.0f" % (time.time() - t0), flush=True)
    supp = {}
    for al in (0.1, 0.2):
        T, d = Tof(run(300, alpha=al)); supp[str(al)] = dict(T=float(T), CI=boot_ci(d, 4000), n=300)
        print("alpha", al, supp[str(al)], flush=True)
    json.dump(dict(grid=grid, alpha_supplement=supp, base_seed=BASE, n_per_cell=200), open('precomputed.json', 'w'), indent=1)
    print("done %.0fs" % (time.time() - t0))
