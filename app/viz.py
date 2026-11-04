"""Визуализация: граф с пошаговым каскадом (HTML-компонент) и кривая C(s) (SVG)."""
import json, math
import numpy as np

FONT = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Segoe UI", Roboto, system-ui, sans-serif'



PALETTES = {
 "dark":  dict(ink="#f5f5f7", mute="#98989d", blue="#0a84ff", red="#ff453a", dred="#b3170f", green="#30d158", node="#0b2a4a",
               nodetext="#6cb6ff", warn="#ff9f0a", edge="#5a5a5e", dot="#3a3a3c", bg="#000000", card="#1c1c1e", ring="rgba(255,255,255,.07)", grid="#3a3a3c",
               gray="#636366", savedtext="#032d10", good="#30d158", bad="#ff6961", foot="#8e8e93", edgeop=".5"),
 "light": dict(ink="#1d1d1f", mute="#6e6e73", blue="#0071e3", red="#ff3b30", dred="#b3261e", green="#34c759", node="#eaf2fd",
               nodetext="#0071e3", warn="#ff9500", edge="#a1a1a6", dot="#d2d2d7", bg="#ffffff", card="#f5f5f7", ring="rgba(0,0,0,.05)", grid="#d2d2d7",
               gray="#c7c7cc", savedtext="#ffffff", good="#1f9d46", bad="#d70015", foot="#86868b", edgeop=".45"),
}

def ru_plural(n, one, few, many):
    n = abs(int(n)); 
    if n % 10 == 1 and n % 100 != 11: return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14: return few
    return many


def layout(topo, N=25, size=600):
    c = size / 2; pos = []
    if topo == 0:
        R = 238
        for i in range(N):
            a = -math.pi / 2 + 2 * math.pi * i / N
            pos.append((c + R * math.cos(a), c + R * math.sin(a)))
    else:
        r_core, R = 88, 238
        for i in range(5):
            a = -math.pi / 2 + 2 * math.pi * i / 5
            pos.append((c + r_core * math.cos(a), c + r_core * math.sin(a)))
        for k in range(N - 5):
            a = -math.pi / 2 + 2 * math.pi * (k + 0.5) / (N - 5)
            pos.append((c + R * math.cos(a), c + R * math.sin(a)))
    return pos


def captions(tr, single_bank, N):
    steps, resc = tr["steps"], tr["rescued"]; out = []
    d0 = len(steps[0])
    if single_bank is not None:
        out.append(f"Шок по банку {single_bank}: " + ("банк не выдержал" if d0 else "банк выдержал, каскада нет"))
    else:
        out.append("Общий шок: " + (f"сразу упало {d0} {ru_plural(d0,'банк','банка','банков')}" if d0 else "все банки выдержали"))
    for t in range(1, len(steps)):
        n = len(steps[t]); m = len(resc[t]); parts = []
        if n: parts.append(f"упало ещё {n}")
        if m: parts.append(f"спасено {m}")
        out.append(f"Волна {t}: " + ", ".join(parts))
    return out


def _pc(x, d=2):
    return f"{x * 100:.{d}f}".replace(".", ",") + "%"


def captions_S(rec, single_bank, s, N):
    """Подписи шагов режима S: шаг = итерация ядра, последний шаг = равновесие contagion.propagate_batch."""
    out = []; h0 = rec["h"][0]
    if single_bank is not None:
        out.append(f"Шок {_pc(s, 1)} по банку {single_bank}: потеряно {_pc(min(1.0, float(h0[single_bank])), 0)} его капитала")
    else:
        out.append(f"Общий шок {_pc(s, 1)}: прямые потери {_pc(rec['S_dir'])} активов системы")
    its = rec["it"]
    for t in range(1, len(its)):
        S, k = _pc(rec["S"][t]), rec["sat"][t]
        if t == len(its) - 1:
            skip = f" (итерации {its[t-1]+1}–{its[t]} сведены в итог)" if its[t] - its[t - 1] > 1 else ""
            out.append(f"Равновесие, итерация {its[t]}{skip}: S_ind = {S} активов, h ≈ 1 у {k} из {N}")
        else:
            out.append(f"Итерация {its[t]}: S_ind = {S} активов, h ≈ 1 у {k} из {N}")
    return out


