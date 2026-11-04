"""Ядро непрерывного заражения (мера типа DebtRank на потере капитала). Движок engine.py не изменён.

Модель. h_i = min(1, L_i / K_i) - доля капитала банка i, уже потерянная.
Потери пересчитываются с нуля на каждом шаге (повторного учёта нет):
        L = L0 + (1 - R) * E @ h ,   h = min(1, L / K)
Предел «порог»: h = 1[L >= K], это ровно каскад дефолтов из engine.py (проверяется в check_contagion.py).

Метрика (абсолютная потеря в единицах активов, нормировка на суммарные активы):
        S_total = sum_i min(L_i, K_i) / sum(A)
        S_ind   = sum_i [min(L_i, K_i) - min(L0_i, K_i)] / sum(A)    (потери, вызванные заражением; аналог «вторичных» дефолтов)
K в метрике - начальный капитал, переданный в функцию (для механизма «резервы» это капитал с резервами);
вливания поддержки в K метрики НЕ входят, их стоимость возвращается отдельно (spent).
Единицы: как и в engine, шок s*A_i; E[i, j] - требование банка i к банку j, при стрессе j теряет кредитор i.
"""
import numpy as np
from engine import (EPS, SGRID, SMAX, DS, _trapz, order_by_liab, mech_setup)

TOL = 1e-12
MAXIT = 200000


# ---------- распространение стресса ----------
def propagate_batch(E, K, R, L0, mode='linear'):
    """Без поддержки. L0: (m, N). Возвращает (L, H): итоговые потери и доли стресса, (m, N).
    Сошедшиеся строки замораживаются, поэтому вблизи критического режима (спектральный радиус
    матрицы (1-R)E/K около 1, сходимость медленная) считаются только оставшиеся строки."""
    K = np.asarray(K, float); L0 = np.asarray(L0, float)
    thr = mode == 'threshold'
    H = (L0 >= K - EPS).astype(float) if thr else np.minimum(1.0, L0 / K)
    active = np.arange(len(L0))
    for it in range(MAXIT):
        Ha = H[active]; L = L0[active] + (1 - R) * (Ha @ E.T)
        Hn = np.maximum(Ha, (L >= K - EPS).astype(float)) if thr else np.minimum(1.0, L / K)
        H[active] = Hn
        active = active[np.abs(Hn - Ha).max(1) >= TOL]
        if len(active) == 0:
            break
    else:
        raise RuntimeError("заражение не сошлось: %d строк, критический режим" % len(active))
    return L0 + (1 - R) * (H @ E.T), H


def propagate_one(E, K0, R, L0, G=0.0, order=None, support=False, mode='linear', target=1.0):
    """Одна строка L0 (N,). С поддержкой (правило как в engine.casc_support: очередь order, вливание дефицита,
    банки, упавшие от шока, не спасаются, неподъёмные пропускаются, спасённый банк может упасть снова).
    target - доля потерянного капитала ПОСЛЕ спасения (только mode='linear'): вливание = L/target - K.
    target = 1 даёт ровно вливание дефицита (как в движке); в mode='threshold' параметр не используется.
    Возвращает dict(L, H, K, spent, iters)."""
    if not 0 < target <= 1:
        raise ValueError("target должен быть в (0, 1]: доля потерянного капитала после спасения")
    K = np.asarray(K0, float).copy(); L0 = np.asarray(L0, float)
    direct = L0 >= K - EPS; Gl = float(G)
    if mode == 'threshold':
        D = direct.copy(); it = 0
        while True:
            L = L0 + (1 - R) * (E @ D.astype(float))
            new = (L >= K - EPS) & ~D
            if not new.any():
                break
            if support:
                for j in order:
                    if new[j] and not direct[j]:
                        need = L[j] - K[j] + 1e-9
                        if need <= Gl:
                            K[j] += need; Gl -= need; new[j] = False
            D |= new; it += 1
        return dict(L=L, H=D.astype(float), K=K, spent=float(G) - Gl, iters=it)
    h = np.minimum(1.0, L0 / K)
    for it in range(MAXIT):
        L = L0 + (1 - R) * (E @ h)
        rescued = False
        if support:
            brink = (L >= K - EPS) & ~direct
            for j in order:
                if brink[j]:
                    need = L[j] / target - K[j] + 1e-9
                    if need <= Gl:
                        K[j] += need; Gl -= need; rescued = True
        hn = np.minimum(1.0, L / K)
        done = np.abs(hn - h).max() < TOL and not rescued
        h = hn
        if done:
            break
    else:
        raise RuntimeError("заражение с поддержкой не сошлось")
    return dict(L=L0 + (1 - R) * (E @ h), H=h, K=K, spent=float(G) - Gl, iters=it)


def final_losses(E, K, R, L0, G=0.0, order=None, support=False, mode='linear', target=1.0):
    """L0: (m, N) -> итоговые потери (m, N) и затраты на поддержку (m,)."""
    if not support:
        return propagate_batch(E, K, R, L0, mode)[0], np.zeros(len(L0))
    res = [propagate_one(E, K, R, l, G, order, True, mode, target) for l in L0]
    return np.array([r['L'] for r in res]), np.array([r['spent'] for r in res])


# ---------- диагностика режима (T1) ----------
SAT_TOL = 1e-9          # банк считается насыщенным, если h_i >= 1 - SAT_TOL


