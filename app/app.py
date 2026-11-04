"""KS Systemic Risk Lab — интерактивная демонстрация (Streamlit). Движок: engine.py (без изменений)."""
import numpy as np
import streamlit as st
from engine import gen_net, metrics, mech_setup, order_by_liab, SGRID, SMAX
from cascade_trace import trace
import hashlib
from hyp_page import hypothesis_page
from viz import graph_html, curve_svg, ru_plural, regime_card, FONT, PALETTES
from contagion import spectral_radius, saturated_share, metrics_S
from s_trace import s_trace, s_curve      # пошаговая запись непрерывного заражения (режим S), ядро не меняется
from run_S_sweep import S_REF          # опорный шок протокола v1.4-ext (0,01)

BASE_SEED = 2026
N = 25
FRAME_H = 1700   # высота фрейма, px: максимум высоты содержимого 1546 (100 сценариев × ширины 900-1920, Chromium,
                 # «О модели» раскрыт) + ~10%; до навигации и «О модели» было 1600 (максимум 1448);
                 # проверяется check_ui.py (scrollHeight <= FRAME_H); полный перебор: python check_ui.py --full-height
MECHS = {"none": "Без помощи", "res": "Резервы", "sup": "Поддержка"}

st.set_page_config(page_title="KS Systemic Risk Lab", page_icon="◉", layout="wide")


def current_theme():
    """Тема берётся из Streamlit (меню ⋮ → Settings → Theme, по умолчанию как в системе)."""
    try:
        t = str(st.context.theme.type)
        return t if t in PALETTES else "light"
    except Exception:
        return "light"


THEME = current_theme()
P = PALETTES[THEME]

st.markdown(f"""
<style>
html, body, .stApp {{ font-family: {FONT} !important; -webkit-font-smoothing: antialiased; }}
.stApp :is(p, label, button, input, li, h1, h2, h3, [data-testid="stMarkdownContainer"]) {{ font-family: {FONT} !important; }}
.block-container {{ max-width: 1240px; padding: 2.6rem 2rem 4rem; }}
header[data-testid="stHeader"] {{ background: transparent; }}
#MainMenu, footer, [data-testid="stDecoration"], .stAppDeployButton {{ display: none !important; }}
.stApp label p, .stApp [data-testid="stWidgetLabel"] p {{ font-size: 16px; color: {P['mute']}; font-weight: 500; }}
.hero h1 {{ font-size: 44px; line-height: 1.08; font-weight: 700; letter-spacing: -0.03em; margin: 0 0 8px; color: {P['ink']}; }}
.hero p {{ font-size: 21px; line-height: 1.4; color: {P['mute']}; margin: 0 0 28px; max-width: 700px; }}
.sec-title {{ font-size: 24px; font-weight: 700; letter-spacing: -0.02em; margin: 6px 0 14px; color: {P['ink']}; }}
.card {{ background: {P['card']}; border-radius: 20px; padding: 22px 24px; margin-bottom: 14px; box-shadow: 0 0 0 1px {P['ring']}; }}
.row {{ display: flex; gap: 28px; flex-wrap: wrap; }}
.stat .num {{ font-size: 56px; line-height: 1; font-weight: 700; letter-spacing: -0.035em; font-variant-numeric: tabular-nums; color: {P['ink']}; }}
.stat .num.red {{ color: {P['red']}; }} .stat .num.green {{ color: {P['green']}; }} .stat .num.blue {{ color: {P['blue']}; }}
.stat .lbl {{ font-size: 16px; color: {P['mute']}; margin-top: 8px; line-height: 1.3; }}
.note {{ font-size: 15px; color: {P['mute']}; line-height: 1.45; margin-top: 12px; }}
.good {{ color: {P['green']}; font-weight: 600; }} .bad {{ color: {P['bad']}; font-weight: 600; }}
.sec-label {{ font-size: 15px; font-weight: 600; color: {P['mute']}; margin: 4px 0 8px; }}
.stApp .stButton > button {{ border-radius: 980px; border: 1px solid {P['ring']}; background: {P['card']}; color: {P['ink']};
  font-size: 16px; font-weight: 600; padding: .5rem 1rem; min-height: 2.9rem; transition: border-color .2s, color .2s, transform .1s; }}
.stApp .stButton > button:hover {{ border-color: {P['blue']}; color: {P['blue']}; }}
.stApp .stButton > button:active {{ transform: scale(.98); }}
.foot {{ font-size: 14px; color: {P['foot']}; margin-top: 26px; line-height: 1.5; }}
.st-key-pickers {{ position: absolute; left: -10000px; top: 0; width: 1px; height: 1px; overflow: hidden; visibility: hidden; }}
[data-testid="stSegmentedControl"] button {{ font-size: 16px; }}
</style>
<div class="hero"><h1>KS Systemic Risk Lab</h1>
<p>Как стресс одного банка передаётся по сети и что меняет поддержка. Выберите сеть, шок и механизм помощи.</p></div>
""", unsafe_allow_html=True)


