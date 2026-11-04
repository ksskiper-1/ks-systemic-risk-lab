"""Пошаговая запись каскада для визуализации.

Это ТА ЖЕ логика, что в engine.casc_support (поддержка) и engine.casc_batch (без поддержки),
но с записью волн. Движок не изменён; совпадение счёта проверяется в check_trace.py.
"""
import numpy as np
from engine import EPS


def trace(E, K0, R, L0, G=0.0, order=None, support=False):
    """Возвращает dict:
       steps   - список волн; steps[0] = прямые дефолты от шока, steps[t] = новые дефолты на волне t
       ratios  - ratios[t][i] = потери банка i / его капитал после шага t (>=1: банк упадёт на следующей волне)
       rescued - список списков: кого спасли на каждой волне (та же длина, что и steps; для волны 0 пусто)
       secondary - число вторичных дефолтов (как в engine)
    """
    K = np.asarray(K0, float).copy()
    L0 = np.asarray(L0, float)
    direct = L0 >= K - EPS
    D = direct.copy()
    Gl = float(G)
    steps = [list(np.where(direct)[0])]
    rescued = [[]]
    def ratio():
        L = L0 + (1 - R) * (E @ D.astype(float))
        r = L / K
        brink = L >= K - EPS                      # ровно то же условие, что и в каскаде
        r = np.where(brink, np.maximum(r, 1.0), np.minimum(r, 0.999))   # округление не должно менять «на грани / держится»
        return np.round(np.clip(r, 0, 1.5), 3).tolist()
    ratios = [ratio()]          # доля капитала, уже потерянная каждым банком, после каждого шага
    while True:
        L = L0 + (1 - R) * (E @ D.astype(float))
        new = (L >= K - EPS) & ~D
        if not new.any():
            break
        saved = []
        if support:
            for j in order:
                if new[j] and not direct[j]:
                    need = L[j] - K[j] + 1e-9
                    if need <= Gl:
                        K[j] += need
                        Gl -= need
                        new[j] = False
                        saved.append(int(j))
        D |= new
        steps.append(list(np.where(new)[0]))
        rescued.append(saved)
        ratios.append(ratio())
    return dict(steps=[[int(x) for x in s] for s in steps], rescued=rescued, ratios=ratios,
                secondary=int(D.sum() - direct.sum()), budget_left=Gl)
