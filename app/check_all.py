"""T4: единая проверка проекта. Ничего не пересчитывает в results/ и не запускает --final.

Запуск:
  python check_all.py                 полная проверка + искусственные поломки на временных копиях
  python check_all.py --no-selftest   без искусственных поломок (так check_all вызывается внутри копий)
  python check_all.py --steps md5,params   только выбранные шаги (для самопроверки)

Шаги (по порядку, остановка на первом нарушении):
  md5       - md5 защищённых файлов, включая все файлы results/ и итоговую серию 2027
  params    - метка версии и параметры: заголовок протокола, PROTOCOL_VERSION скрипта и JSON итоговой серии
              совпадают; md5 в JSON итоговой серии равны текущим файлам; константы скрипта, ядра и JSON
              равны значениям протокола (раздел 3)
  release   - метка релиза RELEASE.json (ставится при заморозке 1 ноября); если файла нет, шаг пропускается
  trace, contagion, protocol, sweep - check_trace.py, check_contagion.py, check_protocol.py, check_sweep.py
  verify    - python run_S_sweep.py --verify results/final_S_sweep_2027
  concept   - вывод check_protocol совпадает с концепцией: T = +0,0107, ДИ [0,0085; 0,0129], δ = 0,0051, 27 из 27
  ui        - check_ui.py (T5): app.py на заглушке Streamlit (оба режима: «Дефолты» и «Заражение (S)», s_trace
              против ядра contagion.py), JS графа в Node на заглушке DOM, ускоренный набор
              headless Chromium (scrollHeight <= FRAME_H, карточка ρ наверху, цвет спасённого банка, клик/наведение/
              стрелки); без Node или Chromium - код 2 (нарушение). Полный перебор высоты: python check_ui.py --full-height
  md5after  - md5 защищённых файлов после всех шагов (ничего не изменилось во время проверки)
  selftest  - искусственные поломки на временных копиях папки; каждая должна дать ненулевой код

Код выхода: 0 и «ВСЁ ПРОЙДЕНО» либо 1 и «НАРУШЕНИЕ: <шаг>: ...».
"""
import argparse, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))