def embed(html, height):
    # st.iframe — новый API (components.html устарел); запасной вариант для старых версий Streamlit
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=height, scrolling=False)


def seg(label, options, default, key, disabled=False):
    """Сегментный переключатель, у которого нельзя снять выбор повторным кликом."""
    last = f"_last_{key}"
    if key not in st.session_state:
        st.session_state[key] = default
        st.session_state[last] = default

    def keep():
        if st.session_state.get(key) is None:          # клик по уже выбранному пункту снимает выбор -> возвращаем прежний
            st.session_state[key] = st.session_state[last]
        st.session_state[last] = st.session_state[key]

    st.segmented_control(label, list(options), format_func=lambda k: options[k], key=key, on_change=keep, disabled=disabled)
    v = st.session_state.get(key)
    return v if v is not None else st.session_state[last]


section = seg("Раздел", {"sim": "Сеть и каскад", "hyp": "Проверка гипотезы"}, "sim", "section")
if section == "hyp":
    hypothesis_page(THEME, embed, seg)
    st.stop()

def pick_bank(i):
    """Клик по банку на графе: шок по одному банку (кнопки скрыты, их нажимает JS из фрейма)."""
    st.session_state["shock"] = "one"; st.session_state["_last_shock"] = "one"; st.session_state["bank"] = i


with st.container(key="pickers"):
    for _i in range(N):
        st.button(f"Шок по банку {_i}", key=f"pick_{_i}", on_click=pick_bank, args=(_i,))

SCEN = {
    "all":    dict(label="Один банк обрушивает всё",   topo=0, mech="none", shock="one", s=10.0, bank=0, net=1),
    "chain":  dict(label="Поддержка рвёт цепочку",     topo=0, mech="sup",  shock="one", s=10.0, bank=0, net=1),
    "common": dict(label="Общий шок: помощь бессильна", topo=1, mech="sup",  shock="all", s=6.0,  bank=0, net=1),
    "cliff":  dict(label="Резервы: обрыв на 6,5%",      topo=0, mech="res",  shock="all", s=6.5,  bank=0, net=1),
}


def apply_story(name):
    sc = SCEN[name]
    for k in ("topo", "mech", "shock"):
        st.session_state[k] = sc[k]; st.session_state[f"_last_{k}"] = sc[k]
    st.session_state[f"s_{sc['shock']}"] = sc["s"]
    st.session_state["bank"] = sc["bank"]; st.session_state["net_id"] = sc["net"]
    st.session_state["alpha"] = 0.5; st.session_state["R"] = 0.4; st.session_state["proto"] = True
    st.session_state["story"] = name
    st.session_state["view"] = "def"; st.session_state["_last_view"] = "def"   # сценарии рассчитаны на режим дефолтов


view = seg("Режим", {"def": "Дефолты", "S": "Заражение (S)"}, "def", "view")
VS = view == "S"
if VS:
    st.caption("Заражение (S): потери капитала распространяются непрерывно, без порога дефолта. "
               "Шаг — одна итерация пересчёта потерь.")
