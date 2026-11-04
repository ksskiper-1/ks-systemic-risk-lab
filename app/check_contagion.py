"""Проверки ядра contagion.py. Ожидается: все строки заканчиваются на 'нарушений: 0' (или 'OK')."""
import time
import numpy as np
from engine import *
from engine import EPS
import contagion as C

t0 = time.time()
FAILS = 0
def report(name, bad, n):
    global FAILS; FAILS += int(bad > 0); print(f"{name}: нарушений: {bad} / {n}")

# 1. Предел «порог» совпадает с движком (число вторичных дефолтов), все три механизма, общий и одиночный шок
bad = n = 0
for rep in range(5):
    for topo in (0, 1):
        E, A, Kb = gen_net(topo, rep, base=2026)
        for mech in ('none', 'res', 'sup'):
            K, G, sup = mech_setup(mech, Kb, A); order = order_by_liab(E)
            rows = [s * A for s in (0.03, 0.05, 0.07, 0.09, 0.12, 0.15)] + [np.eye(25)[i] * K[i] for i in range(25)]
            L0 = np.array(rows)
            ref = secondary(E, K, 0.4, L0, G, order, sup)
            direct = (L0 >= K - EPS).sum(1)
            if sup:
                got = np.array([C.propagate_one(E, K, 0.4, l, G, order, True, 'threshold')['H'].sum() for l in L0]) - direct
            else:
                got = C.propagate_batch(E, K, 0.4, L0, 'threshold')[1].sum(1) - direct
            n += len(L0); bad += int((np.round(got) != ref).sum())
report("1. предел «порог» = движок", bad, n)

# 2. Ручная сеть из трёх банков: цепочка 2 -> 1 -> 0 (банк 0 кредитует 1, банк 1 кредитует 2)
E3 = np.zeros((3, 3)); E3[0, 1] = 10; E3[1, 2] = 10
K3 = np.full(3, 10.0); A3 = np.full(3, 100.0); R = 0.4
L0 = np.array([[0, 0, 5.0]])
L, H = C.propagate_batch(E3, K3, R, L0)
exact = np.array([(1 - R) * 10 * 0.3, (1 - R) * 10 * 0.5, 5.0])      # L0 = 1,8; 3,0; 5,0
exact = np.array([0.6 * 10 * 0.3, 0.6 * 10 * 0.5, 5.0])
bad = int(not np.allclose(L[0], exact, atol=1e-10))
S, _ = C.induced_S(E3, K3, A3, R, L0)
bad += int(abs(S[0] - (exact[0] + exact[1]) / 300) > 1e-12)
report("2. ручная сеть 3 банка (L = 1,8; 3,0; 5,0; S = 0,016)", bad, 2)

# 3. Свойства: R=1 -> передачи нет; нет связей -> передачи нет; S ограничена; сходимость и неподвижная точка; нет двойного счёта
bad = n = 0
for rep in range(4):
    for topo in (0, 1):
        E, A, Kb = gen_net(topo, rep, base=2026)
        for mech in ('none', 'res'):
            K, G, sup = mech_setup(mech, Kb, A)
            L0 = np.vstack([SGRID[:, None] * A[None, :], np.array([np.eye(25)[i] * K[i] * 0.8 for i in range(25)])])
            L1, _ = C.propagate_batch(E, K, 1.0, L0); bad += int(not np.allclose(L1, L0)); n += 1          # R = 1
            Lz, _ = C.propagate_batch(np.zeros_like(E), K, 0.4, L0); bad += int(not np.allclose(Lz, L0)); n += 1   # нет связей
            L, H = C.propagate_batch(E, K, 0.4, L0)
            resid = np.abs(L - (L0 + 0.6 * (np.minimum(1, L / K) @ E.T))).max()                               # неподвижная точка
            bad += int(resid > 1e-8); n += 1
            St, _ = C.induced_S(E, K, A, 0.4, L0, total=True); bad += int((St > K.sum() / A.sum() + 1e-12).any() or (St < -1e-12).any()); n += 1
            Si, _ = C.induced_S(E, K, A, 0.4, L0); bad += int((Si < -1e-12).any()); n += 1
            Lt, _ = C.propagate_batch(E, K, 0.4, L0, 'threshold'); bad += int((L < Lt - 1e-9).any()); n += 1   # линейная >= пороговой
            Stot, _ = C.induced_S(E, K, A, 0.4, SGRID[:, None] * A[None, :], total=True); bad += int((np.diff(Stot) < -1e-12).any()); n += 1  # S_total монотонна по s
            Sg, _ = C.induced_S(E, K, A, 0.4, SGRID[:, None] * A[None, :]); Sd = np.minimum(SGRID[:, None] * A[None, :], K).sum(1) / A.sum()
            bad += int(not np.allclose(Sg, Stot - Sd, atol=1e-12)); n += 1                                   # S_ind = S_total - S_прямые (S_ind может убывать, как число вторичных дефолтов)
