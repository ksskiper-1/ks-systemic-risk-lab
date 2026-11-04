"""Проверки run_S_sweep.py (T3). Расчётов на seed 2027 не выполняет.
Блоки 1-6 работают на подставных данных (быстро), блок 7 вызывает CLI в отдельных процессах.
Ненулевой код выхода при любом нарушении."""
import json, math, os, shutil, subprocess, sys, tempfile, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_S_sweep as RS

t0 = time.time(); TOTAL_BAD = 0


def report(name, bad, n):
    global TOTAL_BAD
    TOTAL_BAD += bad
    print("%s: нарушений: %d / %d" % (name, bad, n))


class FakeC:
    """Подмена contagion: детерминированные числа, несходимость по списку (alpha, topo, rep, base, part)."""
    SAT_TOL, TOL, MAXIT = 1e-9, 1e-12, 200000

    def __init__(self, fail=(), zero_pilot=False):
        self.fail = set(fail); self.zero_pilot = zero_pilot

    def _chk(self, E, part):
        al, topo, rep, base = E
        if (al, topo, rep, base, part) in self.fail:
            raise RuntimeError('подменная несходимость')

    def metrics_S(self, E, A, Kb, mech, R=0.4, s_ref=0.01):
        self._chk(E, 'metrics_S'); al, topo, rep, base = E
        if self.zero_pilot and base == RS.PILOT_BASE:
            return dict(A1S=0.0, A2S=0.0)
        v = 0.002 + 1e-4 * math.sin(rep + 10 * al) + (2e-5 if topo else 0.0)
        return dict(A1S=v / 2, A2S=v)

    def spectral_radius(self, E, K, R):
        return 9.0 * E[0]

    def saturated_share(self, E, A, K, R, s_ref):
        self._chk(E, 'saturated_share'); return 0.0


def fake_gen(topo, rep, N=25, alpha=0.5, base=2026):
    return (alpha, topo, rep, base), None, None


MAIN_BASE = 1234                       # основная серия в тестах не совпадает с пилотом (7777)


def run_fake(tmp, name, C, n=6, pn=5):
    pre = os.path.join(tmp, name)
    rows, pil, summ = RS.run_series(C, fake_gen, MAIN_BASE, n, pn, pre, 'test', {'x': 'y'})
    return pre, rows, pil, {s['alpha']: s for s in summ}