st.markdown('<div class="sec-label">Демонстрационные сценарии</div>', unsafe_allow_html=True)
if VS:
    st.caption("Сценарии рассчитаны на режим «Дефолты»: выбор сценария переключит режим на «Дефолты».")
for col, (name, sc) in zip(st.columns(len(SCEN), gap="small"), SCEN.items()):
    col.button(sc["label"], key=f"story_{name}", on_click=apply_story, args=(name,), use_container_width=True)
st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)


c1, c2, c3 = st.columns(3, gap="large")
with c1: topo = seg("Сеть", {0: "Распределённая", 1: "Концентрированная"}, 0, "topo")
with c2:
    mech_ui = seg("Помощь банкам", MECHS, "none", "mech", disabled=VS)   # выбор сохраняется в state и вернётся в «Дефолтах»
    if VS: st.caption("В режиме S помощь отключена: заражение считается без резервов и поддержки.")
mech = "none" if VS else mech_ui
with c3: shock_kind = seg("Шок", {"one": "Один банк", "all": "Общий"}, "one", "shock")

c4, c5, c6 = st.columns(3, gap="large")
skey = f"s_{shock_kind}"
if skey not in st.session_state: st.session_state[skey] = 10.0 if shock_kind == "one" else 6.0
with c4: s = st.slider("Размер шока, % от активов", 0.0, 15.0, step=0.5, format="%.1f%%", key=skey) / 100
with c5:
    bank = None
    if shock_kind == "one":
        core = (lambda i: " · ядро" if (topo == 1 and i < 5) else "")
        if "bank" not in st.session_state: st.session_state["bank"] = 0
        bank = st.selectbox("Банк, по которому бьёт шок", list(range(N)), format_func=lambda i: f"Банк {i}{core(i)}", key="bank")
with c6:
    if "net_id" not in st.session_state: st.session_state["net_id"] = 1
    net_id = st.number_input("Номер сети", min_value=0, max_value=999, step=1, key="net_id")

with st.expander("Параметры модели"):
    e1, e2, e3 = st.columns(3, gap="large")
    for _k, _v in (("alpha", 0.5), ("R", 0.4), ("proto", True), ("Gabs", 25.0)):
        if _k not in st.session_state: st.session_state[_k] = _v
    alpha = round(e1.slider("Доля межбанковских активов α", 0.1, 0.6, step=0.1, key="alpha"), 1)
    R = e2.slider("Возврат по требованию R", 0.2, 0.6, step=0.2, key="R")
    with e3:
        proto = st.checkbox("Стандартный бюджет поддержки (3% капитала)", key="proto", disabled=VS)
        Gabs = None if proto else st.slider("Бюджет поддержки, ед.", 5.0, 100.0, step=5.0, key="Gabs", disabled=VS)
        if VS: st.caption("В режиме S не используется.")


@st.cache_data(show_spinner=False)
def build(topo, net_id, alpha):
    return gen_net(topo, net_id, N=N, alpha=alpha, base=BASE_SEED)

@st.cache_data(show_spinner=False)
def calc(topo, net_id, alpha, R, mech, Gabs):
    E, A, Kb = build(topo, net_id, alpha)
    r = metrics(E, A, Kb, mech, R=R, Gabs=Gabs)
    K, G, sup = mech_setup(mech, Kb, A, None, Gabs)
    w = A / A.sum(); k = K / A
    single_curve = ((SGRID[:, None] >= k[None, :] - 1e-12) * (w * r["c1"])[None, :]).sum(1)
    return dict(A1=r["A1"], A2=r["A2"], Cg=r["Cg"], single=single_curve, k=k)