# Зафиксированное состояние после итогового запуска T3 (26.10.2026)
# Журнал изменений списка защищённых файлов:
#   26.10.2026, T4: check_contagion.py 857239a13cf833320a6ee2e1b1491a1c -> 3c80bf6f12e9fdf4d5b51fb8df00be42.
#     Причина: самопроверка check_all показала, что блоки 1-9 не ловят поломки «s_ref по умолчанию 0,02»
#     и «SAT_TOL = 1e-3». По решению автора (вариант A) добавлен блок 10: значения протокола по умолчанию,
#     граница h = 1 / 1 - 1e-6, ручной пример s_ref 0,01 и 0,02. Блоки 1-9 не менялись; contagion.py,
#     engine.py, протокол и results/ не менялись.
#   27.10.2026, T5: список защищённых файлов НЕ менялся (21 файл). Добавлен шаг ui (check_ui.py, не защищён:
#     будет меняться в шаге 3) и три поломки самопроверки: статус спасённого банка на грани, кольцо спасённого
#     банка, s_ref карточки ρ = 0,02. Находка самопроверки: поломка s_ref не ловилась, так как при α = 0,3-0,6
#     насыщены 25 из 25 банков и при 0,01, и при 0,02. По решению автора (вариант A) в блок R check_ui.py
#     добавлены конфигурации α = 0,1 (без помощи R = 0,2 и 0,6; резервы R = 0,2); тест сравнивает карточку
#     с saturated_share(..., s_ref=S_REF) и требует хотя бы одну конфигурацию, где доля отличается от 0,02.
#   27.10.2026, T5 (вариант 2): список защищённых файлов НЕ менялся. В check_ui.py добавлены блоки H и C
#     (headless Chromium): scrollHeight <= app.FRAME_H = 1600 (максимум содержимого 1448 px по 100 сценариям
#     × ширины 900-1920, + ~10%), карточка ρ первой в правой панели, цвет обводки спасённого банка после
#     CSS-перехода, клик/наведение/стрелки. В самопроверку добавлена поломка «раздутая карточка ρ».
#   27.10.2026, T5 (навигация): список защищённых файлов НЕ менялся. В check_ui.py добавлены проверки кнопок
#     «← Назад» / «Вперёд →» (Node и Chromium), стрелок при фокусе в полях и ролях Streamlit, блок T (подпись,
#     «О модели», «Демонстрационные сценарии»); высота меряется с раскрытым «О модели». Две новые поломки самопроверки.
#     FRAME_H 1600 -> 1700: максимум содержимого 1546 px (раскрытый «О модели», ширина 900) + ~10%.
#   28.10.2026, T5 (шаг 3, режим «Заражение (S)»): список защищённых файлов НЕ менялся (21 файл; новый модуль
#     s_trace.py и check_ui.py не защищены до ручной приёмки обоих режимов). В check_ui.py добавлены блоки ST
#     (запись s_trace против contagion.propagate_batch / induced_S, независимый пересчёт шагов) и S (переключатель,
#     отключение помощи, панель, сценарии, JS по шагам, навигация), замеры S в Chromium. Девять новых поломок.
#   28.10.2026, финал T5 (оформление): с пользовательских экранов убраны «О модели», подпись о синтетической сети,
#     упоминания протоколов, версий, файлов и seed; в «Проверке гипотезы» «По протоколу» -> «Основной эксперимент».
#     Блок T check_ui.py переписан (сканирование всех экранов на технические подписи), новый блок G (раздел гипотезы в
#     Chromium) нашёл, что фрейм результатов 2100 px не вмещал содержимое (до 2593 px и до правок) -> 2860 px.
#     Три новые поломки. Список защищённых файлов не менялся (21).
PROTECTED = {
    'engine.py':                               '66b1fbd2b94f0acba8a6ea7ce4b7c4c0',
    'contagion.py':                            'f9205f3423cb2e2b64fe24652d410da8',
    'PROTOCOL_v1.4_ext.md':                    '105e2193667b274479e2541160df8a42',
    'run_S_sweep.py':                          '9c8bf3c25cb4182c7819194ad80ebef3',
    'precompute.py':                           'db195aedd0c80d32e31c427415153cf9',
    'precomputed.json':                        'c8c11b22e8a49db566e6924906fd66b1',
    'hypothesis.py':                           '2605f6b397d4a073ae80ce5162a7b504',
    'check_trace.py':                          '88c87cce09f60c2a2b9e9bda3dbe8ba1',
    'check_contagion.py':                      '3c80bf6f12e9fdf4d5b51fb8df00be42',   # блок 10, см. журнал
    'check_protocol.py':                       'a31fc5cf692175a7fa90435c738b39ac',
    'check_sweep.py':                          '6aa33014e34bbbe0cd17bcc72e82ae46',
    'results/common.py':                       '9f86dbba395d36166f235d2a841d4857',
    'results/exploration_alpha_sweep_S.py':    '1b11deb6cad3804aa670266d0bfe6dd3',
    'results/exploration_alpha_sweep_S.txt':   '7fefa451e555fea39897b96b4ee371fd',
    'results/exploration_once_debtrank.py':    '7c52c1178c7fb870d084c85c9a7d2f25',
    'results/exploration_once_debtrank.txt':   '0c68a1f345250be44d5b7ce24ee1bca9',
    'results/exploration_support_S.py':        '5340f4d54d5c20eb05fb5a7e0028e2f1',
    'results/exploration_support_S.txt':       '575d7529cd77516e3c9c90c5042d88be',
    'results/final_S_sweep_2027.csv':          'be71edae1f914fe8fd85a5e178bb970a',
    'results/final_S_sweep_2027_pilot.csv':    '053e0960f084a3151d3bdc407f29b3ee',
    'results/final_S_sweep_2027.json':         'a7096e2a4df11f2d1ea7b7c54c69116b',
}

