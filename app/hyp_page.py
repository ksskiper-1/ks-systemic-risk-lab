"""Страница «Проверка гипотезы» (Streamlit)."""
import streamlit as st
import hypothesis as H
from hyp_view import hyp_html


def hypothesis_page(theme, embed, seg):
    st.markdown(
        '<div class="sec-title" style="margin-top:6px">Проверка гипотезы</div>'
        '<p style="font-size:17px;line-height:1.55;max-width:860px;margin:0 0 6px">'
        '<b>H:</b> эффект государственной поддержки на каскады дефолтов зависит от структуры сети и различается при шоке одного банка и общем шоке.</p>'
        '<p style="font-size:15px;line-height:1.55;max-width:860px;opacity:.7;margin:0 0 18px">'
        'Статистика: T = Δ(один банк) − Δ(общий шок), где Δ — разность эффектов поддержки между концентрированной и распределённой сетью, '
        'измеренных по интегральному масштабу вторичных дефолтов A. Доверительный интервал: bootstrap.</p>', unsafe_allow_html=True)

    mode = seg("Режим", {"proto": "Основной эксперимент", "free": "Произвольное число сетей"}, "proto", "hyp_mode")

    for k, v in (("hyp_n_slider", 100), ("hyp_n_input", 100)):
        if k not in st.session_state: st.session_state[k] = v

    def from_slider(): st.session_state["hyp_n_input"] = st.session_state["hyp_n_slider"]
    def from_input():
        v = int(st.session_state["hyp_n_input"]); st.session_state["hyp_n_slider"] = int(min(1000, max(10, round(v / 10) * 10)))

    if mode == "free":
        c1, c2 = st.columns([3, 1], gap="large")
        c1.slider("Число сетей n", 10, 1000, step=10, key="hyp_n_slider", on_change=from_slider)
        c2.number_input("Точное значение", min_value=10, max_value=1000, step=1, key="hyp_n_input", on_change=from_input)
        n = int(st.session_state["hyp_n_input"])
        st.caption(f"Первый расчёт {n} сетей займёт около {max(1, round(n * 0.021))} с; повторные запуски мгновенные (результаты по сетям запоминаются). "
                   "Результат не заменяет основной эксперимент: число сетей выбрано вручную.")
    else:
        n = 100
        st.caption("Число сетей выбирается автоматически по заранее заданному правилу: 100 → 300 → 1000, пока ширина 95% доверительного интервала не станет меньше порога δ.")

    if st.button("Рассчитать", key="hyp_run", type="primary"):
        bar = st.progress(0.0, text="Расчёт сетей…")
        res = H.analyse(mode, n, progress=lambda k, m: bar.progress(k / m, text=f"Сети: {k} из {m}"))
        bar.empty()
        st.session_state["hyp_res"] = res

    res = st.session_state.get("hyp_res")
    if res:
        # 2860 px: максимум содержимого 2593 px (ручной режим, ширина 1920) по замерам check_ui.py (блок G) + ~10%
        embed(hyp_html(res, H.verdict(res), H.precomputed(), theme), 2860)
    else:
        st.markdown('<p style="opacity:.6;font-size:16px;margin-top:14px">Нажмите «Рассчитать», чтобы провести проверку.</p>', unsafe_allow_html=True)