@st.cache_data(show_spinner=False)
def regime(topo, net_id, alpha, R, mech):
    """rho и доля насыщенных банков текущей сети: функции contagion.py, s_ref протокола, без помощи."""
    E, A, Kb = build(topo, net_id, alpha)
    K, _, _ = mech_setup(mech, Kb, A, None, None)
    rho = spectral_radius(E, K, R)
    try:
        sat = saturated_share(E, A, K, R, S_REF)
    except RuntimeError:            # несходимость вблизи rho = 1: показываем как есть, не подменяем
        sat = None
    return rho, sat

E, A, Kb = build(topo, net_id, alpha)
K, G, sup = mech_setup(mech, Kb, A, None, Gabs)
order = order_by_liab(E); k_now = K / A
if shock_kind == "one":
    L0 = np.zeros(N); L0[bank] = s * A[bank]
else:
    L0 = s * A


@st.cache_data(show_spinner=False)
def s_calc(topo, net_id, alpha, R):
    """Метрики S всего диапазона шоков (ядро contagion.metrics_S, без помощи) и кривые S_ind(s)."""
    E, A, Kb = build(topo, net_id, alpha)
    m = metrics_S(E, A, Kb, "none", R)
    return dict(A1S=m["A1S"], A2S=m["A2S"], Sg=m["Sg"], single=s_curve(E, Kb, A, R, True))


if VS:
    fmt = lambda x: f"{x:.3f}".replace(".", ",")
    pc = lambda x, d=2: f"{x * 100:.{d}f}".replace(".", ",") + "%"
    try:
        rec = s_trace(E, Kb, A, R, L0)
    except RuntimeError as e:
        st.warning(f"Непрерывное заражение для этих параметров не рассчитано: {e}. Шаги S не показываются.")
        st.stop()
    sm = s_calc(topo, net_id, alpha, R)
    who = "по каждому банку по очереди" if shock_kind == "one" else "по всем банкам сразу"
    a_s = sm["A1S"] if shock_kind == "one" else sm["A2S"]
    svg = curve_svg(SGRID, sm["single"] if shock_kind == "one" else sm["Sg"], None, s, "", THEME)
    n_it = rec["n_iter"]
    stats = (f'<div class="stat"><div class="num red" id="sNow">{pc(rec["S"][0])}</div>'
             f'<div class="lbl">S_ind на выбранном шаге:<br>потери капитала из-за заражения, % суммарных активов</div></div>'
             f'<div class="stat"><div class="num" id="satNow">{rec["sat"][0]} из {N}</div>'
             f'<div class="lbl">банков с h ≈ 1<br>(весь капитал потерян)</div></div>')
    extra = (f'<div class="note">Шаг: <b id="stepNow">шок, до заражения</b>.</div>'
             f'<div class="note">Итог (равновесие, {n_it} {ru_plural(n_it, "итерация", "итерации", "итераций")}): '
             f'S_ind = {pc(rec["S"][-1])} активов. Прямые потери от шока {pc(rec["S_dir"])} активов в S_ind не входят.</div>'
             '<div class="note">Помощь в режиме S отключена: расчёт без резервов и поддержки.</div>')
    right = (regime_card(*regime(topo, net_id, alpha, R, "none"), N, S_REF, False)
             + f'<div class="sec-title">Этот шок · непрерывное заражение</div><div class="card"><div class="row">{stats}</div>{extra}</div>'
             f'<div class="sec-title" style="margin-top:22px">Весь диапазон шоков</div>'
             f'<div class="card"><div class="stat"><div class="num blue">{fmt(a_s)}</div>'
             f'<div class="lbl">интегральная мера {"A1S" if shock_kind == "one" else "A2S"}: S_ind, проинтегрированная по шокам 0–15%, удар {who}</div></div>'
             f'<div style="margin-top:18px">{svg}</div>'
             f'<div class="note">Итоговая S_ind (доля суммарных активов) при шоке s, без помощи.</div></div>')
    page = graph_html(topo, E, A, None, bank, N, THEME, right=right, K=Kb, s_rec=rec, s=s)
    sig = hashlib.md5(f"S|{topo}|{shock_kind}|{bank}|{s:.4f}|{net_id}|{alpha}|{R}|{THEME}".encode()).hexdigest()[:12]
    with st.container(key=f"viz_{sig}"):
        embed(page, FRAME_H)
    st.stop()