# Значения протокола v1.4-ext 1.1, раздел 3 (переписаны из документа, не из кода)
PROTOCOL_VALUES = dict(version='1.1', alphas=[0.05, 0.08, 0.10, 0.12, 0.15, 0.20, 0.30, 0.50], R=0.4, mech='none',
                       N=25, base=2027, n=200, pilot_base=7777, pilot_n=100, pilot_topo=0, B=10000,
                       s_ref=0.01, SAT_TOL=1e-9, TOL=1e-12, MAXIT=200000, delta_frac=0.10)
CONCEPT = ['T = +0.0107  95% ДИ [0.0085; 0.0129]  δ = 0.0051', 'знак T в сетке: 27 из 27',
           'исход: гипотеза поддержана', 'сверка с концепцией: совпало']
FINAL = 'results/final_S_sweep_2027'
ALL_STEPS = ['md5', 'params', 'release', 'trace', 'contagion', 'protocol', 'sweep', 'verify', 'concept',
             'ui', 'md5after', 'selftest']


class Violation(Exception):
    pass


def md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def run_py(root, args, timeout=900):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    p = subprocess.run([sys.executable] + args, cwd=root, capture_output=True, text=True, env=env, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


# ---------- шаги ----------
def step_md5(root):
    bad = []
    for rel, exp in PROTECTED.items():
        path = os.path.join(root, rel)
        if not os.path.exists(path):
            bad.append('%s отсутствует' % rel); continue
        got = md5(path)
        if got != exp:
            bad.append('%s: ожидалось %s, получено %s' % (rel, exp, got))
    extra = sorted(set(os.listdir(os.path.join(root, 'results'))) - {r[8:] for r in PROTECTED if r.startswith('results/')}
                   - {'__pycache__'})
    if extra:
        bad.append('в results/ появились незарегистрированные файлы: %s' % ', '.join(extra))
    if bad:
        raise Violation('; '.join(bad))
    return 'защищённых файлов %d, все md5 совпали' % len(PROTECTED)


CONST_SNIPPET = r'''
import json, sys
sys.path.insert(0, '.')
import contagion as C, run_S_sweep as RS
print(json.dumps(dict(version=RS.PROTOCOL_VERSION, alphas=list(RS.ALPHAS), R=RS.R, mech=RS.MECH, N=RS.N_BANKS,
    base=RS.FINAL_BASE, n=RS.FINAL_N, pilot_base=RS.PILOT_BASE, pilot_n=RS.PILOT_N, pilot_topo=RS.PILOT_TOPO,
    B=RS.B, s_ref=RS.S_REF, SAT_TOL=C.SAT_TOL, TOL=C.TOL, MAXIT=C.MAXIT, delta_frac=RS.DELTA_FRAC,
    s_ref_default=C.saturated_share.__defaults__[-1], s_ref_metrics_default=C.metrics_S.__defaults__[-1],
    expected_md5=RS.EXPECTED_MD5)))
'''


def step_params(root):
    bad = []
    head = open(os.path.join(root, 'PROTOCOL_v1.4_ext.md'), encoding='utf-8').read(600)
    m = re.search(r'версия (\d+\.\d+)\)', head)
    doc_ver = m.group(1) if m else None
    if 'ЗАФИКСИРОВАНО' not in head:
        bad.append('в заголовке протокола нет статуса ЗАФИКСИРОВАНО')
    code, out = run_py(root, ['-c', CONST_SNIPPET])
    if code:
        raise Violation('не удалось прочитать константы: ' + out.strip()[-300:])
    k = json.loads(out.strip().splitlines()[-1])
    meta = json.load(open(os.path.join(root, FINAL + '.json'), encoding='utf-8'))
    pv = PROTOCOL_VALUES
    vers = {'протокол (заголовок)': doc_ver, 'run_S_sweep.PROTOCOL_VERSION': k['version'],
            'JSON итоговой серии': meta.get('protocol_version'), 'ожидаемая': pv['version']}
    if len(set(vers.values())) != 1:
        bad.append('метки версии расходятся: ' + ', '.join('%s %s' % kv for kv in vers.items()))
    if meta.get('run_kind') != 'final':
        bad.append('JSON итоговой серии: run_kind = %r' % meta.get('run_kind'))
    for key in ('alphas', 'R', 'mech', 'N', 'B', 's_ref', 'SAT_TOL', 'TOL', 'MAXIT', 'delta_frac',
                'pilot_base', 'pilot_n', 'pilot_topo'):
        if k[key] != pv[key]:
            bad.append('константа %s в коде = %r, по протоколу %r' % (key, k[key], pv[key]))
        if meta['params'].get(key) != pv[key]:
            bad.append('параметр %s в JSON = %r, по протоколу %r' % (key, meta['params'].get(key), pv[key]))
    for key in ('base', 'n'):
        if k[key] != pv[key] or meta['params'].get(key) != pv[key]:
            bad.append('%s: код %r, JSON %r, протокол %r' % (key, k[key], meta['params'].get(key), pv[key]))
    for key in ('s_ref_default', 's_ref_metrics_default'):
        if k[key] != pv['s_ref']:
            bad.append('значение s_ref по умолчанию в contagion (%s) = %r, по протоколу %r' % (key, k[key], pv['s_ref']))
    for f, h in meta['md5'].items():
        cur = md5(os.path.join(root, f))
        if cur != h:
            bad.append('JSON итоговой серии записан при %s = %s, сейчас %s' % (f, h, cur))
    for f, h in k['expected_md5'].items():
        if md5(os.path.join(root, f)) != h:
            bad.append('run_S_sweep.EXPECTED_MD5[%s] не совпадает с файлом' % f)
    if bad:
        raise Violation('; '.join(bad))
    return 'метка версии %s согласована (протокол, скрипт, JSON); параметры и md5 итоговой серии совпали' % doc_ver


def step_release(root):
    """RELEASE.json: {"tag": "...", "date": "YYYY-MM-DD", "md5": {файл: md5, ...}}; ставится при заморозке."""
    path = os.path.join(root, 'RELEASE.json')
    if not os.path.exists(path):
        return 'метка релиза ещё не поставлена (RELEASE.json нет; ожидается при заморозке 1 ноября), шаг пропущен'
    try:
        r = json.load(open(path, encoding='utf-8'))
    except Exception as e:                                    # noqa: BLE001
        raise Violation('RELEASE.json не читается: %r' % e)
    bad = []
    if not isinstance(r.get('tag'), str) or not re.fullmatch(r'v\d+\.\d+[\w.\-]*', r.get('tag', '')):
        bad.append('tag отсутствует или не вида v<число>.<число>...: %r' % r.get('tag'))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(r.get('date', ''))):
        bad.append('date не вида ГГГГ-ММ-ДД: %r' % r.get('date'))
    mm = r.get('md5') or {}
    missing = sorted(set(PROTECTED) - set(mm))
    if missing:
        bad.append('в метке нет md5 для: %s' % ', '.join(missing))
    for f, h in mm.items():
        p = os.path.join(root, f)
        if not os.path.exists(p) or md5(p) != h:
            bad.append('файл %s не совпадает с меткой релиза' % f)
    if bad:
        raise Violation('; '.join(bad))
    return 'метка релиза %s от %s: md5 %d файлов совпали' % (r['tag'], r['date'], len(mm))


