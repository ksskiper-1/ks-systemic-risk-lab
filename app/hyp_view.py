"""HTML для раздела «Проверка гипотезы»: вердикт, график эффектов, воронка интервала, сетка чувствительности."""
import math
from viz import PALETTES, FONT


def f4(x, sign=True):
    s = f"{x:+.4f}" if sign else f"{x:.4f}"
    return s.replace(".", ",").replace("-", "−")


def forest(rows, delta, P):
    """rows: (подпись, оценка, нижняя, верхняя). Горизонтальный график оценок с 95% ДИ, ноль и пороги ±δ."""
    W, left, right, rh, top = 720, 230, 40, 62, 18
    H = top + rh * len(rows) + 46
    lo_all = min([r[2] for r in rows] + [-delta, 0]); hi_all = max([r[3] for r in rows] + [delta, 0])
    pad = (hi_all - lo_all) * 0.08; a, b = lo_all - pad, hi_all + pad
    sx = lambda v: left + (W - left - right) * (v - a) / (b - a)
    g = []
    for v, lab, dash in ((0, "0", ""), (delta, "+δ", "4 5"), (-delta, "−δ", "4 5")):
        g.append(f'<line x1="{sx(v):.1f}" x2="{sx(v):.1f}" y1="{top-4}" y2="{H-34}" stroke="{P["mute"] if dash else P["ink"]}" stroke-opacity="{.45 if dash else .7}" stroke-width="1.2" {f"stroke-dasharray={chr(34)}{dash}{chr(34)}" if dash else ""}/>')
        g.append(f'<text x="{sx(v):.1f}" y="{H-14}" text-anchor="middle" fill="{P["mute"]}" font-size="13">{lab}</text>')
    for i, (lab, est, lo, hi) in enumerate(rows):
        y = top + rh * i + rh / 2; strong = i == len(rows) - 1
        g.append(f'<text x="{left-18}" y="{y+5:.1f}" text-anchor="end" fill="{P["ink"]}" font-size="15" font-weight="{700 if strong else 500}">{lab}</text>')
        g.append(f'<line x1="{sx(lo):.1f}" x2="{sx(hi):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="{P["blue"]}" stroke-width="{4 if strong else 3}" stroke-linecap="round" stroke-opacity="{1 if strong else .55}"/>')
        g.append(f'<circle cx="{sx(est):.1f}" cy="{y:.1f}" r="{8 if strong else 6}" fill="{P["blue"]}"/>')
        g.append(f'<text x="{sx(est):.1f}" y="{y-16:.1f}" text-anchor="middle" fill="{P["ink"]}" font-size="14" font-weight="600">{f4(est)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;font-family:{FONT}">{"".join(g)}</svg>'


def funnel(cps, delta, P):
    """Как сужается 95% ДИ для T с ростом числа сетей n (логарифмическая ось)."""
    W, H, l, r, t, b = 720, 300, 64, 24, 20, 44
    lo_v = min(0, min(c["lo"] for c in cps)); hi_v = max(delta * 1.05, max(c["hi"] for c in cps)); pad = (hi_v - lo_v) * .08
    a, bb = lo_v - pad, hi_v + pad
    x0, x1 = math.log10(10), math.log10(1000)
    sx = lambda n: l + (W - l - r) * (math.log10(max(n, 10)) - x0) / (x1 - x0)
    sy = lambda v: H - b - (H - t - b) * (v - a) / (bb - a)
    g = []
    for v in sorted({0.0, delta}):
        g.append(f'<line x1="{l}" x2="{W-r}" y1="{sy(v):.1f}" y2="{sy(v):.1f}" stroke="{P["mute"] if v else P["ink"]}" stroke-opacity="{.5 if v else .6}" stroke-dasharray="{"4 5" if v else ""}"/>')
        g.append(f'<text x="{l-10}" y="{sy(v)+5:.1f}" text-anchor="end" fill="{P["mute"]}" font-size="13">{"δ" if v else "0"}</text>')
    pts_hi = " ".join(f"{sx(c['n']):.1f},{sy(c['hi']):.1f}" for c in cps); pts_lo = " ".join(f"{sx(c['n']):.1f},{sy(c['lo']):.1f}" for c in reversed(cps))
    if len(cps) > 1:
        g.append(f'<polygon points="{pts_hi} {pts_lo}" fill="{P["blue"]}" fill-opacity=".18"/>')
        g.append(f'<polyline points="{" ".join(f"{sx(c[chr(110)]):.1f},{sy(c[chr(84)]):.1f}" for c in cps)}" fill="none" stroke="{P["blue"]}" stroke-width="2.4" stroke-linejoin="round"/>')
    for c in cps:
        g.append(f'<line x1="{sx(c["n"]):.1f}" x2="{sx(c["n"]):.1f}" y1="{sy(c["lo"]):.1f}" y2="{sy(c["hi"]):.1f}" stroke="{P["blue"]}" stroke-opacity=".5" stroke-width="2"/>')
        g.append(f'<circle cx="{sx(c["n"]):.1f}" cy="{sy(c["T"]):.1f}" r="4.5" fill="{P["blue"]}"/>')
        g.append(f'<text x="{sx(c["n"]):.1f}" y="{H-18}" text-anchor="middle" fill="{P["mute"]}" font-size="13">{c["n"]}</text>')
    g.append(f'<text x="{(l+W-r)/2:.0f}" y="{H-1}" text-anchor="middle" fill="{P["mute"]}" font-size="13">число сетей n</text>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block;font-family:{FONT}">{"".join(g)}</svg>'


def heat(grid):
    """Три панели 3x3: строки R, столбцы α; цвет по знаку и величине T."""
    names = {"G0": "Бюджет G = 3% капитала (≈ 5,3)", "G25": "Бюджет G = 25", "G50": "Бюджет G = 50"}
    out = []
    for gk in ("G0", "G25", "G50"):
        cells = {(c["R"], c["alpha"]): c["T"] for c in grid if c["G"] == gk}
        rows = '<div class="hc hh"></div>' + "".join(f'<div class="hc hh">α = {str(a).replace(".", ",")}</div>' for a in (0.3, 0.5, 0.6))
        for R in (0.2, 0.4, 0.6):
            rows += f'<div class="hc hh">R = {str(R).replace(".", ",")}</div>'
            for a in (0.3, 0.5, 0.6):
                v = cells[(R, a)]; p = min(100, abs(v) / 0.04 * 100); col = "var(--blue)" if v > 0 else "var(--red)"
                rows += f'<div class="hc" style="background:color-mix(in srgb,{col} {max(p, 6):.0f}%,transparent)">{f4(v)}</div>'
        out.append(f'<div class="heat"><div class="ht">{names[gk]}</div><div class="hg">{rows}</div></div>')
    return '<div class="heats">' + "".join(out) + '</div>'


CSS = """
:root{--ink:__ink__;--mute:__mute__;--blue:__blue__;--red:__red__;--green:__good__;--warn:__warn__;--card:__card__;--ring:__ring__;--foot:__foot__}
*{box-sizing:border-box}html,body{margin:0;background:transparent;font-family:__FONT__;color:var(--ink);-webkit-font-smoothing:antialiased}
.wrap{max-width:none;margin:0;padding:4px 2px 28px}
.card{background:var(--card);border-radius:20px;padding:24px 28px;margin-bottom:16px;box-shadow:0 0 0 1px var(--ring)}
h3{font-size:22px;font-weight:700;letter-spacing:-.02em;margin:0 0 4px}
.sub{font-size:15px;line-height:1.5;color:var(--mute);margin:0 0 16px}
.verdict{background:var(--card);border-radius:20px;padding:24px 28px;margin-bottom:16px;box-shadow:0 0 0 1px var(--ring)}
.vt{font-size:40px;font-weight:700;letter-spacing:-.03em;line-height:1.1;margin-top:6px;font-variant-numeric:tabular-nums}
.vs{font-size:17px;margin-top:8px;color:var(--mute);font-variant-numeric:tabular-nums}
.crit{margin-top:18px;display:grid;gap:9px}
.cr{display:flex;gap:12px;align-items:baseline;font-size:16px;line-height:1.4}.cr i{flex:none;width:8px;height:8px;border-radius:50%;background:var(--mute);transform:translateY(-1px)}
.cr .m{color:var(--mute)}.cr .st{font-weight:600;margin-left:6px;white-space:nowrap}
.heats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}
@media (max-width:900px){.heats{grid-template-columns:1fr}}
.ht{font-size:15px;font-weight:600;margin-bottom:8px}.hg{display:grid;grid-template-columns:auto repeat(3,1fr);gap:4px}
.hc{padding:10px 6px;border-radius:8px;text-align:center;font-size:14px;font-variant-numeric:tabular-nums;font-weight:600}
.hh{background:transparent;color:var(--mute);font-weight:500;font-size:13px;padding:10px 4px}
table{width:100%;border-collapse:collapse;font-size:16px;font-variant-numeric:tabular-nums}
th{font-weight:500;color:var(--mute);text-align:left;padding:6px 8px;font-size:14px}td{padding:10px 8px;border-top:1px solid var(--ring)}
.badge{display:inline-block;padding:2px 10px;border-radius:980px;font-size:13px;font-weight:600;background:color-mix(in srgb,var(--warn) 22%,transparent)}
.note{font-size:14px;line-height:1.55;color:var(--mute);margin-top:12px}.foot{font-size:14px;color:var(--foot);line-height:1.55;margin-top:6px}
"""


def hyp_html(res, ver, pre, theme="dark"):
    P = PALETTES[theme]; delta = res["delta"]; T = res["T"]; lo, hi = res["ci"]; proto = res["mode"] == "proto"
    sup_ = pre["alpha_supplement"]
    tail = (f'n = {res["n"]} сетей' + ("" if not proto or len(res["path"]) == 1 else f' (выборка расширена по правилу: {" → ".join(str(p["n"]) for p in res["path"])})'))
    crit = [(ver["excl0"], "95% доверительный интервал для T не содержит 0", f'[{f4(lo)}; {f4(hi)}]'),
            (ver["big"], "|T| не меньше порога практической значимости δ", f'|T| = {f4(abs(T), False)}, δ = {f4(delta, False)}'),
            (ver["sign_share"] >= .9, "Знак T сохраняется в сетке чувствительности (порог 90%)", f'{ver["same_sign"]} из {ver["n_grid"]} ячеек')]
    crit_html = "".join(f'<div class="cr"><i></i><div>{txt} <span class="m">· {val}</span> <span class="st">{"выполнено" if ok else "не выполнено"}</span></div></div>' for ok, txt, val in crit)
    free_note = '' if proto else '<div class="note">Число сетей выбрано вручную, поэтому результат не заменяет основной эксперимент. Режим нужен, чтобы увидеть, как растёт точность оценки.</div>'
    v = (f'<div class="verdict"><h3>Результат проверки</h3><div class="vt">T = {f4(T)}</div>'
         f'<div class="vs">95% ДИ [{f4(lo)}; {f4(hi)}] · {tail}</div><div class="crit">{crit_html}</div>{free_note}</div>')
    rows = [("Δ, шок одного банка", res["Ds"], *res["ci_s"]), ("Δ, общий шок", res["Dg"], *res["ci_g"]), ("T = Δ(один) − Δ(общий)", T, lo, hi)]
    c1 = (f'<div class="card"><h3>Эффект поддержки</h3><p class="sub">Точка: оценка, линия: 95% доверительный интервал (bootstrap, 10 000 повторов). '
          f'Δ = (A конц., поддержка − A конц., без помощи) − (A распр., поддержка − A распр., без помощи). Пунктир: порог ±δ.</p>{forest(rows, delta, P)}</div>')
    c2 = (f'<div class="card"><h3>Как сужается интервал</h3><p class="sub">Оценка T и её 95% ДИ при росте числа сетей. Центр почти не двигается, ширина падает примерно как 1/√n. '
          f'Сети берутся как 0, 1, …, n−1, поэтому меньшие выборки вложены в большие.</p>{funnel(res["cps"], delta, P)}</div>')
    c3 = (f'<div class="card"><h3>Сетка чувствительности</h3><p class="sub">T при разных возврате по требованию R, доле межбанковских активов α и бюджете поддержки G '
          f'(по {pre["n_per_cell"]} сетей на ячейку, рассчитано заранее). Синий: T &gt; 0, красный: T &lt; 0. Знак T сохраняется в {ver["same_sign"]} из {ver["n_grid"]} ячеек.</p>{heat(pre["grid"])}</div>')
    trs = "".join(f'<tr><td>α = {a.replace(".", ",")}</td><td>{f4(d["T"])}</td><td>[{f4(d["CI"][0])}; {f4(d["CI"][1])}]</td><td>{d["T"]/delta*100:.0f}% от δ</td></tr>' for a, d in sup_.items())
    c4 = (f'<div class="card"><h3>Дополнение: меньшая доля межбанковских активов <span class="badge">вне заранее заданной проверки</span></h3>'
          f'<p class="sub">Сетка основного эксперимента охватывает α от 0,3 до 0,6. Здесь тот же расчёт при α = 0,1 и 0,2 (n = {sup_["0.1"]["n"]} сетей). Это дополнительный расчёт: он не меняет вывод основного эксперимента, но показывает границы применимости.</p>'
          f'<table><tr><th>Параметр</th><th>T</th><th>95% ДИ</th><th>Отношение к порогу</th></tr>{trs}</table></div>')
    foot = (f'<div class="foot">Порог δ = {f4(delta, False)} задан как 10% медианы A для распределённой сети без поддержки на 100 пилотных сетях, отдельных от сетей основного эксперимента. '
            f'Расчёт: {res["secs"]:.1f} с.</div>')
    css = CSS.replace("__FONT__", FONT)
    for k, val in P.items(): css = css.replace(f"__{k}__", val)
    return f'<!doctype html><html lang="ru" translate="no" class="notranslate"><head><meta charset="utf-8"><meta name="google" content="notranslate"><style>{css}</style></head><body><div class="wrap">{v}{c1}{c2}{c3}{c4}{foot}</div></body></html>'
