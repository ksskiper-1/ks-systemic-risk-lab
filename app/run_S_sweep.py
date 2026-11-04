"""T3: серия по метрике S (A2S) по протоколу PROTOCOL_v1.4_ext.md, версия 1.1 (зафиксирован 25.10.2026).

Исследовательское дополнение, вердикт v1.3 не меняет. engine.py и contagion.py не изменяются.

Запуск:
  пробный (по умолчанию пишет в trial/):
    python run_S_sweep.py --base 7777 --n 10 --pilot-n 10 --out trial/run1
  итоговый (только по отдельному поручению автора):
    python run_S_sweep.py --final
  проверка уже записанного вывода:
    python run_S_sweep.py --verify trial/run1

  проверка, что пилот и основная серия не пересекаются (без расчёта S):
    python run_S_sweep.py --check-disjoint             (итоговая конфигурация: 2027 x 200 против 7777 x 100)

Коды выхода: 0 - успех; 2 - md5 не совпал; 3 - вывод не прошёл проверку формата;
             4 - запуск отклонён (защита итоговой серии, перезапись, неверные параметры);
             5 - реализации пилота и основной серии пересекаются (только итоговый режим и --check-disjoint).
"""
import argparse, csv, hashlib, json, math, os, platform, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECTED_MD5 = {                       # состояние, зафиксированное в T1/T2
    'PROTOCOL_v1.4_ext.md': '105e2193667b274479e2541160df8a42',
    'engine.py': '66b1fbd2b94f0acba8a6ea7ce4b7c4c0',
    'contagion.py': 'f9205f3423cb2e2b64fe24652d410da8',
}
PROTOCOL_VERSION = '1.1'

# ---- параметры протокола (раздел 3) ----
ALPHAS = (0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30, 0.50)
R = 0.4
MECH = 'none'
N_BANKS = 25
FINAL_BASE, FINAL_N = 2027, 200
PILOT_BASE, PILOT_N, PILOT_TOPO = 7777, 100, 0
B = 10_000
BOOT_SEED = 2027                       # default_rng([2027, round(1000*alpha)]), константа протокола
S_REF = 0.01
DELTA_FRAC = 0.10

LABEL_NONCONV = 'не интерпретируется: неполная сходимость'
LABEL_DEGEN = 'порог вырожден: вердикт не выносится'
LABEL_EQUIV = 'практически эквивалентны'
LABEL_DIFF = 'практически значимое различие'
LABEL_UNCLEAR = 'неопределённо'
LABELS = (LABEL_NONCONV, LABEL_DEGEN, LABEL_EQUIV, LABEL_DIFF, LABEL_UNCLEAR)

CSV_COLS = ['alpha', 'topo', 'rep', 'A1S', 'A2S', 'rho', 'sat_share', 'status', 'nonconv_part']
STATUSES = ('ok', 'nonconv')


def md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def check_md5():
    got = {k: md5(os.path.join(HERE, k)) for k in EXPECTED_MD5}
    bad = {k: (EXPECTED_MD5[k], got[k]) for k in got if got[k] != EXPECTED_MD5[k]}
    return got, bad


# ---- непересечение пилота и основной серии ----
def seed_keys(base, topos, n):
    """SeedSequence-ключи engine.rng, которыми gen_net порождает сети: структура (topo, rep, 0), веса (topo, rep, 1),
    капитал (9, rep, 2)."""
    keys = set()
    for rep in range(n):
        keys.add((base, 9, rep, 2))
        for t in topos:
            keys.add((base, t, rep, 0)); keys.add((base, t, rep, 1))
    return keys