report("3. свойства (R=1, нет связей, границы, неподвижная точка, линейная >= пороговой, S_total монотонна, тождество S_ind)", bad, n)

# 4. Хвост кривой одиночного шока: при s >= k_i результат не зависит от s
bad = n = 0
for rep in range(3):
    E, A, Kb = gen_net(0, rep, base=2026); K, G, sup = mech_setup('none', Kb, A)
    for i in range(25):
        rows = np.zeros((3, 25)); rows[0, i] = K[i]; rows[1, i] = 0.12 * A[i]; rows[2, i] = 0.15 * A[i]
        S, _ = C.induced_S(E, K, A, 0.4, rows); n += 1; bad += int(not np.allclose(S, S[0], atol=1e-12))
report("4. хвост одиночного шока постоянен", bad, n)

# 5. Воспроизводимость
E, A, Kb = gen_net(1, 3, base=2026)
a = C.metrics_S(E, A, Kb, 'sup'); b = C.metrics_S(E, A, Kb, 'sup')
report("5. одинаковые входы -> одинаковые числа", int(a['A1S'] != b['A1S'] or a['A2S'] != b['A2S']), 1)

# 6. Поддержка: затраты не больше бюджета; предел «порог» с поддержкой совпал в п.1 (mech='sup')
bad = n = 0
for rep in range(3):
    for topo in (0, 1):
        E, A, Kb = gen_net(topo, rep, base=2026); K, G, sup = mech_setup('sup', Kb, A); order = order_by_liab(E)
        for l in [s * A for s in (0.05, 0.08, 0.12)]:
            for mode, tg in (('threshold', 1.0), ('linear', 1.0), ('linear', 0.5)):
                r = C.propagate_one(E, K, 0.4, l, G, order, True, mode, tg); n += 1; bad += int(r['spent'] > G + 1e-9)
report("6. затраты на поддержку <= бюджет", bad, n)

# 7. S1 корректен и при k_i > SMAX; target вне (0, 1] отвергается
Ek = np.array([[0., 100.], [100., 0.]]); Ak = np.full(2, 100.); Kk = np.full(2, 20.)
bad = int(not np.allclose(C.metrics_S(Ek, Ak, Kk, 'none', R=.9)['S1'], C.induced_S(Ek, Kk, Ak, .9, np.diag(Kk))[0]))
E2 = np.array([[0., 20.], [0., 0.]]); n = 1
for tg in (0.0, -1.0, 2.0):
    n += 1
    try: C.propagate_one(E2, np.full(2, 10.), .4, np.array([0., 10.]), 3., order_by_liab(E2), True, 'linear', tg); bad += 1
    except ValueError: pass
report("7. S1 при k_i > SMAX; невалидный target отвергается", bad, n)