tr = trace(E, K, R, L0, G, order, sup)

# ---------- вся изменяемая часть (граф + карточки) живёт в ОДНОМ изолированном фрейме ----------
# Так React основной страницы Streamlit не перерисовывает мой HTML при каждой смене параметров,
# а переводчик браузера/расширения не ломают его (ошибка removeChild).
fmt = lambda x: f"{x:.3f}".replace(".", ",")
num = lambda x: str(round(x, 1)).replace(".", ",")

D = set(sum(tr["steps"], [])); saved = [j for j in sorted(set(sum(tr["rescued"], []))) if j not in D]
direct, sec = len(tr["steps"][0]), tr["secondary"]; rest = N - direct
sec_lbl = (f"вторичных дефолтов<br>из {rest} {ru_plural(rest, 'оставшегося банка', 'оставшихся банков', 'оставшихся банков')}" if rest else "вторичных нет:<br>все упали сразу")
stats = (f'<div class="stat"><div class="num red">{sec}</div><div class="lbl">{sec_lbl}</div></div>'
         f'<div class="stat"><div class="num">{direct}</div><div class="lbl">упало<br>от шока</div></div>')
extra = ""
if mech == "sup":
    stats += f'<div class="stat"><div class="num green">{len(saved)}</div><div class="lbl">банков<br>спасено</div></div>'
    extra += f'<div class="note">Бюджет поддержки {num(G)} ед., осталось {num(tr["budget_left"])}. Первыми спасаются банки с наибольшими обязательствами перед другими.</div>'
if mech == "res":
    extra += '<div class="note">Резервы добавляют каждому банку 2% активов к капиталу заранее, до шока.</div>'
if shock_kind == "one":
    extra += f'<div class="note">Банк {bank} падает от шока, если s ≥ {k_now[bank]*100:.1f}% (его капитал в долях активов).</div>'

if direct == 0:
    kmin = k_now.min() * 100
    extra += (f'<div class="note"><span class="bad">Ни один банк не упал.</span> Самому уязвимому нужен шок от {num(kmin)}%.</div>' if shock_kind == "all"
              else f'<div class="note"><span class="bad">Банк {bank} выдержал шок.</span> Ему нужен шок от {num(k_now[bank]*100)}%.</div>')


def alt_trace(mech_, s_):
    """Тот же шок и сеть, но другой механизм или размер: для сравнений в рассказе."""
    K_, G_, sup_ = mech_setup(mech_, Kb, A, None, Gabs)
    L = (np.eye(N)[bank] * s_ * A[bank]) if shock_kind == "one" else s_ * A
    return trace(E, K_, R, L, G_, order, sup_)