def check_disjoint(gen_net, base, n, pilot_base=None, pilot_n=None):
    """Сравнивает пилот (pilot_base, topo 0, rep < pilot_n) с основной серией (base, topo 0 и 1, rep < n)
    по seed-ключам и по самим данным при каждом α: побайтно E, Kb и пара (E, Kb).
    Возвращает (число пересечений, строки отчёта)."""
    import hashlib as _h
    pilot_base = PILOT_BASE if pilot_base is None else pilot_base
    pilot_n = PILOT_N if pilot_n is None else pilot_n
    lines = []
    kp, km = seed_keys(pilot_base, (PILOT_TOPO,), pilot_n), seed_keys(base, (0, 1), n)
    shared = kp & km
    lines.append('seed-ключи: пилот %d, основная серия %d, общих %d' % (len(kp), len(km), len(shared)))
    total = len(shared)
    hE = lambda x: _h.sha256(np.ascontiguousarray(x).tobytes()).hexdigest()
    for alpha in ALPHAS:
        pE, pK, pEK = set(), set(), set()
        for rep in range(pilot_n):
            E, A, Kb = gen_net(PILOT_TOPO, rep, N=N_BANKS, alpha=alpha, base=pilot_base)
            pE.add(hE(E)); pK.add(hE(Kb)); pEK.add(hE(E) + hE(Kb))
        cE = cK = cEK = 0
        for t in (0, 1):
            for rep in range(n):
                E, A, Kb = gen_net(t, rep, N=N_BANKS, alpha=alpha, base=base)
                cE += hE(E) in pE; cK += hE(Kb) in pK; cEK += (hE(E) + hE(Kb)) in pEK
        total += cE + cK
        lines.append('α = %.2f: сетей пилота %d, основной серии %d; совпадений E %d, капитала Kb %d, пары (E, Kb) %d'
                     % (alpha, pilot_n, 2 * n, cE, cK, cEK))
    lines.append('итог: %s' % ('пересечений нет' if total == 0 else 'ПЕРЕСЕЧЕНИЙ %d' % total))
    return total, lines


# ---- расчёт по одной сети (раздел 6: отдельный try на каждый вызов) ----
def eval_net(C, gen_net, topo, rep, alpha, base):
    E, A, Kb = gen_net(topo, rep, N=N_BANKS, alpha=alpha, base=base)
    row = dict(alpha=alpha, topo=topo, rep=rep, A1S=math.nan, A2S=math.nan, rho=math.nan,
               sat_share=math.nan, status='ok', nonconv_part='')
    parts = []
    try:
        # metrics_S внутри вызывает saturated_share; его несходимость тоже обнуляет A1S/A2S (консервативно)
        m = C.metrics_S(E, A, Kb, MECH, R=R, s_ref=S_REF)
        row['A1S'], row['A2S'] = float(m['A1S']), float(m['A2S'])
    except RuntimeError:
        parts.append('metrics_S')
    row['rho'] = float(C.spectral_radius(E, Kb, R))        # K = Kb для механизма none
    try:
        row['sat_share'] = float(C.saturated_share(E, A, Kb, R, S_REF))
    except RuntimeError:
        parts.append('saturated_share')
    if parts:
        row['status'] = 'nonconv'; row['nonconv_part'] = '+'.join(parts)
    return row


# ---- статистика (разделы 4–5) ----
def boot_ci(d, seed_key):
    rng = np.random.default_rng(seed_key)
    n = len(d)
    idx = rng.integers(0, n, (B, n))
    Ds = d[idx].mean(1)
    lo, hi = np.percentile(Ds, [2.5, 97.5])
    return float(lo), float(hi)


def classify(any_nonconv, delta, L, U):
    """Раздел 5, правила 0–4 по порядку. delta = None означает, что δ_S не определён (несходимость пилота)."""
    if any_nonconv or delta is None:
        return LABEL_NONCONV
    if delta == 0.0:
        return LABEL_DEGEN
    if -delta < L <= U < delta:
        return LABEL_EQUIV
    if L > delta or U < -delta:
        return LABEL_DIFF
    return LABEL_UNCLEAR


def _f(x):
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else x


def _desc(v):
    v = np.asarray(v, float); v = v[~np.isnan(v)]
    return dict(n=int(len(v)), mean=_f(float(v.mean())) if len(v) else None,
                median=_f(float(np.median(v))) if len(v) else None)