def make_check(script):
    def f(root, ctx):
        code, out = run_py(root, [script])
        ctx[script] = out
        if code != 0:
            raise Violation('%s завершился с кодом %d; хвост вывода: %s' % (script, code, out.strip()[-400:]))
        return '%s: код 0' % script
    return f


def step_verify(root, ctx):
    code, out = run_py(root, ['run_S_sweep.py', '--verify', FINAL])
    if code != 0:
        raise Violation('--verify завершился с кодом %d: %s' % (code, out.strip()[-400:]))
    return out.strip().splitlines()[-1]


def step_concept(root, ctx):
    out = ctx.get('check_protocol.py')
    if out is None:
        _, out = run_py(root, ['check_protocol.py'])
    miss = [c for c in CONCEPT if c not in out]
    if miss:
        raise Violation('в выводе check_protocol нет строк: %s' % ' | '.join(miss))
    return 'T = +0,0107, ДИ [0,0085; 0,0129], δ = 0,0051, знак 27 из 27, «гипотеза поддержана»'


# ---------- искусственные поломки ----------
def _copy(root):
    dst = tempfile.mkdtemp(prefix='check_all_')
    app = os.path.join(dst, 'app')
    shutil.copytree(root, app, ignore=shutil.ignore_patterns('__pycache__'))
    return dst, app