tmp = tempfile.mkdtemp(prefix='check_sweep_')
try:
    # 1. classify: правила 0-4 и границы
    bad = n = 0
    d = 1e-4
    cases = [((True, d, -1, 1), RS.LABEL_NONCONV), ((False, None, 0, 0), RS.LABEL_NONCONV),
             ((True, 0.0, 5, 6), RS.LABEL_NONCONV),
             ((False, 0.0, 1e-3, 2e-3), RS.LABEL_DEGEN), ((False, 0.0, -1e-3, 1e-3), RS.LABEL_DEGEN),
             ((False, 0.0, 0.0, 0.0), RS.LABEL_DEGEN),
             ((False, d, -0.5e-4, 0.5e-4), RS.LABEL_EQUIV), ((False, d, 0.1e-4, 0.5e-4), RS.LABEL_EQUIV),
             ((False, d, -d, 0.5e-4), RS.LABEL_UNCLEAR), ((False, d, -0.5e-4, d), RS.LABEL_UNCLEAR),
             ((False, d, 1.01e-4, 3e-4), RS.LABEL_DIFF), ((False, d, -3e-4, -1.01e-4), RS.LABEL_DIFF),
             ((False, d, d, 3e-4), RS.LABEL_UNCLEAR), ((False, d, -3e-4, -d), RS.LABEL_UNCLEAR),
             ((False, d, 0.5e-4, 3e-4), RS.LABEL_UNCLEAR), ((False, d, -3e-4, 3e-4), RS.LABEL_UNCLEAR)]
    for args, exp in cases:
        n += 1; bad += int(RS.classify(*args) != exp)
    report("1. ярлыки раздела 5 (несходимость, вырожденный порог, строгие границы ±δ_S, L > δ_S / U < -δ_S)", bad, n)

    # 2. bootstrap: парный, детерминирован, поток зависит только от α
    bad = n = 0
    dd = np.random.default_rng(0).normal(size=50)
    n += 1; bad += int(RS.boot_ci(dd, [2027, 100]) != RS.boot_ci(dd, [2027, 100]))
    n += 1; bad += int(RS.boot_ci(dd, [2027, 100]) == RS.boot_ci(dd, [2027, 120]))
    L, U = RS.boot_ci(dd, [2027, 100]); n += 1; bad += int(not L < dd.mean() < U)
    rng = np.random.default_rng([2027, 100]); Ds = dd[rng.integers(0, 50, (RS.B, 50))].mean(1)
    n += 1; bad += int(tuple(np.percentile(Ds, [2.5, 97.5])) != (L, U))
    report("2. bootstrap (B = 10000, seed [2027, round(1000α)], percentile 2,5/97,5)", bad, n)

    # 3. без сбоев: все строки ok, δ_S = 0,1 * медиана пилота, D = среднее парной разности, δ_S рядом с ярлыком
    bad = n = 0
    pre, rows, pil, S = run_fake(tmp, 'clean', FakeC())
    n += 1; bad += int(any(r['status'] != 'ok' for r in rows + pil))
    for al, s in S.items():
        pa = [r['A2S'] for r in pil if r['alpha'] == al]
        n += 1; bad += int(s['delta_S'] != 0.1 * float(np.median(pa)))
        dv = [next(r['A2S'] for r in rows if (r['alpha'], r['topo'], r['rep']) == (al, 1, k)) -
              next(r['A2S'] for r in rows if (r['alpha'], r['topo'], r['rep']) == (al, 0, k)) for k in range(6)]
        n += 1; bad += int(s['D'] != float(np.mean(dv)) or s['n_ok'] != 6 or bool(s['excluded_reps']))
        n += 1; bad += int('delta_S' not in s or s['label'] not in RS.LABELS)
    n += 1; bad += int(RS.verify(pre) != [])
    report("3. серия без сбоев (статусы ok, δ_S, D, n_ok, проверка формата)", bad, n)

    # 4. несходимость в основной серии: строка сохранена со статусом, ярлык α - «неполная сходимость»
    bad = n = 0
    fail = {(0.10, 1, 2, MAIN_BASE, 'metrics_S'), (0.12, 0, 4, MAIN_BASE, 'saturated_share')}
    pre, rows, pil, S = run_fake(tmp, 'nonconv', FakeC(fail))
    r1 = [r for r in rows if (r['alpha'], r['topo'], r['rep']) == (0.10, 1, 2)][0]
    r2 = [r for r in rows if (r['alpha'], r['topo'], r['rep']) == (0.12, 0, 4)][0]
    n += 1; bad += int(len(rows) != 8 * 2 * 6)                                   # ничего не выброшено
    n += 1; bad += int(r1['status'] != 'nonconv' or r1['nonconv_part'] != 'metrics_S' or not math.isnan(r1['A2S']))
    n += 1; bad += int(r2['status'] != 'nonconv' or r2['nonconv_part'] != 'saturated_share' or math.isnan(r2['A2S']))
    n += 1; bad += int(S[0.10]['label'] != RS.LABEL_NONCONV or S[0.10]['excluded_reps'] != [2] or S[0.10]['n_ok'] != 5)
    n += 1; bad += int(S[0.12]['label'] != RS.LABEL_NONCONV or S[0.12]['excluded_reps'] != [] or S[0.12]['n_ok'] != 6)
    n += 1; bad += int(S[0.10]['D'] is None or 'D и [L, U] только описательно' not in S[0.10]['notes'])
    n += 1; bad += int(any(S[a]['label'] == RS.LABEL_NONCONV for a in RS.ALPHAS if a not in (0.10, 0.12)))
    n += 1; bad += int(S[0.10]['nonconv_main'] != [[1, 2, 'metrics_S']])
    csvtxt = open(pre + '.csv', encoding='utf-8').read()
    n += 1; bad += int(',ok,' not in csvtxt or ',nonconv,metrics_S' not in csvtxt or ',nonconv,saturated_share' not in csvtxt)
    n += 1; bad += int(RS.verify(pre) != [])
    report("4. несходимость основной серии (строки со статусом в CSV, исключённые пары, ярлык, описательная D)", bad, n)

    # 5. несходимость пилота: δ_S не считается по сокращённой выборке
    bad = n = 0
    pre, rows, pil, S = run_fake(tmp, 'pilot_nc', FakeC({(0.20, 0, 3, 7777, 'metrics_S')}))
    s = S[0.20]
    n += 1; bad += int(s['delta_S'] is not None or s['label'] != RS.LABEL_NONCONV)
    n += 1; bad += int(s['pilot']['median_A2S'] is not None or s['pilot']['median_A2S_descriptive_if_incomplete'] is None)
    n += 1; bad += int(s['pilot']['nonconv_A2S'] != [[3, 'metrics_S']] or len(pil) != 8 * 5)
    n += 1; bad += int(S[0.30]['delta_S'] is None)
    n += 1; bad += int(s['nonconv_main_count'] != 0 or s['n_ok'] != 6)            # основная серия при этом α полная
    n += 1; bad += int(RS.verify(pre) != [])
    report("5. несходимость пилота (δ_S не определён, медиана только описательно, остальные α не затронуты)", bad, n)

    # 6. вырожденный порог: δ_S = 0 -> ни эквивалентности, ни значимого различия
    bad = n = 0
    pre, rows, pil, S = run_fake(tmp, 'degen', FakeC(zero_pilot=True))
    for al, s in S.items():
        n += 1; bad += int(s['delta_S'] != 0.0 or s['label'] != RS.LABEL_DEGEN or s['D'] is None)
    n += 1; bad += int(RS.verify(pre) != [])
    report("6. вырожденный порог (δ_S = 0: «порог вырожден: вердикт не выносится», D и [L, U] описательно)", bad, n)

    # 7. CLI: md5, защита итоговой серии, перезапись, порча вывода -> ненулевой код
    bad = n = 0
    py = [sys.executable]
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    run = lambda args, cwd=HERE: subprocess.run(py + args, cwd=cwd, capture_output=True, text=True, env=env).returncode
    work = os.path.join(tmp, 'app'); os.makedirs(work)
    for f in ('run_S_sweep.py', 'engine.py', 'contagion.py', 'PROTOCOL_v1.4_ext.md'):
        shutil.copy(os.path.join(HERE, f), work)
    with open(os.path.join(work, 'PROTOCOL_v1.4_ext.md'), 'a', encoding='utf-8') as f:
        f.write('\n')                                                             # подмена протокола
    n += 1; bad += int(run(['run_S_sweep.py', '--base', '7777', '--n', '2', '--pilot-n', '1', '--out', 'x'], work) != 2)
    shutil.copy(os.path.join(HERE, 'PROTOCOL_v1.4_ext.md'), work)
    with open(os.path.join(work, 'contagion.py'), 'a', encoding='utf-8') as f:
        f.write('# x\n')                                                          # подмена ядра
    n += 1; bad += int(run(['run_S_sweep.py', '--base', '7777', '--n', '2', '--pilot-n', '1', '--out', 'x'], work) != 2)
    n += 1; bad += int(run(['run_S_sweep.py', '--base', '2027', '--n', '2', '--pilot-n', '1', '--out', os.path.join(tmp, 'y')]) != 4)
    n += 1; bad += int(run(['run_S_sweep.py', '--final', '--n', '2']) != 4)
    n += 1; bad += int(run(['run_S_sweep.py', '--base', '7777', '--n', '2']) != 4)
    good = os.path.join(tmp, 'clean')
    n += 1; bad += int(run(['run_S_sweep.py', '--verify', good]) != 0)
    n += 1; bad += int(run(['run_S_sweep.py', '--base', '7777', '--n', '2', '--pilot-n', '1', '--out', good]) != 4)  # перезапись
    corrupt = [
        ('.csv', lambda t: t.replace('alpha,topo,rep', 'alpha;topo;rep', 1)),           # заголовок
        ('.csv', lambda t: '\n'.join(t.split('\n')[:-3]) + '\n'),                         # потеряны строки
        ('.csv', lambda t: t.replace(',ok,', ',OK,', 1)),                                 # статус
        ('.csv', lambda t: t.replace(t.split('\n')[1].split(',')[4], '0.5', 1)),          # значение A2S
        ('_pilot.csv', lambda t: t.replace(t.split('\n')[1].split(',')[4], '0.0', 1)),   # пилот
        ('.json', lambda t: t.replace('"delta_S"', '"delta"', 1)),                        # нет δ_S
        ('.json', lambda t: t.replace(RS.LABEL_EQUIV, 'эквивалентны', 1).replace(RS.LABEL_UNCLEAR, 'х', 1)),
        ('.json', lambda t: t[:len(t) // 2]),                                             # обрезанный JSON
    ]
    for k, (suf, fn) in enumerate(corrupt):
        dst = os.path.join(tmp, 'bad%d' % k)
        for s2 in ('.csv', '_pilot.csv', '.json'):
            shutil.copy(good + s2, dst + s2)
        txt = open(dst + suf, encoding='utf-8').read(); new = fn(txt)
        assert new != txt, k
        open(dst + suf, 'w', encoding='utf-8').write(new)
        n += 1; bad += int(run(['run_S_sweep.py', '--verify', dst]) != 3)
    report("7. CLI: подмена md5 протокола и ядра -> 2; seed 2027 без --final, --final с параметрами, неполные параметры, перезапись -> 4; 8 видов порчи вывода -> 3", bad, n)
    # 8. непересечение пилота (7777) и основной серии
    bad = n = 0
    from engine import gen_net
    tot, lines = RS.check_disjoint(gen_net, RS.FINAL_BASE, RS.FINAL_N)            # итоговая конфигурация
    n += 1; bad += int(tot != 0 or lines[-1] != 'итог: пересечений нет')
    tot, lines = RS.check_disjoint(gen_net, 7777, 10, 7777, 10)                    # пробная: должно найтись
    # ключи: капитал 10 + структура и веса topo 0 20 = 30; на каждое α E 10 (topo 0), Kb 20 (капитал общий для топологий)
    n += 1; bad += int(tot != 30 + 8 * (10 + 20) or 'общих 30' not in lines[0])
    tot, _ = RS.check_disjoint(gen_net, 7778, 10, 7777, 10)                        # соседний base
    n += 1; bad += int(tot != 0)
    # --final останавливается с кодом 5 при пересечении, до расчёта (run_series подменён и упал бы)
    saved = (RS.PILOT_BASE, RS.run_series)
    def _boom(*a, **k):
        raise AssertionError('расчёт не должен начаться')
    try:
        RS.PILOT_BASE = RS.FINAL_BASE; RS.run_series = _boom
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            code = RS.main(['--final', '--out', os.path.join(tmp, 'fin')])
        n += 1; bad += int(code != 5)
    except AssertionError:
        n += 1; bad += 1
    finally:
        RS.PILOT_BASE, RS.run_series = saved
    n += 1; bad += int(run(['run_S_sweep.py', '--check-disjoint']) != 0)
    report("8. непересечение пилота и основной серии (итоговая конфигурация: 0; 7777 против 7777: найдено; --final при пересечении -> 5 до расчёта)", bad, n)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("время: %.1f с" % (time.time() - t0))
raise SystemExit(1 if TOTAL_BAD else 0)