# 8. Диагностика режима (T1): spectral_radius, saturated_share, ключи rho и sat_share в metrics_S
bad = n = 0
E2s = np.array([[0., 50.], [50., 0.]]); K2 = np.full(2, 10.); A2 = np.full(2, 100.)
n += 1; bad += int(abs(C.spectral_radius(E2s, K2, 0.4) - 3.0) > 1e-12)                       # 0,6*50/10 = 3
n += 1; bad += int(C.saturated_share(E2s, A2, K2, 0.4) != 1.0)                               # насыщение уже при 1% (пример аудита)
# нулевая E при капитале, не исчерпанном прямым шоком (K = 10 > s_ref*A = 1): rho = 0, sat_share = 0
Z = np.zeros((3, 3)); Kz = np.full(3, 10.); Az = np.full(3, 100.)
n += 1; bad += int(C.spectral_radius(Z, Kz, 0.4) != 0.0)
n += 1; bad += int(C.saturated_share(Z, Az, Kz, 0.4) != 0.0)
# та же нулевая E, но K = 0,5 < s_ref*A: банки насыщены самим шоком, sat_share = 1 (определение учитывает все банки)
n += 1; bad += int(C.saturated_share(Z, Az, np.full(3, 0.5), 0.4) != 1.0)
# ручной пример: E[0,1] = 30, K = 10, A = 100, R = 0,4, общий шок 5%: h1 = 0,5; L0 = 5 + 0,6*30*0,5 = 14 -> h0 = 1; доля 1/3
E3s = np.zeros((3, 3)); E3s[0, 1] = 30.
n += 1; bad += int(abs(C.saturated_share(E3s, Az, Kz, 0.4, s_ref=0.05) - 1 / 3) > 1e-15)
n += 1; bad += int(C.saturated_share(E3s, Az, Kz, 0.4, s_ref=0.01) != 0.0)                   # при 1%: L0 = 1 + 1,8 = 2,8 < 10
# ориентация M: M[i,j] = (1-R) E[i,j] / K_i, и итог динамики удовлетворяет L = L0 + K * (M @ h)
E, A, Kb = gen_net(1, 0, base=2026); K, _, _ = mech_setup('res', Kb, A); M = C.M_matrix(E, K, 0.4)
n += 1; bad += int(not np.allclose(M[3, 7], 0.6 * E[3, 7] / K[3]) or not np.allclose(M, 0.6 * E / K[:, None]))
L0 = 0.01 * A; L, H = C.propagate_batch(E, K, 0.4, L0[None, :])
n += 1; bad += int(np.abs(L[0] - (L0 + K * (M @ H[0]))).max() > 1e-9)
# свойства на сетях: sat_share в [0, 1] и кратна 1/N; rho >= 0 и линеен по alpha; ключи metrics_S согласованы с функциями;
# sat_share = 1 <=> S_total(s_ref) на потолке sum(K)/sum(A); повторный вызов даёт те же числа
for rep in range(3):
    for topo in (0, 1):
        r05 = C.spectral_radius(*gen_net(topo, rep, base=2026)[::2], 0.4)
        for al in (0.05, 0.10, 0.12, 0.5):
            E, A, Kb = gen_net(topo, rep, alpha=al, base=2026)
            r = C.spectral_radius(E, Kb, 0.4); n += 1; bad += int(r < 0 or abs(r - r05 * al / 0.5) > 1e-9 * max(1, r05))
            for mech in ('none', 'res'):
                K, _, _ = mech_setup(mech, Kb, A); sh = C.saturated_share(E, A, K, 0.4)
                n += 1; bad += int(not 0 <= sh <= 1 or abs(sh * 25 - round(sh * 25)) > 1e-9)
                St, _ = C.induced_S(E, K, A, 0.4, (0.01 * A)[None, :], total=True)
                n += 1; bad += int((sh == 1.0) != bool(abs(St[0] - K.sum() / A.sum()) < 1e-9 * K.sum() / A.sum()))
                n += 1; bad += int(sh != C.saturated_share(E, A, K, 0.4))
E, A, Kb = gen_net(0, 1, base=2026)
for mech in ('none', 'res', 'sup'):
    m = C.metrics_S(E, A, Kb, mech); K, _, _ = mech_setup(mech, Kb, A)
    n += 1; bad += int(m['rho'] != C.spectral_radius(E, K, 0.4) or m['sat_share'] != C.saturated_share(E, A, K, 0.4))
report("8. диагностика режима (rho = 3 на 2 банках, нулевая E, ручной пример 1/3, ориентация M, sat_share в [0,1], rho ~ alpha, ключи metrics_S)", bad, n)

# 9. Пороги из предварительных запусков (results/exploration_alpha_sweep_S.txt; seed 2026, 60 сетей, R = 0,4, без помощи)
#    rho(топо 0): 0,46 при alpha = 0,05 и 4,58 при alpha = 0,5; rho пересекает 1 между 0,10 и 0,12 (около 0,11);
#    при alpha >= 0,15 S_total(1%) на потолке, то есть sat_share = 1; при alpha <= 0,12 насыщены не все.
#    Допуск: средние сравниваются с напечатанными двумя знаками (±0,005), пересечение по линейной интерполяции ±0,01.
bad = n = 0
mr = {}; ms = {}
for al in (0.05, 0.10, 0.12, 0.15, 0.20, 0.50):
    rr = []; ss = []
    for topo in (0, 1):
        for rep in range(60):
            E, A, Kb = gen_net(topo, rep, alpha=al, base=2026)
            if topo == 0: rr.append(C.spectral_radius(E, Kb, 0.4))
            ss.append(C.saturated_share(E, A, Kb, 0.4))
    mr[al] = np.mean(rr); ms[al] = np.mean(ss)