def _patch(app, rel, old, new):
    p = os.path.join(app, rel); s = open(p, encoding='utf-8').read()
    if s.count(old) != 1:
        raise RuntimeError('поломка не применилась: %s / %r' % (rel, old))
    open(p, 'w', encoding='utf-8').write(s.replace(old, new))


MUTATIONS = [
    # (название, файл, было, стало, команда, которая должна дать ненулевой код)
    ('спектральный радиус без множителя (1-R)', 'contagion.py',
     'return float(np.abs(np.linalg.eigvals(M_matrix(E, K, R))).max())',
     'return float(np.abs(np.linalg.eigvals(np.asarray(E, float) / np.asarray(K, float)[:, None])).max())',
     ['check_contagion.py']),
    ('s_ref по умолчанию 0,02 вместо 0,01 (contagion.saturated_share)', 'contagion.py',
     'def saturated_share(E, A, K, R, s_ref=0.01):', 'def saturated_share(E, A, K, R, s_ref=0.02):',
     ['check_contagion.py']),
    ('s_ref итоговой серии 0,02 вместо 0,01 (run_S_sweep.S_REF)', 'run_S_sweep.py',
     'S_REF = 0.01', 'S_REF = 0.02', ['check_all.py', '--no-selftest', '--steps', 'params']),
    ('порог насыщения SAT_TOL = 1e-3 вместо 1e-9', 'contagion.py',
     'SAT_TOL = 1e-9 ', 'SAT_TOL = 1e-3 ', ['check_contagion.py']),
    ('метка версии скрипта 1.2 вместо 1.1', 'run_S_sweep.py',
     "PROTOCOL_VERSION = '1.1'", "PROTOCOL_VERSION = '1.2'", ['check_all.py', '--no-selftest', '--steps', 'params']),
    ('метка версии в заголовке протокола 1.2 вместо 1.1', 'PROTOCOL_v1.4_ext.md',
     '(версия 1.1).**', '(версия 1.2).**', ['check_all.py', '--no-selftest', '--steps', 'params']),
    ('md5 протокола: добавлена пустая строка', 'PROTOCOL_v1.4_ext.md', None, '\n',
     ['run_S_sweep.py', '--check-disjoint']),
    # T5: интерфейс
    ('спасённый банк на грани снова показан как «спасён поддержкой» (viz.py, статус)', 'viz.py',
     '(saved.has(i)?(D.ratios[t][i]>=1?"savedrisk":"saved"):"ok"));', '(saved.has(i)?"saved":"ok"));', ['check_ui.py']),
    ('кольцо спасённого банка гаснет независимо от ratio (viz.py)', 'viz.py',
     '(saved.has(i)&&r<1)', 'saved.has(i)', ['check_ui.py']),
    ('карточка ρ: s_ref 0,02 вместо S_REF протокола (app.py)', 'app.py',
     'sat = saturated_share(E, A, K, R, S_REF)', 'sat = saturated_share(E, A, K, R, 0.02)', ['check_ui.py']),
    ('раздутая карточка ρ: min-height 600px (viz.py)', 'viz.py',
     '.rg{padding:14px 20px}', '.rg{padding:14px 20px;min-height:600px}', ['check_ui.py']),
    ('«Вперёд →» не блокируется на последнем шаге (viz.py)', 'viz.py',
     'nextB.disabled=t>=T-1', 'nextB.disabled=false', ['check_ui.py']),
    ('стрелки листают каскад при фокусе на ползунке Streamlit (viz.py)', 'viz.py',
     '[role="slider"],', '', ['check_ui.py']),
    # T5, шаг 3: режим «Заражение (S)»
    ('s_trace: остановка при max|Δh| < 1e-4 вместо TOL ядра (s_trace.py)', 's_trace.py',
     'if np.abs(Hn - Ha).max(1)[0] < C.TOL:', 'if np.abs(Hn - Ha).max(1)[0] < 1e-4:', ['check_ui.py']),
    ('s_trace: шаг 0 начинается с h = 0, а не с прямого шока (s_trace.py)', 's_trace.py',
     'H = np.minimum(1.0, L0b / K)                       # как в', 'H = np.zeros_like(L0b)                       # как в', ['check_ui.py']),
    ('s_trace: последний шаг не равновесие ядра (хвост итераций потерян, s_trace.py)', 's_trace.py',
     '        show.append(n_iter)\n', '        pass\n', ['check_ui.py']),
    ('режим S не отключает помощь (app.py)', 'app.py',
     'mech = "none" if VS else mech_ui', 'mech = mech_ui', ['check_ui.py']),
    ('режим S: бюджет поддержки не заблокирован (app.py)', 'app.py',
     'key="proto", disabled=VS)', 'key="proto")', ['check_ui.py']),
    ('сценарий из режима S не переключает на «Дефолты» (app.py)', 'app.py',
     'st.session_state["view"] = "def"; st.session_state["_last_view"] = "def"', 'pass', ['check_ui.py']),
    ('подсказка S показывает h шага шока вместо выбранного шага (viz.py)', 'viz.py',
     'h=D.h[cur][i],sat=h>=1-D.sat_tol', 'h=D.h[0][i],sat=h>=1-D.sat_tol', ['check_ui.py']),
    ('панель S показывает итоговую S_ind вместо текущего шага (viz.py)', 'viz.py',
     'sn.textContent=fm(D.S[t]*100,2)', 'sn.textContent=fm(D.S[T-1]*100,2)', ['check_ui.py']),
    ('S: «Вперёд →» не блокируется на равновесии (viz.py)', 'viz.py',
     'nextB.disabled=(t>=T-1)', 'nextB.disabled=false', ['check_ui.py']),
    # финал T5: технические подписи на экране и раздел «Проверка гипотезы»
    ('на экран вернулась подпись с протоколом и seed (app.py)', 'app.py',
     "Серая линия — без помощи.</div></div>')", "Серая линия — без помощи.</div></div>'\n         f'<div class=\"note\">Протокол v1.3, seed {BASE_SEED}.</div>')", ['check_ui.py']),
    ('переключатель гипотезы снова «По протоколу» (hyp_page.py)', 'hyp_page.py',
     '"proto": "Основной эксперимент"', '"proto": "По протоколу"', ['check_ui.py']),
    ('фрейм результатов гипотезы снова 2100 px (hyp_page.py)', 'hyp_page.py',
     'H.precomputed(), theme), 2860)', 'H.precomputed(), theme), 2100)', ['check_ui.py']),
]