def summarize(rows, pilot_rows, n):
    out = []
    for alpha in ALPHAS:
        key = int(round(1000 * alpha))
        main = {(r['topo'], r['rep']): r for r in rows if r['alpha'] == alpha}
        pil = [r for r in pilot_rows if r['alpha'] == alpha]
        nonconv_main = sorted([[r['topo'], r['rep'], r['nonconv_part']] for r in main.values() if r['status'] != 'ok'])
        pil_bad = sorted([[r['rep'], r['nonconv_part']] for r in pil if math.isnan(r['A2S'])])
        pil_nonconv_any = sorted([[r['rep'], r['nonconv_part']] for r in pil if r['status'] != 'ok'])
        a2 = np.array([r['A2S'] for r in pil], float)
        pilot_median_desc = float(np.median(a2[~np.isnan(a2)])) if (~np.isnan(a2)).any() else None
        if pil_bad:
            delta = None                       # раздел 6.4: по сокращённому пилоту δ_S не считается
        else:
            delta = DELTA_FRAC * float(np.median(a2))
        reps_ok = [rep for rep in range(n)
                   if not math.isnan(main[(0, rep)]['A2S']) and not math.isnan(main[(1, rep)]['A2S'])]
        excluded = [rep for rep in range(n) if rep not in reps_ok]
        d = np.array([main[(1, r)]['A2S'] - main[(0, r)]['A2S'] for r in reps_ok], float)
        if len(d):
            D = float(d.mean()); L, U = boot_ci(d, [BOOT_SEED, key])
        else:
            D = L = U = math.nan
        any_nc = bool(nonconv_main)
        label = classify(any_nc, delta, L, U) if len(d) else LABEL_NONCONV
        notes = []
        if len(d) and not (L <= 0 <= U) and label in (LABEL_EQUIV, LABEL_UNCLEAR):
            notes.append('различие статистически обнаружимо')
        if delta is not None and delta > 0 and len(d) and (U - L) >= 2 * delta:
            notes.append('w >= 2*δ_S: ярлык «практически эквивалентны» недостижим по построению')
        if label in (LABEL_NONCONV, LABEL_DEGEN):
            notes.append('D и [L, U] только описательно')
        # вспомогательные (раздел 4), в критерии не входят
        a1 = np.array([main[(1, r)]['A1S'] - main[(0, r)]['A1S'] for r in range(n)
                       if not math.isnan(main[(0, r)]['A1S']) and not math.isnan(main[(1, r)]['A1S'])], float)
        a1ci = boot_ci(a1, [BOOT_SEED, key, 1]) if len(a1) else (math.nan, math.nan)
        mean_a2_t0 = np.nanmean([main[(0, r)]['A2S'] for r in reps_ok]) if reps_ok else math.nan
        per_topo = {str(t): {k: _desc([main[(t, r)][k] for r in range(n)]) for k in ('A1S', 'A2S', 'rho', 'sat_share')}
                    for t in (0, 1)}
        out.append(dict(
            alpha=alpha, label=label, delta_S=_f(delta), D=_f(D), L=_f(L), U=_f(U),
            w=_f(U - L) if len(d) else None, notes=notes,
            n_pairs=n, n_ok=len(reps_ok), excluded_reps=excluded,
            nonconv_main=nonconv_main, nonconv_main_count=len(nonconv_main),
            pilot=dict(n=len(pil), median_A2S=_f(None if pil_bad else float(np.median(a2))),
                       median_A2S_descriptive_if_incomplete=_f(pilot_median_desc) if pil_bad else None,
                       nonconv_A2S=pil_bad, nonconv_any=pil_nonconv_any),
            aux=dict(r=_f(D / mean_a2_t0) if len(d) and mean_a2_t0 > 0 else None,
                     mean_abs_d=_f(float(np.abs(d).mean())) if len(d) else None,
                     A1S_diff=dict(mean=_f(float(a1.mean())) if len(a1) else None, L=_f(a1ci[0]), U=_f(a1ci[1])),
                     per_topo=per_topo)))
    return out


# ---- запись и проверка формата ----
def _cell(v):
    if isinstance(v, float):
        return 'nan' if math.isnan(v) else repr(v)
    return str(v)


def write_csv(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, lineterminator='\n'); w.writerow(CSV_COLS)
        for r in rows:
            w.writerow([_cell(r[c]) for c in CSV_COLS])


def read_csv(path):
    with open(path, encoding='utf-8', newline='') as f:
        rd = csv.reader(f); head = next(rd)
        if head != CSV_COLS:
            raise ValueError('заголовок CSV %s не совпадает: %s' % (path, head))
        rows = []
        for line in rd:
            if len(line) != len(CSV_COLS):
                raise ValueError('строка CSV неверной длины: %s' % line)
            r = dict(zip(CSV_COLS, line))
            rows.append(dict(alpha=float(r['alpha']), topo=int(r['topo']), rep=int(r['rep']),
                             A1S=float(r['A1S']), A2S=float(r['A2S']), rho=float(r['rho']),
                             sat_share=float(r['sat_share']), status=r['status'], nonconv_part=r['nonconv_part']))
    return rows