n += 1; bad += int(abs(mr[0.05] - 0.46) > 0.005)
n += 1; bad += int(abs(mr[0.50] - 4.58) > 0.005)
n += 1; bad += int(not (mr[0.10] < 1 < mr[0.12]))
cross = 0.10 + (1 - mr[0.10]) / (mr[0.12] - mr[0.10]) * 0.02
n += 1; bad += int(abs(cross - 0.11) > 0.01)
for al in (0.15, 0.20, 0.50): n += 1; bad += int(ms[al] != 1.0)
for al in (0.05, 0.10, 0.12): n += 1; bad += int(not ms[al] < 1.0)
report("9. пороги предварительных запусков (rho 0,46 / 4,58, пересечение 1 около alpha = 0,11 [получено %.3f], sat_share = 1 при alpha >= 0,15)" % cross, bad, n)

# 10. Значения протокола v1.4-ext 1.1 по умолчанию и граница насыщения (добавлено в T4 по решению автора 26.10)
#     Значения переписаны из протокола (раздел 3): s_ref = 0,01, SAT_TOL = 1e-9.
bad = n = 0
P_SREF, P_SATTOL = 0.01, 1e-9
n += 1; bad += int(C.saturated_share.__defaults__[-1] != P_SREF)                # s_ref по умолчанию в saturated_share
n += 1; bad += int(C.metrics_S.__defaults__[-1] != P_SREF)                      # s_ref по умолчанию в metrics_S
n += 1; bad += int(C.SAT_TOL != P_SATTOL)
# граница: нулевая E, A = 100, шок 10% (L0 = 10); K = 10 -> h = 1 (насыщен), K = 10/(1 - 1e-6) -> h = 1 - 1e-6 (не насыщен),
# K = 20 -> h = 0,5; ожидаемая доля 1/3
Zb = np.zeros((3, 3)); Ab = np.full(3, 100.); Kb3 = np.array([10., 10. / (1 - 1e-6), 20.])
_, Hb = C.propagate_batch(Zb, Kb3, 0.4, (0.1 * Ab)[None, :])
n += 1; bad += int(Hb[0, 0] != 1.0 or abs(Hb[0, 1] - (1 - 1e-6)) > 1e-12)       # граничные h получены именно такими
n += 1; bad += int(C.saturated_share(Zb, Ab, Kb3, 0.4, s_ref=0.1) != 1 / 3)
n += 1; bad += int(C.saturated_share(np.zeros((1, 1)), Ab[:1], Kb3[1:2], 0.4, s_ref=0.1) != 0.0)   # h = 1 - 1e-6 -> 0
n += 1; bad += int(C.saturated_share(np.zeros((1, 1)), Ab[:1], Kb3[:1], 0.4, s_ref=0.1) != 1.0)    # h = 1 -> 1
# ручной пример: 3 банка, E[0,1] = 100, K = 10, A = 100, R = 0,4.
#   s = 0,01: h1 = 0,1; L0 = 1 + 0,6*100*0,1 = 7  -> h0 = 0,7, доля 0
#   s = 0,02: h1 = 0,2; L0 = 2 + 0,6*100*0,2 = 14 -> h0 = 1,   доля 1/3
Eh = np.zeros((3, 3)); Eh[0, 1] = 100.; Kh = np.full(3, 10.); Ah = np.full(3, 100.)
_, H1 = C.propagate_batch(Eh, Kh, 0.4, (0.01 * Ah)[None, :])
_, H2 = C.propagate_batch(Eh, Kh, 0.4, (0.02 * Ah)[None, :])
n += 1; bad += int(abs(H1[0, 0] - 0.7) > 1e-12 or H2[0, 0] != 1.0)
n += 1; bad += int(C.saturated_share(Eh, Ah, Kh, 0.4) != 0.0)                    # по умолчанию (s_ref = 0,01)
n += 1; bad += int(C.saturated_share(Eh, Ah, Kh, 0.4, s_ref=0.01) != 0.0)
n += 1; bad += int(C.saturated_share(Eh, Ah, Kh, 0.4, s_ref=0.02) != 1 / 3)
report("10. значения протокола по умолчанию (s_ref = 0,01, SAT_TOL = 1e-9), граница h = 1 / 1 - 1e-6, ручной пример s_ref 0,01 -> 0 и 0,02 -> 1/3", bad, n)

print("время: %.1f с" % (time.time() - t0))
raise SystemExit(1 if FAILS else 0)