def step_selftest(root, ctx):
    lines = []; failed = []
    for name, rel, old, new, cmd in MUTATIONS:
        dst, app = _copy(root)
        try:
            if old is None:
                with open(os.path.join(app, rel), 'a', encoding='utf-8') as f:
                    f.write(new)
            else:
                _patch(app, rel, old, new)
            code, out = run_py(app, cmd)
            whole, wout = run_py(app, ['check_all.py', '--no-selftest'])
            ok = code != 0 and whole != 0
            lines.append('  [%s] %s: %s -> код %d; check_all.py --no-selftest -> код %d'
                         % ('пойман' if ok else 'НЕ ПОЙМАН', name, ' '.join(cmd), code, whole))
            if not ok:
                failed.append(name)
        finally:
            shutil.rmtree(dst, ignore_errors=True)
    # подмена каждого защищённого файла
    nf = 0
    for rel in PROTECTED:
        dst, app = _copy(root)
        try:
            with open(os.path.join(app, rel), 'ab') as f:
                f.write(b'\n')
            code, out = run_py(app, ['check_all.py', '--no-selftest'])
            if code != 1 or 'НАРУШЕНИЕ: md5' not in out:
                failed.append('подмена %s' % rel)
                lines.append('  [НЕ ПОЙМАН] подмена %s -> код %d' % (rel, code))
            else:
                nf += 1
        finally:
            shutil.rmtree(dst, ignore_errors=True)
    lines.append('  подмена защищённого файла (добавлен байт): поймано %d из %d, каждый раз «НАРУШЕНИЕ: md5», код 1'
                 % (nf, len(PROTECTED)))
    # незарегистрированный файл в results/
    dst, app = _copy(root)
    try:
        open(os.path.join(app, 'results', 'final_S_sweep_2027_v2.csv'), 'w').write('x\n')
        code, _ = run_py(app, ['check_all.py', '--no-selftest'])
        lines.append('  [%s] лишний файл в results/ -> код %d' % ('пойман' if code == 1 else 'НЕ ПОЙМАН', code))
        if code != 1:
            failed.append('лишний файл в results/')
    finally:
        shutil.rmtree(dst, ignore_errors=True)
    # метка релиза: верная проходит, неверная ловится
    dst, app = _copy(root)
    try:
        rel = dict(tag='v1.4-test', date='2026-11-01', md5={f: md5(os.path.join(app, f)) for f in PROTECTED})
        json.dump(rel, open(os.path.join(app, 'RELEASE.json'), 'w'))
        c1, _ = run_py(app, ['check_all.py', '--no-selftest', '--steps', 'release'])
        rel['md5']['engine.py'] = '0' * 32
        json.dump(rel, open(os.path.join(app, 'RELEASE.json'), 'w'))
        c2, _ = run_py(app, ['check_all.py', '--no-selftest', '--steps', 'release'])
        ok = c1 == 0 and c2 == 1
        lines.append('  [%s] метка релиза: верная RELEASE.json -> код %d, с чужим md5 -> код %d'
                     % ('пойман' if ok else 'НЕ ПОЙМАН', c1, c2))
        if not ok:
            failed.append('метка релиза')
    finally:
        shutil.rmtree(dst, ignore_errors=True)
    print('\n'.join(lines))
    if failed:
        raise Violation('не пойманы поломки: %s' % '; '.join(failed))
    return 'все искусственные поломки дали ненулевой код'


