"""Тест KSTI: добавляет ли он информацию сверх простых показателей (FS, средний k) о размере каскада.
Данные: сети seed 2026, rep 0..299, обе топологии, три механизма; пороги θ = 5%, 10%, 20%.
Идентичность: KSTI = (1 - FS) + sum_i w_i * v_i * k_i, где v_i = 1[c1_i > θ]. То есть при равных весах KSTI = линейная функция
FS и «капитала банков-триггеров»; вопрос «добавляет ли KSTI» = «несёт ли информацию капитал триггеров сверх FS».
Исходы: A1, A2 (дефолты, движок) и A1S, A2S (потеря капитала, contagion.py; только механизм 'none').
ВНИМАНИЕ: A1 строится из того же вектора c1, что FS и KSTI, поэтому для A1 связь отчасти механическая; осмысленнее A2 и A2S.
Запуск: python ksti_test.py"""
import json, time
import numpy as np
from engine import gen_net, metrics, mech_setup
import contagion as C

NREP = 300; THETAS = (0.05, 0.10, 0.20); MECHS = ('none', 'res', 'sup'); OUTS = ('A1', 'A2', 'A1S', 'A2S')

def collect():
    rows = []
    for rep in range(NREP):
        for topo in (0, 1):
            E, A, Kb = gen_net(topo, rep, base=2026)
            for mech in MECHS:
                r = metrics(E, A, Kb, mech); K, G, sup = mech_setup(mech, Kb, A); w = A / A.sum(); k = K / A
                row = dict(topo=topo, mech=mech, rep=rep, A1=r['A1'], A2=r['A2'], c1=r['c1'], k=k, w=w)
                if mech == 'none':
                    s = C.metrics_S(E, A, Kb, 'none'); row['A1S'] = s['A1S']; row['A2S'] = s['A2S']
                rows.append(row)
    return rows

def predictors(row, th):
    v = row['c1'] > th; w, k = row['w'], row['k']
    FS = float((w * v).sum()); KSTI = float((w * np.where(v, k, 1.0)).sum()); kbar = float((w * k).sum())
    return FS, KSTI, kbar

def ranks(x):
    u, inv, cnt = np.unique(x, return_inverse=True, return_counts=True)
    return (np.cumsum(cnt) - (cnt - 1) / 2.0)[inv]

def spearman(a, b):
    ra, rb = ranks(a), ranks(b)
    if ra.std() == 0 or rb.std() == 0: return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])

def X_of(cols): return np.column_stack([np.ones(len(cols[0]))] + list(cols))

def r2_in(X, y):
    b = np.linalg.lstsq(X, y, rcond=None)[0]; return 1 - ((y - X @ b) ** 2).sum() / ((y - y.mean()) ** 2).sum()

def cv_e2(X, y, reps=10, folds=5, seed=0):
    """Квадрат ошибки вне выборки для каждого наблюдения (среднее по повторам разбиений)."""
    n = len(y); rng = np.random.default_rng(seed); acc = np.zeros(n)
    for _ in range(reps):
        idx = rng.permutation(n); parts = np.array_split(idx, folds)
        for p in parts:
            tr = np.setdiff1d(idx, p); b = np.linalg.lstsq(X[tr], y[tr], rcond=None)[0]; acc[p] += (y[p] - X[p] @ b) ** 2
    return acc / reps

def boot_mean(d, B=2000, seed=1):
    rng = np.random.default_rng(seed); n = len(d); m = d[rng.integers(0, n, (B, n))].mean(1)
    return np.percentile(m, [2.5, 97.5])