def graph_html(topo, E, A, tr, single_bank, N=25, theme="dark", right="", K=None, s_rec=None, s=None):
    """tr - запись каскада дефолтов (режим «Дефолты»); s_rec - запись s_trace (режим «Заражение (S)»)."""
    pos = layout(topo, N)
    Emax = E.max() if E.max() > 0 else 1
    edges = [dict(i=int(i), j=int(j), w=float(E[i, j] / Emax)) for i in range(N) for j in range(N) if E[i, j] > 0]
    rmean = float(np.mean(A))
    def _node(i):
        cr = sorted(((a, float(E[a, i])) for a in range(N) if E[a, i] > 0), key=lambda x: -x[1])   # кредиторы: кто потеряет, если i упадёт
        return dict(x=round(pos[i][0], 1), y=round(pos[i][1], 1), r=round(15 * math.sqrt(A[i] / rmean), 1),
                    A=round(float(A[i]), 1), K=None if K is None else round(float(K[i]), 1),
                    nc=len(cr), cred=[[int(a), round(w, 1)] for a, w in cr[:3]])
    nodes = [_node(i) for i in range(N)]
    if s_rec is None:
        data = dict(nodes=nodes, edges=edges, steps=tr["steps"], rescued=tr["rescued"], ratios=tr["ratios"],
                    captions=captions(tr, single_bank, N), shocked=[] if single_bank is None else [int(single_bank)], N=N,
                    core=[0, 1, 2, 3, 4] if topo == 1 else [])
    else:
        data = dict(mode="S", nodes=nodes, edges=edges, h=[[float(x) for x in h] for h in s_rec["h"]],
                    S=[float(x) for x in s_rec["S"]], it=[int(x) for x in s_rec["it"]], sat=[int(x) for x in s_rec["sat"]],
                    n_iter=int(s_rec["n_iter"]), sat_tol=float(s_rec["sat_tol"]), captions=captions_S(s_rec, single_bank, s, N),
                    shocked=[] if single_bank is None else [int(single_bank)], N=N, core=[0, 1, 2, 3, 4] if topo == 1 else [])
    html = HTML.replace("__RIGHT__", right).replace("__DATA__", json.dumps(data)).replace("__FONT__", FONT)
    html = html.replace("__MODE__", "mS" if s_rec is not None else "mD")
    for k, val in PALETTES[theme].items(): html = html.replace(f"__{k}__", val)
    return html


def regime_card(rho, sat, N, s_ref, with_reserves=False):
    """Компактная строка «Режим передачи стресса»: rho и доля насыщенных банков — две отдельные величины.
    Значения считаются в app.py функциями contagion.spectral_radius / saturated_share; здесь только вёрстка."""
    f2 = lambda x: f"{x:.2f}".replace(".", ",")
    pct = str(round(s_ref * 100, 2)).rstrip("0").rstrip(".").replace(".", ",")
    sat_num, sat_lbl = (("—", "насыщение: расчёт не сошёлся") if sat is None
                        else (f"{int(round(sat * N))} из {N}", f"насыщены (h ≈ 1) при общем шоке {pct}%"))
    return (f'<div class="card rg"><div class="rgt">Режим передачи стресса</div><div class="rgr">'
            f'<div class="num">{f2(rho)}</div><div class="lbl">спектральный радиус ρ</div>'
            f'<div class="num">{sat_num}</div><div class="lbl">{sat_lbl}</div></div>'
            f'<div class="note">ρ &lt; 1: стресс затухает, ρ &gt; 1: усиливается; насыщение — по доле банков с h ≈ 1, '
            f'при больших α насыщение всех банков ожидаемо.</div></div>')


def curve_svg(sgrid, base, cur, marker_s, label_cur, theme="dark"):
    P = PALETTES[theme]
    mute, grid, gray, blue, ink, bgc = P["mute"], P["grid"], P["gray"], P["blue"], P["ink"], P["bg"]
    """base - кривая без поддержки (серая), cur - выбранный механизм (синяя); None если совпадает."""
    W, H, pl, pr, pt, pb = 420, 170, 8, 8, 14, 28
    ymax = max(float(np.max(base)), float(np.max(cur)) if cur is not None else 0, 0.02) * 1.15
    sx = lambda s: pl + (W - pl - pr) * s / sgrid[-1]
    sy = lambda v: H - pb - (H - pt - pb) * v / ymax
    def path(c):
        idx = list(range(0, len(sgrid), 6)); 
        if idx[-1] != len(sgrid) - 1: idx.append(len(sgrid) - 1)
        return "M" + " L".join(f"{sx(sgrid[i]):.1f},{sy(c[i]):.1f}" for i in idx)
    g = []
    base_color = blue if cur is None else gray
    for s in (0, .05, .10, .15):
        anc = "start" if s == 0 else ("end" if s == .15 else "middle")
        g.append(f'<text x="{sx(s):.1f}" y="{H-8}" text-anchor="{anc}" fill="{mute}" font-size="12">{int(s*100)}%</text>')
    g.append(f'<line x1="{pl}" x2="{W-pr}" y1="{H-pb}" y2="{H-pb}" stroke="{grid}"/>')
    g.append(f'<path d="{path(base)}" fill="none" stroke="{base_color}" stroke-width="2.4" stroke-linejoin="round"/>')
    if cur is not None:
        g.append(f'<path d="{path(cur)}" fill="none" stroke="{blue}" stroke-width="2.4" stroke-linejoin="round"/>')
    ms = min(max(marker_s, 0), sgrid[-1]); line = cur if cur is not None else base
    i = int(round(ms / (sgrid[1] - sgrid[0]))); 
    g.append(f'<line x1="{sx(ms):.1f}" x2="{sx(ms):.1f}" y1="{pt}" y2="{H-pb}" stroke="{ink}" stroke-opacity=".3" stroke-dasharray="3 4"/>')
    g.append(f'<circle cx="{sx(ms):.1f}" cy="{sy(line[i]):.1f}" r="4.5" fill="{bgc}" stroke="{blue}" stroke-width="2.4"/>')
    return f'<svg viewBox="0 0 {W} {H}" width="100%" style="font-family:{FONT};display:block">{"".join(g)}</svg>'