def verify(prefix):
    """Возвращает список ошибок (пустой - формат верен). Пересчитывает сводку из CSV и сравнивает с JSON побитно."""
    errs = []
    try:
        meta = json.load(open(prefix + '.json', encoding='utf-8'))
        rows = read_csv(prefix + '.csv'); pil = read_csv(prefix + '_pilot.csv')
    except Exception as e:                                   # noqa: BLE001
        return ['не удалось прочитать вывод: %r' % e]
    for k in ('protocol_version', 'params', 'md5', 'env', 'summary'):
        if k not in meta:
            errs.append('в JSON нет ключа %s' % k)
    if errs:
        return errs
    p = meta['params']; n, pn = p['n'], p['pilot_n']
    if tuple(p['alphas']) != ALPHAS:
        errs.append('сетка α в JSON не совпадает с протоколом')
    if len(rows) != len(ALPHAS) * 2 * n:
        errs.append('строк основной серии %d, ожидалось %d' % (len(rows), len(ALPHAS) * 2 * n))
    if len(pil) != len(ALPHAS) * pn:
        errs.append('строк пилота %d, ожидалось %d' % (len(pil), len(ALPHAS) * pn))
    keys = {(r['alpha'], r['topo'], r['rep']) for r in rows}
    if keys != {(a, t, r) for a in ALPHAS for t in (0, 1) for r in range(n)}:
        errs.append('набор (α, topo, rep) основной серии неполон или с повторами')
    for r in rows + pil:
        if r['status'] not in STATUSES:
            errs.append('неизвестный статус %r' % r['status']); break
        if (r['status'] == 'ok') != (r['nonconv_part'] == ''):
            errs.append('статус и nonconv_part не согласованы: %r' % r); break
        if r['status'] == 'ok' and any(math.isnan(r[k]) for k in ('A1S', 'A2S', 'rho', 'sat_share')):
            errs.append('NaN в строке со статусом ok: %r' % r); break
    for s in meta['summary']:
        if s.get('label') not in LABELS:
            errs.append('неизвестный ярлык %r' % s.get('label'))
        if 'delta_S' not in s:
            errs.append('нет delta_S рядом с ярлыком при α = %s' % s.get('alpha'))
    if errs:
        return errs
    again = summarize(rows, pil, n)
    if json.dumps(again, ensure_ascii=False, sort_keys=True) != json.dumps(meta['summary'], ensure_ascii=False, sort_keys=True):
        errs.append('сводка JSON не воспроизводится из CSV')
    return errs