def analyse(rows, topo, mech, th, out):
    sel = [r for r in rows if r['topo'] == topo and r['mech'] == mech and out in r]
    if not sel: return None
    y = np.array([r[out] for r in sel]); P = np.array([predictors(r, th) for r in sel]); FS, KS, kb = P.T
    var = y.var()
    if var < 1e-14 or FS.std() == 0: return dict(skip=True)
    e = {name: cv_e2(X_of(cols), y) for name, cols in dict(F=[FS], K=[KS], B=[kb], FB=[FS, kb], FK=[FS, KS], FBK=[FS, kb, KS]).items()}
    cv = lambda n: 1 - e[n].mean() / var
    d1 = (e['F'] - e['FK']) / var; d2 = (e['FB'] - e['FBK']) / var; d3 = (e['F'] - e['K']) / var     # положит. = KSTI лучше
    rho_f, rho_k = abs(spearman(FS, y)), abs(spearman(KS, y))
    rng = np.random.default_rng(2); n = len(y); dr = []
    for _ in range(1000):
        i = rng.integers(0, n, n); dr.append(abs(spearman(KS[i], y[i])) - abs(spearman(FS[i], y[i])))
    return dict(n=n, r2_FS=r2_in(X_of([FS]), y), r2_KS_on_FS=r2_in(X_of([FS]), KS), cvFS=cv('F'), cvKS=cv('K'),
                dCV_FS=(d1.mean(), *boot_mean(d1)), dCV_FSk=(d2.mean(), *boot_mean(d2)), dCV_KvsFS=(d3.mean(), *boot_mean(d3)),
                rho_FS=rho_f, rho_KSTI=rho_k, drho=(rho_k - rho_f, *np.nanpercentile(dr, [2.5, 97.5])), nFS=len(np.unique(FS)))

if __name__ == '__main__':
    t0 = time.time(); rows = collect(); print("данные: %d наблюдений, %.0f с" % (len(rows), time.time() - t0))
    ok = lambda lo, hi: "да" if (lo > 0 or hi < 0) else "нет"
    # --- 1. воспроизведение проверки из концепции: R² KSTI ~ FS
    print("\n1. R² регрессии KSTI на FS (θ = 10%) по стратам:")
    for topo in (0, 1):
        for mech in MECHS:
            sel = [r for r in rows if r['topo'] == topo and r['mech'] == mech]; P = np.array([predictors(r, .10) for r in sel])
            print("   topo=%d %-4s R²=%.4f" % (topo, mech, r2_in(X_of([P[:, 0]]), P[:, 1])))
    # --- 2. основная таблица: θ = 10%, механизм none
    print("\n2. θ = 10%, механизм none: добавочная информация KSTI (ΔR² вне выборки, 95%% ДИ; «знач.» = ДИ без нуля)")
    print("   %-5s %-4s %6s %6s | %-27s | %-27s | %s" % ("сеть", "исх", "R²(FS)", "R²cv", "Δ KSTI | FS", "Δ KSTI | FS,k̄", "ρ: FS / KSTI (Δ, знач.)"))
    for topo in (0, 1):
        for out in OUTS:
            a = analyse(rows, topo, 'none', .10, out)
            if a is None or a.get('skip'): print("   topo=%d %-3s пропуск (нет вариации)" % (topo, out)); continue
            f = lambda t: "%+.4f [%+.4f;%+.4f] %s" % (*t, ok(t[1], t[2]))
            print("   topo=%d %-3s %6.3f %6.3f | %s | %s | %.3f / %.3f (%+.3f, %s)" % (topo, out, a['r2_FS'], a['cvFS'], f(a['dCV_FS']), f(a['dCV_FSk']), a['rho_FS'], a['rho_KSTI'], a['drho'][0], ok(a['drho'][1], a['drho'][2])))
    # --- 3. сводка по всем сочетаниям: две базы сравнения
    print("\n3. Сводка: все θ x страты x механизмы (ΔR²cv от добавления KSTI; «практически значимо» = ДИ > 0 и Δ >= 0,01)")
    for outset, label in ((('A2', 'A2S'), "независимые исходы (A2, A2S)"), (('A1', 'A1S'), "исходы из c1 (A1, A1S), связь частично механическая")):
        for key, base in (('dCV_FSk', "база FS + средний k (честная)"), ('dCV_FS', "база только FS (k̄ не учтён: KSTI подменяет k̄)")):
            vals = []; pos = neg = 0
            for th in THETAS:
                for topo in (0, 1):
                    for mech in MECHS:
                        for out in outset:
                            a = analyse(rows, topo, mech, th, out)
                            if a is None or a.get('skip'): continue
                            m, lo, hi = a[key]; vals.append(m); pos += (lo > 0 and m >= 0.01); neg += (hi < 0 and m <= -0.01)
                            if key == 'dCV_FSk': pass
            v = np.array(vals); print("   %s | %s: %d сравнений | медиана %+.4f, макс %+.4f, мин %+.4f | практически лучше с KSTI: %d, хуже: %d" % (label, base, len(v), np.median(v), v.max(), v.min(), pos, neg))
    print("\nвремя: %.0f с" % (time.time() - t0))