def M_matrix(E, K, R):
    """M = diag(1/K) (1-R) E: M[i, j] = (1-R) E[i, j] / K_i (строка делится на капитал КРЕДИТОРА i).
    Линеаризация динамики при h < 1: h = h0 + M h, то есть L = L0 + K * (M @ h)."""
    K = np.asarray(K, float)
    return (1 - R) * np.asarray(E, float) / K[:, None]


def spectral_radius(E, K, R):
    """rho = max |собственных значений| матрицы M = diag(1/K)(1-R)E.
    rho < 1: линеаризованная передача затухает; rho > 1: усиливается (вплоть до насыщения h = 1).
    Замечание: спектр diag(1/K)E совпадает со спектром E diag(1/K) и E^T, поэтому rho сам по себе
    не проверяет ориентацию E; ориентацию проверяет связь M с динамикой (check_contagion.py, блок 8)."""
    return float(np.abs(np.linalg.eigvals(M_matrix(E, K, R))).max())


def saturated_share(E, A, K, R, s_ref=0.01):
    """Доля банков с h_i >= 1 - SAT_TOL после распространения при общем шоке L0 = s_ref * A
    (непрерывная модель, без помощи). Учитываются все банки, в том числе насыщенные самим шоком
    (L0_i >= K_i); при s_ref = 0,01 и штатном капитале (k_i >= 0,04) таких нет.
    A нужен для формирования шока s_ref * A."""
    A = np.asarray(A, float)
    _, H = propagate_batch(E, K, R, (s_ref * A)[None, :])
    return float((H[0] >= 1 - SAT_TOL).mean())


# ---------- метрики ----------
def induced_S(E, K, A, R, L0, G=0.0, order=None, support=False, mode='linear', target=1.0, total=False):
    """S_ind (или S_total при total=True) для каждой строки L0; плюс затраты на поддержку."""
    L, spent = final_losses(E, K, R, L0, G, order, support, mode, target)
    lost = np.minimum(L, K) - (0.0 if total else np.minimum(L0, K))
    return lost.sum(1) / A.sum(), spent


def single_curves(E, K, A, R, G, order, support, mode, target):
    """S_ind(s) при шоке s*A_i на ОДНОМ банке i, i = 0..N-1; кривая (N, len(SGRID)).
    При s >= k_i (L0_i >= K_i) банк целиком в стрессе, и результат от s больше не зависит
    (как ступенька в движке), поэтому считаем только участок s < k_i и одно значение для хвоста."""
    N = len(A); k = K / A; out = np.zeros((N, len(SGRID))); spent_tail = np.zeros(N); S_tail = np.zeros(N)
    for i in range(N):
        m = SGRID < k[i] - 1e-12
        rows = np.zeros((int(m.sum()) + 1, N)); rows[:-1, i] = SGRID[m] * A[i]; rows[-1, i] = K[i]
        S, sp = induced_S(E, K, A, R, rows, G, order, support, mode, target)
        out[i, m] = S[:-1]; out[i, ~m] = S[-1]; spent_tail[i] = sp[-1]; S_tail[i] = S[-1]
    return out, spent_tail, S_tail


def metrics_S(E, A, Kb, mech, R=0.4, rho=None, Gabs=None, mode='linear', target=1.0, s_ref=0.01):
    """Аналог engine.metrics для метрики S. Ключи:
       A1S  - интеграл по s от S_ind(s) для шока одного банка, усреднённый по инициаторам с весами w_i = A_i / sum(A)
       A2S  - интеграл по s от S_ind(s) при общем шоке s*A
       A2St - то же для S_total (с прямыми потерями)
       S06/S08/S10 - S_ind при общем шоке 6/8/10%
       S1   - S_ind при L0_i = K_i (банк i полностью потерял капитал), вектор по банкам (карта уязвимости);
              считается напрямую, а не как конец кривой, поэтому верно и при k_i > SMAX
       cost1  - средние по банкам затраты на поддержку при L0_i = K_i (по одному значению на банк)
       cost_g - средние затраты на поддержку при общем шоке по узлам сетки s (301 значение).
       Это разные способы усреднения, прямо сравнивать cost1 и cost_g нельзя.
       rho       - спектральный радиус M = diag(1/K)(1-R)E, K - капитал механизма (для 'res' с резервами)
       sat_share - saturated_share(E, A, K, R, s_ref): доля банков с h ~ 1 при общем шоке s_ref*A,
                   всегда непрерывная модель БЕЗ помощи (поддержка и mode на неё не влияют).
       Внимание: аргумент rho - это ставка резервов для mech_setup, а ключ 'rho' в выводе - спектральный радиус."""
    N = len(A); w = A / A.sum()
    K, G, sup = mech_setup(mech, Kb, A, rho, Gabs); order = order_by_liab(E)
    curves, sp1, S1 = single_curves(E, K, A, R, G, order, sup, mode, target)
    A1S = float((w * _trapz(curves, dx=DS, axis=1)).sum())
    L0g = SGRID[:, None] * A[None, :]
    Sg, spg = induced_S(E, K, A, R, L0g, G, order, sup, mode, target)
    St, _ = induced_S(E, K, A, R, L0g, G, order, sup, mode, target, total=True)
    idx = lambda s: int(round(s / DS))
    return dict(A1S=A1S, A2S=float(_trapz(Sg, dx=DS)), A2St=float(_trapz(St, dx=DS)),
                S06=Sg[idx(.06)], S08=Sg[idx(.08)], S10=Sg[idx(.10)], S1=S1, Sg=Sg,
                cost1=float(sp1.mean()), cost_g=float(spg.mean()),
                rho=spectral_radius(E, K, R), sat_share=saturated_share(E, A, K, R, s_ref))
