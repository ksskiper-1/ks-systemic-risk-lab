"""s_trace.py — пошаговая запись непрерывного заражения (режим «Заражение (S)» интерфейса, T5).

Зачем отдельный модуль. Ядро contagion.py возвращает только равновесие (propagate_batch -> L, H),
промежуточных итераций оно не отдаёт, а менять ядро нельзя. Здесь та же итерация, что в
contagion.propagate_batch (mode='linear', без помощи), с тем же начальным состоянием, тем же порядком
арифметических операций, теми же TOL и MAXIT, но каждое состояние h_k сохраняется:
        h_0 = min(1, L0 / K)
        h_k = min(1, (L0 + (1 - R) * h_{k-1} @ E.T) / K),  k = 1, 2, ...
        стоп, когда max|h_k - h_{k-1}| < TOL.
Конечное состояние сверяется с ядром при каждом вызове: h_n должен побитно совпасть с H из
contagion.propagate_batch, иначе RuntimeError (запись не показывается). Итоговая метрика S_ind
берётся из contagion.induced_S, промежуточные S_ind,k считаются по той же формуле метрики
(сумма потерянного капитала K*h_k сверх прямого шока min(L0, K), делённая на сумму активов).

Помощь (резервы, поддержка) здесь не поддерживается: режим S в интерфейсе работает только без помощи.
"""
import numpy as np
import contagion as C

SHOW_MAX = 20        # сколько итераций показывать шагами; дальше последний шаг — равновесие ядра
SHOW_DH = 1e-4       # итерации после того, как max|Δh| < SHOW_DH, визуально неотличимы: показываем сразу итог


def s_trace(E, K, A, R, L0):
    """Пошаговая запись непрерывного заражения без помощи.

    Возвращает dict:
      h      - список массивов h по ПОКАЗЫВАЕМЫМ шагам (0 = шок, ..., последний = равновесие ядра)
      it     - номер итерации ядра для каждого показываемого шага (0, 1, 2, ..., n_iter)
      S      - S_ind на каждом показываемом шаге (доля суммарных активов); последний = contagion.induced_S
      S_dir  - прямые потери от шока: sum(min(L0, K)) / sum(A)
      sat    - число насыщенных банков (h >= 1 - SAT_TOL) на каждом шаге
      sat_tol- порог насыщения ядра contagion.SAT_TOL (передаётся в интерфейс, чтобы не дублировать константу)
      n_iter - число итераций до сходимости (как в ядре)
      h_all_n- длина полной записи (n_iter + 1)
    """
    E = np.asarray(E, float); K = np.asarray(K, float); A = np.asarray(A, float)
    L0 = np.asarray(L0, float)
    L0b = L0[None, :]
    H = np.minimum(1.0, L0b / K)                       # как в propagate_batch (mode='linear')
    hist = [H[0].copy()]
    for it in range(C.MAXIT):
        Ha = H; L = L0b + (1 - R) * (Ha @ E.T)         # тот же порядок операций, что в ядре
        Hn = np.minimum(1.0, L / K)
        H = Hn
        hist.append(H[0].copy())
        if np.abs(Hn - Ha).max(1)[0] < C.TOL:
            break
    else:
        raise RuntimeError("заражение не сошлось: критический режим")
    n_iter = len(hist) - 1

    # сверка с ядром: равновесие записи = равновесие propagate_batch (побитно)
    _, Hcore = C.propagate_batch(E, K, R, L0b)
    if not np.array_equal(Hcore[0], hist[-1]):
        raise RuntimeError("пошаговая запись S расходится с contagion.propagate_batch")
    S_core = float(C.induced_S(E, K, A, R, L0b)[0][0])

    # какие итерации показывать шагами
    show = [0]
    for k in range(1, n_iter + 1):
        if len(show) > SHOW_MAX - 1 or k == n_iter:
            break
        show.append(k)
        if np.abs(hist[k] - hist[k - 1]).max() < SHOW_DH:
            break
    if show[-1] != n_iter:
        show.append(n_iter)

    base = np.minimum(L0, K).sum()
    Ssum = A.sum()
    def S_of(h):
        return float((K * h).sum() - base) / Ssum
    S = [S_of(hist[k]) for k in show[:-1]] + [S_core]
    S = [max(0.0, x) for x in S]                        # шаг 0: K*min(1, L0/K) - min(L0, K) = 0 с точностью округления
    hs = [hist[k] for k in show]
    sat = [int((h >= 1 - C.SAT_TOL).sum()) for h in hs]
    return dict(h=hs, it=show, S=S, S_dir=float(base / Ssum), sat=sat, sat_tol=C.SAT_TOL, n_iter=n_iter, h_all_n=len(hist))


def s_curve(E, K, A, R, single):
    """Кривая S_ind(s) по сетке SGRID ядром contagion: общий шок (single=False) или
    шок одного банка, усреднённый по инициаторам с весами A_i / sum(A) (single=True), как A1S в metrics_S."""
    from engine import SGRID, order_by_liab
    if single:
        curves, _, _ = C.single_curves(E, K, A, R, 0.0, order_by_liab(E), False, 'linear', 1.0)
        return ((A / A.sum())[:, None] * curves).sum(0)
    return C.induced_S(E, K, A, R, SGRID[:, None] * A[None, :])[0]
