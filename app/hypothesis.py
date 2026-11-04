"""Раздел «Проверка гипотезы»: расчёт T, доверительного интервала и вердикта (протокол v1.3, base seed 2026).
Логика повторяет run_main.py; результаты по сетям кэшируются, поэтому повторные запуски мгновенные."""
import json, os, time
import numpy as np
import streamlit as st
from engine import gen_net, metrics

BASE, PILOT = 2026, 7777
MECH = ('none', 'res', 'sup')
HERE = os.path.dirname(os.path.abspath(__file__))


def precomputed():
    with open(os.path.join(HERE, 'precomputed.json')) as f:
        return json.load(f)


@st.cache_data(show_spinner=False, max_entries=4000)
def rep_cached(rep):
    """Одна реализация: A (шок одного банка, общий шок) для 2 топологий x 3 механизмов."""
    out = np.zeros((2, 3, 2))
    for topo in (0, 1):
        E, A, Kb = gen_net(topo, rep, base=BASE)
        for mi, m in enumerate(MECH):
            r = metrics(E, A, Kb, m); out[topo, mi] = [r['A1'], r['A2']]
    return out


def series(n, progress=None):
    out = np.zeros((n, 2, 3, 2))
    for rep in range(n):
        out[rep] = rep_cached(rep)
        if progress and (rep % 10 == 0 or rep == n - 1):
            progress(rep + 1, n)
    return out


@st.cache_data(show_spinner=False)
def pilot_delta():
    """Порог практической значимости: 10% медианы A (распределённая сеть, без поддержки) на пилотных сетях seed 7777."""
    a1, a2 = [], []
    for rep in range(100):
        E, A, Kb = gen_net(0, rep, base=PILOT); r = metrics(E, A, Kb, 'none'); a1.append(r['A1']); a2.append(r['A2'])
    return float(0.1 * max(np.median(a1), np.median(a2)))


def effects(o):
    """T = Δ(один банк) − Δ(общий шок); Δ = эффект поддержки в концентрированной минус в распределённой сети."""
    d = o[:, :, 2, :] - o[:, :, 0, :]; m = d.mean(0)
    Ds = m[1, 0] - m[0, 0]; Dg = m[1, 1] - m[0, 1]
    return float(Ds - Dg), float(Ds), float(Dg), d


def boot(d, B=10000, seed=2026, chunk=1000):
    """Bootstrap: сети пересэмплируются независимо по топологии, пары остаются внутри сети. Тот же поток чисел, что в study.T_boot."""
    r = np.random.default_rng(seed); n = d.shape[0]
    i0 = r.integers(0, n, (B, n)); i1 = r.integers(0, n, (B, n))
    d0, d1 = d[:, 0, :], d[:, 1, :]; Dd = np.empty((B, 2))
    for a in range(0, B, chunk):
        b = min(B, a + chunk); Dd[a:b] = d1[i1[a:b]].mean(1) - d0[i0[a:b]].mean(1)
    q = lambda x: [float(v) for v in np.percentile(x, [2.5, 97.5])]
    return q(Dd[:, 0] - Dd[:, 1]), q(Dd[:, 0]), q(Dd[:, 1])


def analyse(mode, n_free=100, progress=None):
    t0 = time.time(); delta = pilot_delta(); path = []
    n = 100 if mode == 'proto' else int(n_free)
    while True:
        o = series(n, progress); T, Ds, Dg, d = effects(o)
        ci, ci_s, ci_g = boot(d); w = ci[1] - ci[0]
        path.append(dict(n=n, T=T, lo=ci[0], hi=ci[1], width=w))
        if mode != 'proto' or w <= delta or n >= 1000:
            break
        n = {100: 300, 300: 1000}[n]
    cps = []
    for k in sorted({k for k in (10, 20, 50, 100, 200, 300, 500, 1000, n) if k <= n}):
        Tk, _, _, dk = effects(o[:k]); c = boot(dk, B=3000)[0]; cps.append(dict(n=k, T=Tk, lo=c[0], hi=c[1]))
    return dict(mode=mode, n=n, T=T, Ds=Ds, Dg=Dg, ci=ci, ci_s=ci_s, ci_g=ci_g, delta=delta, path=path, cps=cps, secs=time.time() - t0)


def verdict(res):
    """Правила исхода из run_main.py (заданы заранее)."""
    T, (lo, hi), delta = res['T'], res['ci'], res['delta']
    grid = precomputed()['grid']
    sg = float(np.mean([np.sign(c['T']) == np.sign(T) for c in grid]))
    excl0 = lo > 0 or hi < 0; big = abs(T) >= delta; inside = lo >= -delta and hi <= delta
    if excl0 and big and sg >= 0.9: v = 'supported'
    elif inside: v = 'not_supported'
    else: v = 'unstable'
    return dict(v=v, excl0=bool(excl0), big=bool(big), inside=bool(inside), sign_share=sg, n_grid=len(grid), same_sign=int(round(sg * len(grid))))