def run_series(C, gen_net, base, n, pn, prefix, kind, md5s):
    """Считает основную серию и пилот, пишет CSV и JSON. C и gen_net передаются явно (для тестов с подменой)."""
    rows = [eval_net(C, gen_net, topo, rep, alpha, base) for alpha in ALPHAS for topo in (0, 1) for rep in range(n)]
    pilot = [eval_net(C, gen_net, PILOT_TOPO, rep, alpha, PILOT_BASE) for alpha in ALPHAS for rep in range(pn)]
    summary = summarize(rows, pilot, n)

    meta = dict(
        protocol='PROTOCOL_v1.4_ext.md', protocol_version=PROTOCOL_VERSION,
        status='исследовательское дополнение, вердикт v1.3 не меняет',
        run_kind=kind,
        params=dict(alphas=list(ALPHAS), R=R, mech=MECH, N=N_BANKS, base=base, n=n, pilot_base=PILOT_BASE,
                    pilot_n=pn, pilot_topo=PILOT_TOPO, B=B, boot_seed='default_rng([%d, round(1000*alpha)])' % BOOT_SEED,
                    aux_A1S_boot_seed='default_rng([%d, round(1000*alpha), 1])' % BOOT_SEED,
                    s_ref=S_REF, SAT_TOL=C.SAT_TOL, TOL=C.TOL, MAXIT=C.MAXIT, delta_frac=DELTA_FRAC,
                    ci='95% percentile bootstrap, парный по rep'),
        md5=dict(md5s, **{'run_S_sweep.py': md5(os.path.abspath(__file__))}),
        env=dict(python=platform.python_version(), numpy=np.__version__),
        summary=summary)
    write_csv(prefix + '.csv', rows); write_csv(prefix + '_pilot.csv', pilot)
    with open(prefix + '.json', 'w', encoding='utf-8') as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True); f.write('\n')

    return rows, pilot, summary


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--base', type=int, default=None, help='base seed основной серии (пробный запуск: 7777)')
    ap.add_argument('--n', type=int, default=None, help='число сетей на топологию')
    ap.add_argument('--pilot-n', type=int, default=None, help='число пилотных сетей (seed 7777, topo 0)')
    ap.add_argument('--out', default=None, help='префикс выходных файлов')
    ap.add_argument('--final', action='store_true', help='итоговая серия: seed 2027, n = 200, пилот 100')
    ap.add_argument('--verify', metavar='PREFIX', help='только проверить формат уже записанного вывода')
    ap.add_argument('--check-disjoint', action='store_true',
                    help='только проверить непересечение пилота и основной серии итоговой конфигурации')
    a = ap.parse_args(argv)

    if a.verify:
        errs = verify(a.verify)
        for e in errs:
            print('ОШИБКА ФОРМАТА:', e)
        print('проверка формата %s: %s' % (a.verify, 'ошибок нет' if not errs else '%d ошибок' % len(errs)))
        return 3 if errs else 0

    got, bad = check_md5()
    for k, (exp, g) in bad.items():
        print('md5 НЕ СОВПАЛ: %s ожидалось %s, получено %s' % (k, exp, g))
    if bad:
        print('расчёт остановлен (протокол v1.4-ext, раздел 2)'); return 2
    print('md5 совпали:', ', '.join('%s %s' % (k, v[:10]) for k, v in got.items()))

    if a.check_disjoint:
        sys.path.insert(0, HERE)
        from engine import gen_net
        total, lines = check_disjoint(gen_net, FINAL_BASE, FINAL_N)
        print('непересечение: основная серия base %d, n = %d (topo 0, 1) против пилота base %d, n = %d (topo %d)'
              % (FINAL_BASE, FINAL_N, PILOT_BASE, PILOT_N, PILOT_TOPO))
        print('\n'.join(lines))
        return 5 if total else 0

    if a.final:
        if any(v is not None for v in (a.base, a.n, a.pilot_n)):
            print('с --final параметры --base/--n/--pilot-n не задаются'); return 4
        base, n, pn = FINAL_BASE, FINAL_N, PILOT_N
        prefix = a.out or os.path.join(HERE, 'results', 'final_S_sweep_2027')
    else:
        if a.base is None or a.n is None or a.pilot_n is None or a.out is None:
            print('для пробного запуска нужны --base, --n, --pilot-n и --out'); return 4
        if a.base == FINAL_BASE:
            print('seed 2027 зарезервирован за итоговой серией; используйте --final по поручению автора'); return 4
        base, n, pn, prefix = a.base, a.n, a.pilot_n, a.out
        if n < 2 or pn < 1:
            print('нужно n >= 2 и pilot-n >= 1'); return 4
    for suf in ('.csv', '_pilot.csv', '.json'):
        if os.path.exists(prefix + suf):
            print('файл %s уже существует, перезапись запрещена' % (prefix + suf)); return 4
    os.makedirs(os.path.dirname(os.path.abspath(prefix)), exist_ok=True)

    sys.path.insert(0, HERE)
    import contagion as C
    from engine import gen_net
    total, lines = check_disjoint(gen_net, base, n, PILOT_BASE, pn)
    print('непересечение пилота и основной серии:', lines[-1][len('итог: '):])
    if total:
        if a.final:
            print('\n'.join(lines)); print('итоговый расчёт остановлен'); return 5
        print('  (пробный режим: пересечение допускается и не анализируется)')
    rows, pilot, summary = run_series(C, gen_net, base, n, pn, prefix, 'final' if a.final else 'trial', got)

    errs = verify(prefix)
    for e in errs:
        print('ОШИБКА ФОРМАТА:', e)
    nc = sum(r['status'] != 'ok' for r in rows); ncp = sum(r['status'] != 'ok' for r in pilot)
    print('записано: %s.csv (%d строк, nonconv %d), %s_pilot.csv (%d строк, nonconv %d), %s.json'
          % (prefix, len(rows), nc, prefix, len(pilot), ncp, prefix))
    for s in summary:
        print('α = %.2f  δ_S = %-10s D = %-11s [L, U] = [%s; %s]  n_ok = %d  ярлык: %s%s'
              % (s['alpha'], '%.3e' % s['delta_S'] if s['delta_S'] is not None else 'не опр.',
                 '%+.3e' % s['D'] if s['D'] is not None else 'nan',
                 '%.3e' % s['L'] if s['L'] is not None else 'nan', '%.3e' % s['U'] if s['U'] is not None else 'nan',
                 s['n_ok'], s['label'], ('  (' + '; '.join(s['notes']) + ')') if s['notes'] else ''))
    print('проверка формата: %s' % ('ошибок нет' if not errs else '%d ошибок' % len(errs)))
    return 3 if errs else 0


if __name__ == '__main__':
    sys.exit(main())