story_html = ""
_sc = SCEN.get(st.session_state.get("story"))
if (_sc and topo == _sc["topo"] and mech == _sc["mech"] and shock_kind == _sc["shock"] and abs(s * 100 - _sc["s"]) < 1e-6
        and net_id == _sc["net"] and (shock_kind == "all" or bank == _sc["bank"]) and alpha == 0.5 and R == 0.4 and proto):
    name = st.session_state["story"]; waves = len(tr["steps"]) - 1
    resc_all = len(set(sum(tr["rescued"], []))); spent = G - tr["budget_left"]
    wv = lambda n: f"{n} {ru_plural(n, 'волну', 'волны', 'волн')}"
    base_sec = alt_trace("none", s)["secondary"]
    if name == "all":
        title = "Один банк обрушивает всё"
        _all = (f"падают все остальные {N-1} банка" if sec == N - 1 else f"падают ещё {sec} из {N-1} банков")
        text = (f"Банк {bank} не выдержал шока, и без помощи за ним друг за другом {_all} за {wv(waves)}. "
                "Следите за кольцами: банки по очереди теряют капитал, доходят до полного кольца и падают.")
    elif name == "chain":
        title = "Поддержка рвёт цепочку"
        who = f"помощь получает банк {saved[0]}" if saved else "помощь распределяется по очереди"
        text = (f"Тот же шок, но у государства есть бюджет {num(G)} ед. Сам банк {bank} спасать нельзя, он упал от шока. Зато {who} "
                f"(потрачено {num(spent)} ед.), и цепочка обрывается: вторичных дефолтов {sec} вместо {base_sec}.")
    elif name == "common":
        title = "Общий шок: помощь бессильна"
        waste = (" Но спасённые банки всё равно упали позже." if (resc_all and not saved) else "")
        text = (f"Шок бьёт по всем банкам сразу, и {direct} {ru_plural(direct, 'банк падает', 'банка падают', 'банков падают')} мгновенно. "
                f"Поддержка потратила {num(spent)} из {num(G)} ед. на {resc_all} {ru_plural(resc_all, 'банк', 'банка', 'банков')}.{waste} "
                f"Вторичных дефолтов с помощью {sec}, без помощи {base_sec}" + (": помощь ничего не изменила." if sec == base_sec else "."))
    else:
        title = "Резервы: обрыв на 6,5%"
        t60 = alt_trace("res", 0.06); d60 = len(t60["steps"][0]) + t60["secondary"]
        text = (f"Резервы добавили каждому банку по 2% активов. При шоке 6,0% " + ("не падает никто" if d60 == 0 else f"падает {d60}") + f": самому слабому нужно {num(k_now.min()*100)}%. "
                f"При {num(s*100)}% сразу падают {direct}, а за ними ещё {sec}. Между «ничего» и «почти всё» полпроцента. "
                "Передвиньте ползунок на 6,0%, чтобы увидеть обрыв.")
    story_html = f'<div class="story"><div class="t">{title}</div><p>{text}</p></div>'

cur = calc(topo, net_id, alpha, R, mech, Gabs); base = calc(topo, net_id, alpha, R, "none", Gabs)
key, curve = ("A1", "single") if shock_kind == "one" else ("A2", "Cg")
a_cur, a_base = cur[key], base[key]
delta = ""
if mech != "none":
    d = a_cur - a_base
    if abs(d) < 5e-6: delta = '<div class="note">Для этого типа шока механизм почти ничего не меняет.</div>'
    else:
        cls, word = ("good", "ниже") if d < 0 else ("bad", "выше")
        delta = f'<div class="note"><span class="{cls}">{fmt(abs(d))} {word}</span>, чем без помощи ({fmt(a_base)}).</div>'
svg = curve_svg(SGRID, base[curve], None if mech == "none" else cur[curve], s, MECHS[mech], THEME)
who = "по каждому банку по очереди" if shock_kind == "one" else "по всем банкам сразу"

right = (regime_card(*regime(topo, net_id, alpha, R, mech), N, S_REF, mech == "res")
         + story_html + f'<div class="sec-title">Этот шок</div><div class="card"><div class="row">{stats}</div>{extra}</div>'
         f'<div class="sec-title" style="margin-top:22px">Весь диапазон шоков</div>'
         f'<div class="card"><div class="stat"><div class="num blue">{fmt(a_cur)}</div>'
         f'<div class="lbl">интегральный масштаб каскада A, шоки 0–15%, удар {who}</div></div>{delta}'
         f'<div style="margin-top:18px">{svg}</div>'
         f'<div class="note">Доля банков, упавших из-за соседей, при шоке s. Серая линия — без помощи.</div></div>')

page = graph_html(topo, E, A, tr, bank, N, THEME, right=right, K=K)
sig = hashlib.md5(f"{topo}|{mech}|{shock_kind}|{bank}|{s:.4f}|{net_id}|{alpha}|{R}|{Gabs}|{THEME}".encode()).hexdigest()[:12]
with st.container(key=f"viz_{sig}"):      # новый ключ -> чистое пересоздание фрейма вместо «заплаток» старого
    embed(page, FRAME_H)