HTML = r"""<!doctype html><html lang="ru" translate="no" class="notranslate"><head><meta charset="utf-8"><meta name="google" content="notranslate"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
:root{--ink:__ink__;--mute:__mute__;--blue:__blue__;--red:__red__;--dred:__dred__;--green:__green__;--node:__node__;--nodetext:__nodetext__;--warn:__warn__;--edge:__edge__;--dot:__dot__;--saved:__savedtext__;--edgeop:__edgeop__;--card:__card__;--ring:__ring__;--good:__good__;--bad:__bad__;--foot:__foot__}
*{box-sizing:border-box}html,body{margin:0;background:transparent;font-family:__FONT__;color:var(--ink);-webkit-font-smoothing:antialiased}
.layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:44px;align-items:start;padding:4px 2px 24px}
@media (max-width:860px){.layout{grid-template-columns:minmax(0,1fr);gap:28px}}
.wrap{max-width:640px;margin:0 auto;position:relative}
.sec-title{font-size:24px;font-weight:700;letter-spacing:-.02em;margin:6px 0 14px}
.card{background:var(--card);border-radius:20px;padding:22px 24px;margin-bottom:14px;box-shadow:0 0 0 1px var(--ring)}
.row{display:flex;gap:28px;flex-wrap:wrap}
.stat .num{font-size:56px;line-height:1;font-weight:700;letter-spacing:-.035em;font-variant-numeric:tabular-nums}
.stat .num.red{color:var(--red)}.stat .num.green{color:var(--good)}.stat .num.blue{color:var(--blue)}
.stat .lbl{font-size:16px;color:var(--mute);margin-top:8px;line-height:1.3}
.note{font-size:15px;color:var(--mute);line-height:1.45;margin-top:12px}
.good{color:var(--good);font-weight:600}.bad{color:var(--bad);font-weight:600}
.rg{padding:14px 20px}.rgt{font-size:15px;font-weight:700;margin-bottom:6px}.rg .note{margin-top:6px;font-size:13px;line-height:1.35}
.rgr{display:grid;grid-template-columns:auto 1fr auto 1fr;gap:4px 10px;align-items:baseline}.rgr .num{font-size:24px;font-weight:700;font-variant-numeric:tabular-nums;white-space:nowrap}.rgr .lbl{font-size:13px;color:var(--mute);line-height:1.25}
.foot{font-size:14px;color:var(--foot);margin-top:20px;line-height:1.5}
svg{width:100%;height:auto;display:block}
.edge{fill:none;stroke:var(--edge);stroke-opacity:var(--edgeop);transition:stroke .5s,stroke-opacity .5s}
.edge.hot{stroke:var(--red);stroke-opacity:.7}
.node circle.body{fill:var(--node);stroke:var(--blue);stroke-width:1.6;transition:fill .55s,stroke .55s}
.node text{font-size:11.5px;font-weight:600;fill:var(--nodetext);text-anchor:middle;dominant-baseline:central;transition:fill .55s;font-variant-numeric:tabular-nums}
.node.direct circle.body{fill:var(--dred);stroke:var(--dred)}.node.sec circle.body{fill:var(--red);stroke:var(--red)}
.node.saved circle.body{fill:var(--green);stroke:var(--green)}
.node.saved.risk circle.body{fill:var(--node);stroke:var(--red);stroke-width:3;stroke-dasharray:4 3}.node.saved.risk text{fill:var(--nodetext)}
.node.direct text,.node.sec text{fill:#fff}.node.saved text{fill:var(--saved)}
.ring{fill:none;stroke:var(--blue);stroke-width:3;stroke-linecap:butt;transition:stroke-dasharray .6s ease,stroke .5s,opacity .4s}
.ring.mid{stroke:var(--warn)}.ring.hi{stroke:var(--red)}.ring.off{opacity:0}
.ring.brink{animation:pulse 1.1s ease-in-out infinite}@keyframes pulse{50%{opacity:.3}}
.ringnote{margin:8px 6px 0;font-size:14px;line-height:1.45;color:var(--mute)}
.story{border-radius:20px;padding:20px 24px;margin-bottom:22px;background:color-mix(in srgb,var(--blue) 14%,transparent)}
.story .t{font-size:20px;font-weight:700;letter-spacing:-.015em;margin-bottom:6px}
.story p{margin:0;font-size:16px;line-height:1.5;color:var(--ink)}
.halo{fill:none;stroke:var(--red);stroke-width:1.6;stroke-dasharray:3 4;opacity:0;transition:opacity .4s}.halo.on{opacity:1}
.bar{display:flex;align-items:center;gap:14px;margin:6px 4px 0;min-height:40px}.bar.hidden{display:none}
.play{flex:none;width:40px;height:40px;border-radius:50%;border:0;background:var(--blue);cursor:pointer;display:grid;place-items:center;transition:transform .15s,background .2s}
.play:hover{background:#409cff}.play:active{transform:scale(.94)}.play:focus-visible{outline:3px solid #7ab8ff;outline-offset:2px}
.play svg{width:16px;height:16px;fill:#fff}
.dots{display:flex;gap:7px;flex-wrap:wrap;flex:1 1 0;min-width:0}
.nav{flex:none;height:34px;padding:0 13px;border-radius:17px;border:1.5px solid var(--blue);background:transparent;color:var(--blue);font-family:inherit;font-size:14px;font-weight:600;line-height:1;white-space:nowrap;cursor:pointer;transition:background .2s,opacity .2s}
.nav:hover:not(:disabled){background:rgba(10,132,255,.12)}.nav:focus-visible{outline:3px solid #7ab8ff;outline-offset:2px}
.nav:disabled{opacity:.35;cursor:default;border-color:var(--mute);color:var(--mute)}
.dot{width:10px;height:10px;border-radius:50%;background:var(--dot);border:0;padding:0;cursor:pointer;transition:background .3s,transform .3s}
.dot.on{background:var(--blue)}.dot.cur{transform:scale(1.5)}
.cap{margin:12px 6px 0;font-size:19px;line-height:1.35;font-weight:600;letter-spacing:-.01em;min-height:52px}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin:10px 6px 0;font-size:14px;color:var(--mute)}
.legend i{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:7px;vertical-align:-1px}
.node{cursor:default}.node.pick{cursor:pointer}
.tip{position:absolute;z-index:5;pointer-events:none;opacity:0;transition:opacity .12s;width:250px;background:var(--card);color:var(--ink);border-radius:14px;padding:12px 14px;box-shadow:0 0 0 1px var(--ring),0 8px 28px rgba(0,0,0,.28);font-size:13.5px;line-height:1.4}
.tip.on{opacity:1}.tip .tt{font-size:16px;font-weight:700;margin-bottom:6px}
.tip .tr{display:flex;justify-content:space-between;gap:10px;padding:2px 0}.tip .tr span{color:var(--mute)}.tip .tr b{font-weight:600;text-align:right}
.tip .tc{margin-top:6px;padding-top:6px;border-top:1px solid var(--ring);color:var(--mute)}.tip .th{margin-top:6px;color:var(--blue);font-weight:600}
.waves{margin:18px 6px 0}.wt{font-size:14px;font-weight:600;color:var(--mute);margin-bottom:6px}
.wb{display:flex;gap:6px;align-items:flex-end}
.wc{flex:1 1 0;min-width:0;cursor:pointer;transition:opacity .3s}.wc.fut{opacity:.3}
.wbars{display:flex;gap:3px;align-items:flex-end;justify-content:center;height:96px}
.wbar{flex:1 1 0;max-width:34px;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;height:100%}
.wbar span{font-size:12px;font-weight:600;color:var(--mute);font-variant-numeric:tabular-nums;min-height:15px}
.wbar b{display:block;width:100%;border-radius:5px 5px 2px 2px;min-height:2px}
.wbar b.d{background:var(--dred)}.wbar b.s{background:var(--red)}.wbar b.g{background:var(--green)}
.wl{text-align:center;font-size:12px;color:var(--mute);margin-top:4px;border-top:1px solid var(--ring);padding-top:4px;font-variant-numeric:tabular-nums}
.wc.now .wl{color:var(--ink);font-weight:700}
.mS .ldD,.mD .ldS{display:none}
.node.s circle.body{stroke:var(--red);stroke-width:1.6}.node.s.sat circle.body{fill:var(--red)}.node.s.sat text{fill:#fff}
.wbar b.sv{background:var(--red)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}.ring.brink{animation:none}}
</style></head><body class="__MODE__"><div class="layout"><div class="left"><div class="wrap">
<svg id="g" viewBox="0 0 600 600" role="img" aria-label="Сеть банков"></svg><div class="tip" id="tip"></div>
<div class="bar"><button class="play" id="play" aria-label="Запустить сначала"></button><button class="nav" id="prev" type="button" aria-label="Предыдущий шаг">← Назад</button><button class="nav" id="next" type="button" aria-label="Следующий шаг">Вперёд →</button><div class="dots" id="dots"></div></div>
<div class="cap" id="cap" aria-live="polite"></div>
<div class="legend ldS"><span><i style="background:var(--node);border:1.5px solid var(--red)"></i>h = 0: без потерь</span><span><i style="background:color-mix(in srgb,var(--red) 45%,var(--node))"></i>0 &lt; h &lt; 1: чем темнее, тем больше потеряно</span><span><i style="background:var(--red)"></i>h ≈ 1: весь капитал потерян</span></div>
<div class="ringnote ldS">h — доля потерянного капитала банка. Цвет и кольцо показывают h на выбранном шаге. Шаг — одна итерация пересчёта потерь, последний шаг — равновесие. Красные связи: должник потерял не меньше половины капитала. Шаги можно листать стрелками ← и →.</div>
<div class="legend ldD"><span><i style="background:var(--node);border:1.5px solid var(--blue)"></i>работает</span><span><i style="background:var(--dred)"></i>упал от шока</span><span><i style="background:var(--red)"></i>упал из-за соседей</span><span><i style="background:var(--green)"></i>спасён</span><span><i style="background:var(--node);border:2px dashed var(--red)"></i>спасён, снова на грани</span></div>
<div class="ringnote ldD">Кольцо вокруг банка показывает, какая часть его капитала уже потеряна. Полное мигающее кольцо: банк на грани и упадёт на следующей волне. Шаги можно листать стрелками ← и →.</div>
<div class="waves" id="waves"></div>
</div></div>
<div class="right">__RIGHT__</div></div>
<script>
(function(){
try{const pd=parent.document;pd.documentElement.setAttribute("translate","no");pd.documentElement.classList.add("notranslate");pd.documentElement.lang="ru";
if(!pd.querySelector('meta[name="google"]')){const m=pd.createElement("meta");m.name="google";m.content="notranslate";pd.head.appendChild(m)}}catch(e){}
const D=__DATA__;const NS="http://www.w3.org/2000/svg";const fm=(x,d)=>x.toFixed(d).replace(".",",");const g=document.getElementById("g");
const el=(n,a,p)=>{const e=document.createElementNS(NS,n);for(const k in a)e.setAttribute(k,a[k]);(p||g).appendChild(e);return e};
const edgeEls=D.edges.map(e=>{const a=D.nodes[e.i],b=D.nodes[e.j];const mx=(a.x+b.x)/2,my=(a.y+b.y)/2,dx=b.x-a.x,dy=b.y-a.y,L=Math.hypot(dx,dy)||1;
 const k=0.09;const cx=mx+dy/L*L*k,cy=my-dx/L*L*k;const p=el("path",{d:`M${a.x},${a.y} Q${cx.toFixed(1)},${cy.toFixed(1)} ${b.x},${b.y}`,class:"edge","stroke-width":(0.6+1.5*e.w).toFixed(2)});return p});
const halos=D.shocked.map(i=>{const n=D.nodes[i];return el("circle",{cx:n.x,cy:n.y,r:n.r+10,class:"halo on"})});
const ringEls=[],bodyEls=[];const nodeEls=D.nodes.map((n,i)=>{const gr=el("g",{class:"node"});bodyEls.push(el("circle",{cx:n.x,cy:n.y,r:n.r,class:"body"},gr));const rr=n.r+4.5;const rg=el("circle",{cx:n.x,cy:n.y,r:rr,class:"ring off",transform:`rotate(-90 ${n.x} ${n.y})`,"stroke-dasharray":`0 ${2*Math.PI*rr}`},gr);rg._c=2*Math.PI*rr;ringEls.push(rg);const t=el("text",{x:n.x,y:n.y},gr);t.textContent=i;return gr});
const SM=D.mode==="S";const T=SM?D.h.length:D.steps.length;let cur=0,timer=null,touched=false,status=[];
const bar=document.querySelector(".bar"),dots=document.getElementById("dots"),cap=document.getElementById("cap"),play=document.getElementById("play");
const prevB=document.getElementById("prev"),nextB=document.getElementById("next");
const dotEls=[];for(let t=0;t<T;t++){const b=document.createElement("button");b.className="dot";b.setAttribute("aria-label","Шаг "+t);b.onclick=()=>{touched=true;pause();show(t)};dots.appendChild(b);dotEls.push(b)}
const wv=document.getElementById("waves");
if(SM)(function(){const mx=Math.max(1e-12,...D.S);const L=D.it.length;
 let h='<div class="wt">S_ind после шага, % суммарных активов (потери капитала из-за заражения)</div><div class="wb">';
 for(let t=0;t<L;t++){const v=D.S[t]*100;
  h+='<div class="wc" data-t="'+t+'" title="'+(t===0?'Шок':(t===L-1?'Равновесие, итерация '+D.it[t]:'Итерация '+D.it[t]))+'"><div class="wbars">'
   +'<div class="wbar"><span>'+v.toFixed(1).replace(".",",")+'</span><b class="sv" style="height:'+Math.round(D.S[t]/mx*70)+'px"></b></div>'
   +'</div><div class="wl">'+(t===0?'шок':(t===L-1?'итог':D.it[t]))+'</div></div>'}
 wv.innerHTML=h+'</div>';
 wv.querySelectorAll(".wc").forEach(c=>c.onclick=()=>{touched=true;pause();show(+c.dataset.t)})})();
else (function(){const anyS=D.rescued.some(a=>a.length);const mx=Math.max(1,...D.steps.map(s=>s.length),...D.rescued.map(s=>s.length));
 let h='<div class="wt">Сколько банков упало на каждой волне</div><div class="wb">';
 for(let t=0;t<T;t++){const n=D.steps[t].length,m=D.rescued[t].length;
  h+='<div class="wc" data-t="'+t+'" title="'+(t===0?'От шока':'Волна '+t)+'"><div class="wbars">'
   +'<div class="wbar"><span>'+n+'</span><b class="'+(t===0?'d':'s')+'" style="height:'+Math.round(n/mx*70)+'px"></b></div>'
   +(anyS?'<div class="wbar"><span>'+(m||"")+'</span><b class="g" style="height:'+Math.round(m/mx*70)+'px"></b></div>':'')
   +'</div><div class="wl">'+(t===0?'шок':t)+'</div></div>'}
 wv.innerHTML=h+'</div>';
 wv.querySelectorAll(".wc").forEach(c=>c.onclick=()=>{touched=true;pause();show(+c.dataset.t)})})();
const I_PLAY='<svg viewBox="0 0 16 16"><path d="M4.5 2.5v11l9-5.5z"/></svg>',
 I_PAUSE='<svg viewBox="0 0 16 16"><rect x="3.5" y="2.5" width="3.2" height="11" rx="1"/><rect x="9.3" y="2.5" width="3.2" height="11" rx="1"/></svg>',
 I_RE='<svg viewBox="0 0 16 16"><path d="M8 2.2a5.8 5.8 0 1 0 5.6 7.3h-1.7A4.2 4.2 0 1 1 8 3.8c1.2 0 2.2.5 3 1.2L9 7h5V2l-1.9 1.9A5.8 5.8 0 0 0 8 2.2z"/></svg>';
function btn(){const playing=timer!==null;const m=playing?[I_PAUSE,"Пауза"]:(cur>=T-1?[I_RE,"Показать сначала"]:[I_PLAY,"Продолжить"]);play.innerHTML=m[0];play.setAttribute("aria-label",m[1]);play.title=m[1]}
function showS(t){cur=t;const h=D.h[t],sat=1-D.sat_tol;
 nodeEls.forEach((n,i)=>{n.setAttribute("class","node s"+(h[i]>=sat?" sat":""));
  bodyEls[i].style.fill=h[i]>=sat?"":"color-mix(in srgb,var(--red) "+Math.round(Math.min(h[i],1)*85)+"%,var(--node))"});
 ringEls.forEach((rg,i)=>{const r=h[i];rg.setAttribute("class","ring"+(r<0.02?" off":(r>=sat?" hi":(r>=0.5?" mid":""))));
  rg.setAttribute("stroke-dasharray",`${Math.min(r,1)*rg._c} ${rg._c}`)});
 status=D.nodes.map((_,i)=>h[i]>=sat?"ssat":(h[i]>=0.005?"sloss":"sok"));
 wv.querySelectorAll(".wc").forEach(c=>{const s=+c.dataset.t;c.className="wc"+(s<=t?"":" fut")+(s===t?" now":"")});
 D.edges.forEach((e,k)=>edgeEls[k].classList.toggle("hot",h[e.j]>=0.5));
 dotEls.forEach((d,s)=>d.className="dot"+(s<=t?" on":"")+(s===t?" cur":""));
 cap.textContent=D.captions[t];
 const sn=document.getElementById("sNow"),sk=document.getElementById("satNow"),sl=document.getElementById("stepNow");
 if(sn)sn.textContent=fm(D.S[t]*100,2)+"%";if(sk)sk.textContent=D.sat[t]+" из "+D.N;
 if(sl)sl.textContent=t===0?"шок, до заражения":(t===T-1?"равновесие, итерация "+D.it[t]:"итерация "+D.it[t]);
 prevB.disabled=(t<=0);nextB.disabled=(t>=T-1);btn()}
function show(t){if(SM)return showS(t);cur=t;const dead=new Set(),saved=new Set();
 for(let s=0;s<=t;s++){D.steps[s].forEach(i=>dead.add(i));D.rescued[s].forEach(i=>saved.add(i))}
 nodeEls.forEach((n,i)=>{let c="node";if(dead.has(i))c+=D.steps[0].includes(i)?" direct":" sec";else if(saved.has(i))c+=" saved"+(D.ratios[t][i]>=1?" risk":"");n.setAttribute("class",c)});
 ringEls.forEach((rg,i)=>{const r=D.ratios[t][i];const off=dead.has(i)||(saved.has(i)&&r<1)||r<0.02;
  rg.setAttribute("class","ring"+(off?" off":(r>=1?" hi brink":(r>=0.5?" mid":""))));
  rg.setAttribute("stroke-dasharray",`${Math.min(r,1)*rg._c} ${rg._c}`)});
 status=D.nodes.map((_,i)=>dead.has(i)?(D.steps[0].includes(i)?"direct":"sec"):(saved.has(i)?(D.ratios[t][i]>=1?"savedrisk":"saved"):"ok"));
 wv.querySelectorAll(".wc").forEach(c=>{const s=+c.dataset.t;c.className="wc"+(s<=t?"":" fut")+(s===t?" now":"")});
 D.edges.forEach((e,k)=>edgeEls[k].classList.toggle("hot",dead.has(e.j)));
 dotEls.forEach((d,s)=>d.className="dot"+(s<=t?" on":"")+(s===t?" cur":""));
 let txt=D.captions[t];if(t===T-1){txt+=` — итого в дефолте ${dead.size} из ${D.N}`}cap.textContent=txt;prevB.disabled=t<=0;nextB.disabled=t>=T-1;btn()}
function pause(){if(timer){clearInterval(timer);timer=null}btn()}
function start(){if(timer||T===1)return;timer=setInterval(()=>{if(cur<T-1)show(cur+1);if(cur>=T-1)pause()},950);btn()}
play.onclick=()=>{touched=true;if(timer)pause();else{if(cur>=T-1)show(0);start()}};
function step(d){const t=Math.min(T-1,Math.max(0,cur+d));touched=true;pause();if(t!==cur)show(t)}
prevB.onclick=()=>step(-1);nextB.onclick=()=>step(1);

const tip=document.getElementById("tip"),wrapEl=document.querySelector(".wrap");
const STS={sok:"без потерь",sloss:"теряет капитал",ssat:"насыщен: весь капитал потерян"};
function tipS(i){const n=D.nodes[i],h=D.h[cur][i],sat=h>=1-D.sat_tol,h0=D.h[0][i];
 let s='<div class="tt">Банк '+i+(D.core.includes(i)?" · ядро":"")+'</div><div class="tr"><span>Состояние</span><b>'+STS[status[i]]+'</b></div>'
  +'<div class="tr"><span>Активы</span><b>'+fm(n.A,1)+'</b></div>';
 if(n.K!=null)s+='<div class="tr"><span>Капитал</span><b>'+fm(n.K,1)+' ('+fm(n.K/n.A*100,1)+'% активов)</b></div>';
 s+='<div class="tr"><span>Потеряно капитала, h</span><b>'+(sat?"весь (h ≈ 1)":fm(h*100,1)+"% (h = "+fm(h,3)+")")+'</b></div>';
 if(cur>0)s+='<div class="tr"><span>За этот шаг</span><b>+'+fm(Math.max(0,h-D.h[cur-1][i])*100,1)+' п. п.</b></div>';
 if(h0>0)s+='<div class="tr"><span>Из них прямой шок</span><b>'+fm(Math.min(h0,1)*100,1)+'% капитала</b></div>';
 s+='<div class="tc">'+(n.nc?'Кредиторы (теряют вместе с ростом h этого банка): '+n.cred.map(c=>"банк "+c[0]+" ("+fm(c[1],1)+")").join(", ")+(n.nc>3?" и ещё "+(n.nc-3):""):"Кредиторов нет")+'</div>';
 if(pickBtn(i))s+='<div class="th">Клик: ударить шоком по этому банку</div>';
 return s}

const STX={ok:"работает",direct:"упал от шока",sec:"упал из-за соседей",saved:"спасён поддержкой",savedrisk:"спасён, но снова на грани дефолта"};
function pickBtn(i){try{return parent.document.querySelector(".st-key-pick_"+i+" button")}catch(e){return null}}
function tipHtml(i){if(SM)return tipS(i);const n=D.nodes[i],st=status[i],r=D.ratios[cur][i];
 let h='<div class="tt">Банк '+i+(D.core.includes(i)?" · ядро":"")+'</div><div class="tr"><span>Статус</span><b>'+STX[st]+'</b></div>'
  +'<div class="tr"><span>Активы</span><b>'+fm(n.A,1)+'</b></div>';
 if(n.K!=null)h+='<div class="tr"><span>Капитал</span><b>'+fm(n.K,1)+' ('+fm(n.K/n.A*100,1)+'% активов)</b></div>';
 if(st==="ok"||st==="saved"||st==="savedrisk")h+='<div class="tr"><span>Потеряно капитала</span><b>'+(r>=1?"весь, на грани":Math.round(r*100)+"%")+'</b></div>';
 h+='<div class="tc">'+(n.nc?'Кредиторы (потеряют, если банк упадёт): '+n.cred.map(c=>"банк "+c[0]+" ("+fm(c[1],1)+")").join(", ")+(n.nc>3?" и ещё "+(n.nc-3):""):"Кредиторов нет")+'</div>';
 if(pickBtn(i))h+='<div class="th">Клик: ударить шоком по этому банку</div>';
 return h}
function place(ev){const w=wrapEl.getBoundingClientRect();let x=ev.clientX-w.left+16,y=ev.clientY-w.top+16;
 if(x+250>w.width)x=ev.clientX-w.left-250-16;if(x<0)x=0;
 const th=tip.offsetHeight;if(y+th>w.height)y=Math.max(0,ev.clientY-w.top-th-16);
 tip.style.left=x+"px";tip.style.top=y+"px"}
nodeEls.forEach((nd,i)=>{
 nd.addEventListener("pointerenter",ev=>{tip.innerHTML=tipHtml(i);nd.classList.toggle("pick",!!pickBtn(i));tip.classList.add("on");place(ev)});
 nd.addEventListener("pointermove",place);
 nd.addEventListener("pointerleave",()=>tip.classList.remove("on"));
 nd.addEventListener("click",()=>{const b=pickBtn(i);if(b){tip.classList.remove("on");b.click()}});
});
// стрелки не листают каскад при вводе: поля, списки, ползунки и переключатели Streamlit (role=...) и с модификаторами
const TYPING='input,textarea,select,[contenteditable=""],[contenteditable="true"],[role="slider"],[role="spinbutton"],[role="textbox"],[role="combobox"],[role="listbox"],[role="radiogroup"],[role="tablist"],[role="menu"]';
function typing(ev){const g=ev.target;if(!g)return false;const a=g.tagName;
 if(a==="INPUT"||a==="TEXTAREA"||a==="SELECT"||g.isContentEditable)return true;
 return !!(g.closest&&g.closest(TYPING))}
function onKey(ev){const k=ev.key;if(k!=="ArrowLeft"&&k!=="ArrowRight")return;
 if(ev.altKey||ev.ctrlKey||ev.metaKey||ev.shiftKey||ev.defaultPrevented||typing(ev))return;
 ev.preventDefault();step(k==="ArrowRight"?1:-1)}
document.addEventListener("keydown",onKey);
try{if(parent.__ksKey)parent.document.removeEventListener("keydown",parent.__ksKey);parent.__ksKey=onKey;parent.document.addEventListener("keydown",onKey)}catch(e){}
window.__ks={show:show,pause:pause};
if(matchMedia("(prefers-reduced-motion:reduce)").matches){show(T-1)}else{show(0);setTimeout(()=>{if(!touched)start()},700)}
})();
</script></body></html>"""