STEPS = {
    'md5': lambda r, c: step_md5(r), 'params': lambda r, c: step_params(r), 'release': lambda r, c: step_release(r),
    'trace': make_check('check_trace.py'), 'contagion': make_check('check_contagion.py'),
    'protocol': make_check('check_protocol.py'), 'sweep': make_check('check_sweep.py'),
    'verify': step_verify, 'concept': step_concept, 'ui': make_check('check_ui.py'), 'md5after': lambda r, c: step_md5(r), 'selftest': step_selftest,
}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--no-selftest', action='store_true')
    ap.add_argument('--steps', default=None, help='через запятую: ' + ','.join(ALL_STEPS))
    a = ap.parse_args(argv)
    steps = a.steps.split(',') if a.steps else [s for s in ALL_STEPS if not (a.no_selftest and s == 'selftest')]
    unknown = [s for s in steps if s not in STEPS]
    if unknown:
        print('НАРУШЕНИЕ: аргументы: неизвестные шаги %s' % unknown); return 1
    t0 = time.time(); ctx = {}
    for s in steps:
        ts = time.time()
        try:
            msg = STEPS[s](HERE, ctx)
        except Violation as e:
            print('НАРУШЕНИЕ: %s: %s' % (s, e)); print('время: %.1f с' % (time.time() - t0)); return 1
        except Exception as e:                                # noqa: BLE001
            print('НАРУШЕНИЕ: %s: ошибка выполнения шага: %r' % (s, e)); print('время: %.1f с' % (time.time() - t0))
            return 1
        print('[ok] %-9s %s (%.1f с)' % (s, msg, time.time() - ts))
    print('ВСЁ ПРОЙДЕНО (%d шагов, %.1f с)' % (len(steps), time.time() - t0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
