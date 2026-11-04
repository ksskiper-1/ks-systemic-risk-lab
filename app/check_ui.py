"""check_ui.py — проверки интерфейса T5 без браузера.

Что делает:
  1. Запускает app.py целиком на заглушке Streamlit (st.* — минимальные no-op), перехватывает HTML фрейма.
  2. Блок R (шаг 1): карточка «Режим передачи стресса» — ρ и доля насыщенных банков показаны отдельно,
     значения совпадают с contagion.spectral_radius / saturated_share при s_ref протокола и текущих α, R;
     нет бинарной подписи только по ρ; формулы не продублированы в app.py / viz.py.
  3. Блок V (шаг 2): JS графа выполняется в Node на заглушке DOM. Для каждого шага t и банка i
     спасённый банк с ratio >= 1 не должен выглядеть безопасным: класс узла "saved risk",
     кольцо "hi brink", статус в подсказке «снова на грани», строка «Потеряно капитала».
     Пример из аудита: topo 0, сеть 0, seed 2026, общий шок 5%, поддержка; банки 14 и 17.
  4. Блок J: клик по банку (кнопка pick_i в parent), стрелки ←/→ (не листают при вводе), кнопки «← Назад» /
     «Вперёд →» (недоступны на первом / последнем шаге), высота фрейма = app.FRAME_H.
  4a. Блок T: короткая подпись, свёрнутый блок «О модели» (протокол, seed, номер сети), «Демонстрационные сценарии».
  5. Блок S (шаг 3): переключатель «дефолты / заражение (S)»; в режиме S помощь отключена.
Ограничение: заглушка DOM не делает раскладку и не рисует; реальный браузер не проверяется.
  6. Блоки H, C (headless Chromium): scrollHeight <= FRAME_H; карточка ρ наверху правой панели; цвет обводки
     спасённого банка после CSS-перехода; клик, наведение, стрелки. По умолчанию — ускоренный набор
     (4 истории + 2 сценария × 5 ширин); полный перебор (100 сценариев × 5 ширин): python check_ui.py --full-height
Код выхода: 0 — всё прошло, 1 — есть ошибки, 2 — нет Node или Chromium (не проверено).
"""
import os, re, sys, json, types, shutil, subprocess, tempfile, contextlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
sys.dont_write_bytecode = True

FAIL = []
def ok(cond, msg):
    print(("  [ok] " if cond else "  [FAIL] ") + msg)
    if not cond: FAIL.append(msg)


# ---------------------------------------------------------------- заглушка Streamlit
class _Stop(Exception): pass

class _State(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)
    def __setattr__(self, k, v): self[k] = v

def make_streamlit(state, sink):
    st = types.ModuleType("streamlit")
    st.session_state = state
    st.context = types.SimpleNamespace(theme=types.SimpleNamespace(type="dark"))
    noop = lambda *a, **k: None
    for n in ("set_page_config", "markdown", "caption", "progress", "info", "write"):
        setattr(st, n, noop)
    st.warning = lambda text, *a, **k: sink.setdefault("warnings", []).append(str(text))
    def cache_data(fn=None, **kw):
        return fn if fn is not None else (lambda f: f)
    st.cache_data = cache_data
    def _val(key, default):
        if key is not None and key in state: return state[key]
        if key is not None: state[key] = default
        return default
    st.button = lambda label, key=None, **k: False
    def _dis(key, k): sink.setdefault("disabled", {})[key] = bool(k.get("disabled", False))
    def _lab(label): sink.setdefault("labels", []).append(str(label))
    def slider(label, mn=None, mx=None, value=None, step=None, key=None, **k):
        _lab(label); _dis(key, k); return _val(key, mn if value is None else value)
    st.slider = slider
    def selectbox(label, options, key=None, format_func=str, **k):
        _lab(label); sink.setdefault("labels", []).extend(str(format_func(o)) for o in options); return _val(key, list(options)[0])
    st.selectbox = selectbox
    def number_input(label, key=None, min_value=0, **k):
        _lab(label); return _val(key, min_value)
    st.number_input = number_input
    st.button = lambda label, key=None, **k: (_lab(label), False)[1]
    def checkbox(label, key=None, value=False, **k):
        _lab(label); _dis(key, k); return _val(key, value)
    st.checkbox = checkbox
    st.toggle = lambda label, key=None, value=False, **k: _val(key, value)
    def segmented_control(label, options, key=None, disabled=False, format_func=str, **k):
        sink.setdefault("seg", {})[key] = dict(label=label, disabled=disabled, options=list(options),
                                               labels=[str(format_func(o)) for o in options])
        return state.get(key)
    st.segmented_control = segmented_control
    def caption(text, *a, **k): sink.setdefault("captions", []).append(str(text))
    st.caption = caption
    def markdown(text, *a, **k): sink.setdefault("md", []).append(str(text))
    st.markdown = markdown
    @contextlib.contextmanager
    def ctx(*a, **k): yield _Col()
    class _Col:
        def __getattr__(self, n): return getattr(st, n)
        def __enter__(self): return self
        def __exit__(self, *a): return False
    st.container = ctx; st.expander = ctx
    st.columns = lambda spec, **k: [_Col() for _ in range(spec if isinstance(spec, int) else len(spec))]
    def iframe(html, height=None, **k):
        if "html" in sink: sink.setdefault("frames", []).append((sink["html"], sink["height"]))
        sink["html"] = html; sink["height"] = height
    st.iframe = iframe
    def stop(): raise _Stop()
    st.stop = stop
    return st

def run_app(**cfg):
    """Выполнить app.py с заданным состоянием; вернуть словарь с HTML фрейма, высотой и сегментами."""
    sec = cfg.get("section", "sim")
    state = _State(section=sec, _last_section=sec)
    state.update(cfg.get("extra_state", {}))
    if cfg.get("story"):
        state["story"] = cfg["story"]
    for k in ("topo", "mech", "shock", "view"):
        if k in cfg: state[k] = cfg[k]; state[f"_last_{k}"] = cfg[k]
    shock = cfg.get("shock", "one")
    state[f"s_{shock}"] = cfg.get("s", 10.0 if shock == "one" else 6.0)
    state["bank"] = cfg.get("bank", 0); state["net_id"] = cfg.get("net", 1)
    state["alpha"] = cfg.get("alpha", 0.5); state["R"] = cfg.get("R", 0.4)
    state["proto"] = cfg.get("proto", True); state["Gabs"] = 25.0
    sink = {}
    sys.modules["streamlit"] = make_streamlit(state, sink)
    for m in ("hypothesis", "hyp_page", "hyp_view"):
        sys.modules.pop(m, None)
    src = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    g = {"__name__": "__ks_app__", "__file__": os.path.join(HERE, "app.py")}
    try:
        exec(compile(src, "app.py", "exec"), g)
    except _Stop:
        pass
    sink["state"] = state; sink["g"] = g
    return sink


# ---------------------------------------------------------------- Node-заглушка DOM
JS_HARNESS = r"""
const fs=require('fs');const html=fs.readFileSync(process.argv[2],'utf8');const plan=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const m=html.match(/<script>([\s\S]*)<\/script><\/body>/);if(!m){console.log(JSON.stringify({error:'no script'}));process.exit(0)}
const code=m[1];
function mkEl(tag){const e={tagName:String(tag).toUpperCase(),attrs:{},children:[],style:{},dataset:{},_h:{},textContent:'',_html:'',
 setAttribute(k,v){this.attrs[k]=String(v)},getAttribute(k){return this.attrs[k]},
 appendChild(c){this.children.push(c);return c},
 addEventListener(t,f){(this._h[t]=this._h[t]||[]).push(f)},removeEventListener(){},
 fire(t,ev){(this._h[t]||[]).forEach(f=>f(ev||{}))},
 querySelectorAll(){return[]},querySelector(){return null},
 getBoundingClientRect(){return{left:0,top:0,width:600,height:600}},offsetHeight:100};
 Object.defineProperty(e,'className',{get(){return e.attrs['class']||''},set(v){e.attrs['class']=String(v)}});
 Object.defineProperty(e,'innerHTML',{get(){return e._html},set(v){e._html=String(v)}});
 e.classList={_s(){return new Set((e.attrs['class']||'').split(/\s+/).filter(Boolean))},
  _w(s){e.attrs['class']=[...s].join(' ')},
  add(c){const s=this._s();s.add(c);this._w(s)},remove(c){const s=this._s();s.delete(c);this._w(s)},
  toggle(c,f){const s=this._s();const on=f===undefined?!s.has(c):!!f;on?s.add(c):s.delete(c);this._w(s);return on},
  contains(c){return this._s().has(c)}};
 return e}
const ids={};const byId=id=>ids[id]||(ids[id]=mkEl('div'));const q={};
const docH={};
const document={getElementById:byId,querySelector:s=>q[s]||(q[s]=mkEl('div')),querySelectorAll:()=>[],
 createElementNS:(ns,t)=>mkEl(t),createElement:t=>mkEl(t),addEventListener(t,f){(docH[t]=docH[t]||[]).push(f)},removeEventListener(){}};
const clicks=[];const pbtn={};
const pdoc={documentElement:mkEl('html'),head:mkEl('head'),createElement:t=>mkEl(t),
 querySelector(s){const mm=s.match(/^\.st-key-pick_(\d+) button$/);if(mm&&plan.pick){const i=+mm[1];return pbtn[i]||(pbtn[i]={click(){clicks.push(i)}})}return null},
 addEventListener(){},removeEventListener(){}};
const parent={document:pdoc};const window={};
const timers=[];
const fn=new Function('window','document','parent','matchMedia','setTimeout','setInterval','clearInterval',code);
fn(window,document,parent,()=>({matches:true}),(f)=>{timers.push(f);return 1},()=>2,()=>{});
const out={T:0,steps:[],keys:[],clicks:[]};
const g=byId('g');const nodes=g.children.filter(c=>c.tagName==='G');
out.T=window.__ks?1:0;
const tip=byId('tip');
for(const t of plan.ts){window.__ks.show(t);const row=[];
 nodes.forEach((nd,i)=>{nd.fire('pointerenter',{clientX:10,clientY:10});
  row.push({node:nd.attrs['class'],ring:nd.children[1].attrs['class'],fill:nd.children[0].style.fill||'',tip:tip.innerHTML})});
 out.steps.push(row);(out.panel=out.panel||[]).push({sNow:byId('sNow').textContent,satNow:byId('satNow').textContent,
  stepNow:byId('stepNow').textContent,cap:byId('cap').textContent})}
out.wv=byId('waves').innerHTML;
if(plan.keys){window.__ks.show(0);const ev=k=>({key:k,target:{tagName:'BODY'},preventDefault(){}});
 const capEl=byId('cap');
 for(const k of plan.keys){(docH.keydown||[]).forEach(f=>f(ev(k)));out.keys.push(capEl.textContent)}}
if(plan.nav){const P0=byId('prev'),N0=byId('next'),capEl=byId('cap');const r=[];
 const cl=e=>{if(typeof e.onclick==='function'&&!e.disabled)e.onclick()};   // как браузер: недоступная кнопка не нажимается
 const P_={get disabled(){return P0.onclick?P0.disabled:'нет кнопки'},onclick(){cl(P0)}},N_={get disabled(){return N0.onclick?N0.disabled:'нет кнопки'},onclick(){cl(N0)}};
 const snap=()=>r.push({cap:capEl.textContent,p:P_.disabled===true,n:N_.disabled===true});
 window.__ks.show(0);snap();N_.onclick();snap();P_.onclick();snap();P_.onclick();snap();
 for(let i=0;i<60;i++)N_.onclick();snap();N_.onclick();snap();P_.onclick();snap();
 const kd=(k,tg,mod)=>(docH.keydown||[]).forEach(f=>f(Object.assign({key:k,target:tg,preventDefault(){}},mod||{})));
 window.__ks.show(1);snap();
 kd('ArrowRight',{tagName:'INPUT'});snap();
 kd('ArrowRight',{tagName:'TEXTAREA'});snap();
 kd('ArrowLeft',{tagName:'DIV',closest:q=>/role="slider"/.test(q)?{}:null});snap();
 kd('ArrowLeft',{tagName:'DIV',closest:q=>/role="spinbutton"/.test(q)?{}:null});snap();
 kd('ArrowRight',{tagName:'BODY',closest:()=>null},{altKey:true});snap();
 kd('ArrowRight',{tagName:'BODY',closest:()=>null});snap();
 kd('ArrowLeft',{tagName:'BUTTON',closest:()=>null});snap();
 out.nav=r}
if(plan.pick){nodes[plan.pick_i].fire('click',{});out.clicks=clicks.slice();
 nodes[plan.pick_i].fire('pointerenter',{clientX:10,clientY:10});out.pick_tip=tip.innerHTML;out.pick_cls=nodes[plan.pick_i].attrs['class']}
console.log(JSON.stringify(out));
"""

NODE = shutil.which("node")

def run_js(html, ts, keys=None, pick_i=None, nav=False):
    with tempfile.TemporaryDirectory() as d:
        hp, pp, jp = (os.path.join(d, n) for n in ("p.html", "plan.json", "h.js"))
        open(hp, "w", encoding="utf-8").write(html)
        json.dump(dict(ts=list(ts), keys=keys, pick=pick_i is not None, pick_i=pick_i, nav=nav), open(pp, "w"))
        open(jp, "w").write(JS_HARNESS)
        r = subprocess.run([NODE, jp, hp, pp], capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("node: " + r.stderr[-800:])
    return json.loads(r.stdout.strip().splitlines()[-1])


# ---------------------------------------------------------------- headless Chromium
def find_chrome():
    import glob
    c = os.environ.get("KS_CHROME")
    if c and os.path.exists(c): return c
    for n in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        w = shutil.which(n)
        if w: return w
    g = sorted(glob.glob(os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")))
    return g[-1] if g else None

CHROME = find_chrome()

CH_HARNESS = r"""<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<div id="btns"></div><script id="P" type="application/json">__P__</script>
<script>
const P=JSON.parse(document.getElementById('P').textContent);const clicks=[];
for(let i=0;i<25;i++){const d=document.createElement('div');d.className='st-key-pick_'+i;const b=document.createElement('button');
 b.onclick=()=>clicks.push(i);d.appendChild(b);document.getElementById('btns').appendChild(d)}
function load(fr,html){return new Promise(r=>{fr.onload=()=>setTimeout(r,30);fr.srcdoc=html})}
function steps(win,doc,f){for(let t=0;t<80;t++){try{win.__ks.show(t)}catch(e){break}f(t)}}
(async()=>{const out={h:[],inter:{}};
 const fr=document.createElement('iframe');fr.style.border='0';fr.style.display='block';fr.height=P.fh;document.body.appendChild(fr);
 for(const w of P.widths){fr.style.width=w+'px';fr.style.height=P.fh+'px';
  for(const p of P.pages){await load(fr,p.html);const d=fr.contentDocument,win=fr.contentWindow;win.__ks.pause();
   d.querySelectorAll('details').forEach(x=>x.open=true);   // раскрывающихся блоков на экране больше нет (финал T5); оставлено на случай их возврата
   let mx=0,mr=0,ml=0,mc=0;steps(win,d,()=>{mx=Math.max(mx,d.documentElement.scrollHeight);
     mc=Math.max(mc,Math.ceil(d.querySelector('.layout').getBoundingClientRect().bottom+win.scrollY));
     mr=Math.max(mr,d.querySelector('.right').getBoundingClientRect().bottom);ml=Math.max(ml,d.querySelector('.left').getBoundingClientRect().bottom)});
   const rg=d.querySelector('.right .rg'),first=d.querySelector('.right').firstElementChild,nxt=rg&&rg.nextElementSibling;
   const bar=d.querySelector('.bar').getBoundingClientRect(),sv=d.getElementById('g').getBoundingClientRect();
   out.h.push({name:p.name,w:w,h:mx,content:mc,right:Math.round(mr),left:Math.round(ml),cols:getComputedStyle(d.querySelector('.layout')).gridTemplateColumns.split(' ').length,
    rgFirst:first===rg,rgTop:rg?Math.round(rg.getBoundingClientRect().top):null,rgBottom:rg?Math.round(rg.getBoundingClientRect().bottom):null,
    nextTop:nxt?Math.round(nxt.getBoundingClientRect().top):null,graphTop:Math.round(sv.top),barBottom:Math.round(bar.bottom),
    nav:['prev','next'].map(id=>{const b=d.getElementById(id);if(!b)return null;const q=b.getBoundingClientRect(),lc=d.querySelector('.left').getBoundingClientRect(),cs=getComputedStyle(b);
     return {w:Math.round(q.width),h:Math.round(q.height),inLeft:q.left>=lc.left-1&&q.right<=lc.right+1,top:Math.round(q.top),vis:cs.visibility==='visible'&&cs.display!=='none'&&+cs.opacity>0,
      text:b.textContent,hit:(()=>{const e=d.elementFromPoint(q.left+q.width/2,q.top+q.height/2);return e===b||b.contains(e)})()}})})}}
 const I=P.inter;fr.style.width=I.w+'px';
 // спасённый банк на грани: настоящий CSS
 await load(fr,I.audit);{const d=fr.contentDocument,win=fr.contentWindow;win.__ks.pause();win.__ks.show(1);
  await new Promise(r=>setTimeout(r,100));
  // при --virtual-time-budget часы CSS-анимаций headless Chromium не идут (currentTime = 0), поэтому переход
  // завершается штатно Animation.finish(): computed style = конечное значение перехода; длительность фиксируется
  const durs=[];for(const i of I.risk){const b=d.querySelectorAll('#g g.node')[i].querySelector('circle.body');
   b.getAnimations().forEach(a=>{if(a.transitionProperty){durs.push(a.effect.getTiming().duration);a.finish()}})}
  const g=d.querySelectorAll('#g g.node');const res=[];
  for(const i of I.risk){const b=g[i].querySelector('circle.body'),cs=getComputedStyle(b),ring=g[i].querySelectorAll('circle')[1];
   res.push({i,cls:g[i].getAttribute('class'),fill:cs.fill,stroke:cs.stroke,dash:cs.strokeDasharray,ring:ring.getAttribute('class'),anim:getComputedStyle(ring).animationName})}
  const ref=d.createElement('div');ref.style.color='var(--green)';d.body.appendChild(ref);const green=getComputedStyle(ref).color;
  ref.style.color='var(--red)';const red=getComputedStyle(ref).color;out.inter.risk={res,green,red,durs}}
 // клик, наведение, стрелки
 await load(fr,I.click);{const d=fr.contentDocument,win=fr.contentWindow;win.__ks.pause();
  const g=d.querySelectorAll('#g g.node')[I.i];const c=g.querySelector('circle.body').getBoundingClientRect();
  const cx=c.left+c.width/2,cy=c.top+c.height/2;const hit=d.elementFromPoint(cx,cy);
  out.inter.hit=!!(hit&&g.contains(hit));
  g.dispatchEvent(new PointerEvent('pointerenter',{clientX:cx,clientY:cy,bubbles:false}));
  const tip=d.getElementById('tip'),tr=tip.getBoundingClientRect(),wr=d.querySelector('.wrap').getBoundingClientRect();
  out.inter.tip={on:tip.classList.contains('on'),text:tip.textContent,pick:g.classList.contains('pick'),cursor:getComputedStyle(g).cursor,
   inside:tr.left>=wr.left-1&&tr.right<=wr.right+1&&tr.top>=wr.top-1,w:Math.round(tr.width),h:Math.round(tr.height)};
  g.dispatchEvent(new PointerEvent('pointerleave',{bubbles:false}));out.inter.tipOff=!tip.classList.contains('on');
  g.dispatchEvent(new MouseEvent('click',{bubbles:true,clientX:cx,clientY:cy}));out.inter.clicks=clicks.slice();
  const cap=d.getElementById('cap');win.__ks.show(0);const caps=[cap.textContent];
  const key=(doc,k)=>doc.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true}));
  key(d,'ArrowRight');caps.push(cap.textContent);key(document,'ArrowRight');caps.push(cap.textContent);
  key(d,'ArrowLeft');caps.push(cap.textContent);
  const inp=d.createElement('input');d.body.appendChild(inp);inp.focus();
  inp.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));caps.push(cap.textContent);
  out.inter.caps=caps;
  // кнопки «← Назад» / «Вперёд →» настоящими кликами и клавиши из полей родительской страницы (как в Streamlit)
  const pv=d.getElementById('prev'),nx=d.getElementById('next'),nv=[];const sn=()=>nv.push({cap:cap.textContent,p:pv.disabled,n:nx.disabled});
  win.__ks.show(0);sn();pv.click();sn();nx.click();sn();for(let i=0;i<60;i++)nx.click();sn();nx.click();sn();pv.click();sn();
  const r1=nx.getBoundingClientRect();win.__ks.show(0);d.elementFromPoint(r1.left+r1.width/2,r1.top+r1.height/2).click();sn();
  const mk=(tag,attrs)=>{const e=document.createElement(tag);for(const k in attrs)e.setAttribute(k,attrs[k]);document.body.appendChild(e);return e};
  const fields=[mk('input',{type:'number'}),mk('textarea',{}),mk('div',{role:'slider',tabindex:'0'}),mk('div',{role:'radiogroup',tabindex:'0'})];
  const inner=document.createElement('span');fields[2].appendChild(inner);
  win.__ks.show(1);const before=cap.textContent;const pk=[];
  for(const f of [...fields,inner]){f.focus&&f.focus();for(const k of ['ArrowRight','ArrowLeft'])f.dispatchEvent(new KeyboardEvent('keydown',{key:k,bubbles:true,cancelable:true}));pk.push(cap.textContent===before)}
  document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true,cancelable:true}));pk.push(cap.textContent!==before);
  out.inter.nav={nv,pk}}
 if(I.S){await load(fr,I.S);const d=fr.contentDocument,win=fr.contentWindow;win.__ks.pause();
  const nx=d.getElementById('next'),pv=d.getElementById('prev');
  const vis=sel=>{const e=d.querySelector(sel);return !!e&&getComputedStyle(e).display!=='none'};
  win.__ks.show(0);const pan=()=>({sNow:d.getElementById('sNow').textContent,cap:d.getElementById('cap').textContent,p:pv.disabled,n:nx.disabled});
  const seq=[pan()];for(let i=0;i<40;i++){nx.click();seq.push(pan())}pv.click();seq.push(pan());
  // цвета узлов на последнем шаге после завершения CSS-переходов
  win.__ks.show(I.St);await new Promise(r=>setTimeout(r,60));
  d.querySelectorAll('#g g.node circle.body').forEach(b=>b.getAnimations().forEach(a=>a.finish()));
  const ref=d.createElement('div');d.body.appendChild(ref);const col=v=>{ref.style.color=v;return getComputedStyle(ref).color};
  const fills=[...d.querySelectorAll('#g g.node')].map(g=>({cls:g.getAttribute('class'),fill:getComputedStyle(g.querySelector('circle.body')).fill}));
  const g3=d.querySelectorAll('#g g.node')[I.Si],c=g3.querySelector('circle.body').getBoundingClientRect();
  g3.dispatchEvent(new PointerEvent('pointerenter',{clientX:c.left+c.width/2,clientY:c.top+c.height/2,bubbles:false}));
  const tip=d.getElementById('tip');
  out.inter.S={seq,fills,red:col('var(--red)'),node:col('var(--node)'),legS:vis('.legend.ldS'),legD:vis('.legend.ldD'),
   noteS:vis('.ringnote.ldS'),noteD:vis('.ringnote.ldD'),tip:tip.textContent,tipOn:tip.classList.contains('on'),wt:d.querySelector('#waves .wt').textContent}}
 document.body.setAttribute('data-out',JSON.stringify(out));
})().catch(e=>document.body.setAttribute('data-out',JSON.stringify({error:String(e&&e.stack||e)})));
</script></body></html>"""

def run_chrome(pages, widths, inter, fh, budget_ms=120000):
    """Один запуск headless Chromium: высоты всех pages при всех widths + проверки взаимодействия."""
    import html as _h
    P = json.dumps(dict(pages=[dict(name=n, html=h) for n, h in pages], widths=widths, inter=inter, fh=fh), ensure_ascii=False)
    P = P.replace("</", "<\\/")
    with tempfile.TemporaryDirectory() as d:
        hp = os.path.join(d, "h.html")
        open(hp, "w", encoding="utf-8").write(CH_HARNESS.replace("__P__", P))
        r = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=2000,1100", f"--virtual-time-budget={budget_ms}", "--dump-dom", "file://" + hp],
                           capture_output=True, text=True, timeout=300)
    m = re.search(r'data-out="([^"]*)"', r.stdout)
    if not m:
        raise RuntimeError("Chromium не вернул результат; stderr: " + r.stderr[-600:])
    return json.loads(_h.unescape(m.group(1)))


def trace_data(html):
    m = re.search(r"const D=(\{.*?\});const NS=", html, re.S)
    return json.loads(m.group(1))


# ---------------------------------------------------------------- блок R: ρ и доля насыщенных
def block_R():
    print("Блок R: ρ и доля насыщенных банков (шаг 1)")
    from engine import gen_net, mech_setup
    import contagion as C
    from run_S_sweep import S_REF
    ok(abs(S_REF - 0.01) < 1e-15, f"s_ref протокола = {S_REF}")
    cfgs = [dict(topo=t, mech=m, net=n, alpha=a, R=R) for t in (0, 1) for m in ("none", "res", "sup")
            for (n, a, R) in ((1, 0.5, 0.4), (0, 0.3, 0.2), (7, 0.6, 0.6))]
    # малые α (вариант A, T5): здесь доля насыщенных при s_ref = 0,01 и 0,02 различается, поэтому подмена s_ref видна
    cfgs += [dict(topo=0, mech="none", net=1, alpha=0.1, R=0.2), dict(topo=0, mech="none", net=1, alpha=0.1, R=0.6),
             dict(topo=0, mech="res", net=1, alpha=0.1, R=0.2)]
    seen_rho = set(); n_diff = 0
    for c in cfgs:
        out = run_app(shock="all", s=6.0, **c)
        html = out["html"]
        E, A, Kb = gen_net(c["topo"], c["net"], N=25, alpha=c["alpha"], base=2026)
        K, _, _ = mech_setup(c["mech"], Kb, A, None, None)
        rho = C.spectral_radius(E, K, c["R"])
        try: k_sat = f"{int(round(C.saturated_share(E, A, K, c['R'], s_ref=S_REF) * 25))} из 25"
        except RuntimeError: k_sat = "—"
        try: k_sat02 = f"{int(round(C.saturated_share(E, A, K, c['R'], s_ref=0.02) * 25))} из 25"
        except RuntimeError: k_sat02 = "—"
        n_diff += k_sat != k_sat02
        i0 = html.find("Режим передачи стресса")
        ends = [j for j in (html.find('<div class="story">', i0), html.find('<div class="sec-title">', i0)) if j > 0]
        card = html[i0: min(ends)]   # карточка ρ — первый блок панели (T5): до истории или «Этот шок»
        nums = re.findall(r'<div class="num">([^<]*)</div><div class="lbl">([^<]*)', card)
        exp_rho = f"{rho:.2f}".replace(".", ",")
        tag = f"topo={c['topo']} mech={c['mech']} net={c['net']} α={c['alpha']} R={c['R']}"
        ok(i0 > 0 and len(nums) == 2, f"{tag}: карточка есть, в ней два отдельных показателя")
        if len(nums) == 2:
            ok(nums[0][0] == exp_rho and "ρ" in nums[0][1], f"{tag}: ρ = {nums[0][0]} (contagion: {exp_rho})")
            ok(nums[1][0] == k_sat and "h ≈ 1" in nums[1][1] and "1%" in card,
               f"{tag}: насыщены {nums[1][0]} (contagion при S_REF: {k_sat}; при 0,02: {k_sat02}), шок 1%")
        ok("при больших α насыщение всех банков ожидаемо" in card, f"{tag}: пояснение о больших и малых α")
        ok("ρ &lt; 1" in card and "ρ &gt; 1" in card and "h ≈ 1" in card, f"{tag}: пометка ρ<1 / ρ>1 и насыщение по h ≈ 1")
        bad = [w for w in ("стабильн", "безопасн", "опасн", "устойчив", "критич") if w in card.lower()]
        ok(not bad, f"{tag}: нет бинарной подписи по ρ {bad if bad else ''}")
        seen_rho.add(exp_rho)
    ok(n_diff >= 1, f"различающая сила: в {n_diff} конфигурациях доля при S_REF отличается от доли при 0,02")
    ok(len(seen_rho) > 3, f"ρ меняется вместе с α, R, механизмом: {len(seen_rho)} разных значений")
    for f in ("app.py", "viz.py"):
        s = open(os.path.join(HERE, f), encoding="utf-8").read()
        dup = [w for w in ("eigvals", "np.linalg", "SAT_TOL", "1e-9") if w in s]
        ok(not dup, f"{f}: формулы ρ / насыщения не продублированы {dup if dup else ''}")
    s = open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
    ok("spectral_radius(" in s and "saturated_share(" in s and "S_REF" in s, "app.py вызывает contagion.spectral_radius / saturated_share с S_REF")


# ---------------------------------------------------------------- блок V: спасённый банк на грани
def check_rings(html, tag, need=None):
    D = trace_data(html)
    T = len(D["steps"])
    res = run_js(html, range(T))
    n_risk = n_safe = 0
    errs = []
    for t in range(T):
        dead = set(sum(D["steps"][: t + 1], [])); saved = set(sum(D["rescued"][: t + 1], []))
        for i in range(D["N"]):
            r = D["ratios"][t][i]; row = res["steps"][t][i]
            node = set(row["node"].split()); ring = set(row["ring"].split()); tip = row["tip"]
            if i in dead:
                continue
            if i in saved and r >= 1:
                n_risk += 1
                if not ({"saved", "risk"} <= node): errs.append(f"t={t} банк {i}: класс узла «{row['node']}» (ожидался saved risk)")
                if not ({"hi", "brink"} <= ring) or "off" in ring: errs.append(f"t={t} банк {i}: кольцо «{row['ring']}» (ожидалось hi brink)")
                if "снова на грани" not in tip: errs.append(f"t={t} банк {i}: в подсказке нет «снова на грани»")
                if "Потеряно капитала" not in tip or "весь, на грани" not in tip: errs.append(f"t={t} банк {i}: в подсказке нет потерянной доли")
            elif i in saved:
                n_safe += 1
                if "risk" in node or "saved" not in node: errs.append(f"t={t} банк {i}: класс узла «{row['node']}» (ожидался saved)")
                if "off" not in ring: errs.append(f"t={t} банк {i}: кольцо «{row['ring']}» (ожидалось off)")
                if "спасён поддержкой" not in tip or "Потеряно капитала" not in tip: errs.append(f"t={t} банк {i}: подсказка спасённого")
            else:
                if "saved" in node or "risk" in node: errs.append(f"t={t} банк {i}: неспасённый с классом «{row['node']}»")
    ok(not errs, f"{tag}: узлы/кольца/подсказки согласованы с данными trace ({n_risk} случаев «спасён, на грани», {n_safe} «спасён, безопасен»)"
       + ("" if not errs else "\n         " + "\n         ".join(errs[:6])))
    if need:
        for (t, i) in need:
            row = res["steps"][t][i]
            ok("risk" in row["node"].split() and "brink" in row["ring"].split() and "снова на грани" in row["tip"],
               f"{tag}: t={t} банк {i}: узел «{row['node']}», кольцо «{row['ring']}», подсказка «снова на грани»")
    return n_risk, n_safe

def block_V():
    print("Блок V: спасённый банк, которому снова угрожает дефолт (шаг 2)")
    out = run_app(topo=0, mech="sup", shock="all", s=5.0, net=0)
    D = trace_data(out["html"])
    ok(D["rescued"] == [[], [17, 14], [], []] or [sorted(x) for x in D["rescued"]] == [[], [14, 17], [], []],
       f"пример аудита: спасения по волнам {D['rescued']}")
    ok(all(D["ratios"][1][i] >= 1 for i in (14, 17)), f"пример аудита: на шаге 1 ratio банков 14, 17 = "
       f"{[round(D['ratios'][1][i], 3) for i in (14, 17)]} (≥ 1)")
    ok(all(i in D["steps"][2] for i in (14, 17)), "пример аудита: банки 14, 17 падают на шаге 2")
    check_rings(out["html"], "аудит topo0 сеть0 общий 5% поддержка", need=[(1, 14), (1, 17)])
    tot_r = tot_s = 0
    for topo in (0, 1):
        for net in range(6):
            for shock, s in (("all", 4.0), ("all", 6.0), ("one", 10.0)):
                out = run_app(topo=topo, mech="sup", shock=shock, s=s, net=net, bank=net % 25)
                D = trace_data(out["html"])
                if not any(D["rescued"]): continue
                r, sf = check_rings(out["html"], f"topo{topo} сеть{net} {shock} {s}%")
                tot_r += r; tot_s += sf
    ok(tot_r > 0 and tot_s > 0, f"перебор покрывает оба случая: «на грани» {tot_r}, «безопасен» {tot_s}")


# ---------------------------------------------------------------- блок J: клик, стрелки, высота
def block_J():
    print("Блок J: клик по банку, стрелки, высота фрейма")
    out = run_app(topo=0, mech="none", shock="one", s=10.0, net=1, bank=0)
    fh = out["g"]["FRAME_H"]
    ok(out["height"] == fh, f"высота фрейма, переданная в st.iframe, = FRAME_H = {fh}")
    D = trace_data(out["html"]); T = len(D["steps"])
    res = run_js(out["html"], [], keys=["ArrowRight"] * (T + 1) + ["ArrowLeft"], pick_i=3)
    caps = res["keys"]
    last = D["captions"][T - 1]
    ok(caps[:T - 2] == D["captions"][1:T - 1] and all(c.startswith(last + " — итого") for c in caps[T - 2:T + 1])
       and caps[-1] == D["captions"][T - 2],
       f"стрелки: → проходит {T} шагов и останавливается на последнем, ← возвращает на шаг назад")
    ok(res["clicks"] == [3], f"клик по банку 3 нажимает кнопку pick_3 ({res['clicks']})")
    C_ = D["captions"]; fin = lambda c: c.startswith(C_[T - 1] + " — итого")
    nv = run_js(out["html"], [], nav=True)["nav"]
    ok(nv[0]["cap"] == C_[0] and nv[0]["p"] and not nv[0]["n"], "шаг 0: «← Назад» недоступна, «Вперёд →» доступна")
    ok(nv[1]["cap"] == C_[1] and not nv[1]["p"] and not nv[1]["n"], "«Вперёд →»: шаг 0 → 1, обе кнопки доступны")
    ok(nv[2]["cap"] == C_[0] and nv[2]["p"], "«← Назад»: шаг 1 → 0, «← Назад» снова недоступна")
    ok(nv[3]["cap"] == C_[0], "«← Назад» на шаге 0 ничего не делает")
    ok(fin(nv[4]["cap"]) and nv[4]["n"] and not nv[4]["p"], f"«Вперёд →» доходит до последнего шага {T - 1} и становится недоступной")
    ok(fin(nv[5]["cap"]), "«Вперёд →» на последнем шаге ничего не делает")
    ok(nv[6]["cap"] == C_[T - 2] and not nv[6]["n"], "«← Назад» с последнего шага: шаг назад, «Вперёд →» снова доступна")
    base = nv[7]["cap"]
    ok(base == C_[1], "исходная точка проверки клавиш: шаг 1")
    for k, what in ((8, "INPUT"), (9, "TEXTAREA"), (10, "role=slider (ползунок Streamlit)"), (11, "role=spinbutton (числовое поле)"), (12, "Alt+→")):
        ok(nv[k]["cap"] == base, f"клавиша-стрелка при фокусе {what} не листает каскад")
    ok(nv[13]["cap"] == C_[2], "→ на странице листает вперёд (шаг 1 → 2)")
    ok(nv[14]["cap"] == C_[1], "← при фокусе на кнопке листает назад (шаг 2 → 1)")
    ok("Клик: ударить шоком" in res["pick_tip"] and "pick" in res["pick_cls"].split(), "подсказка о клике и курсор-указатель при наличии кнопки")


# ---------------------------------------------------------------- блок T: тексты
# Финал T5: на пользовательских экранах нет технических подписей (протоколы, версии, имена файлов, seed),
# блока «О модели» и подписи про синтетическую сеть. Описание данных и протоколов остаётся в README и документации.
BANNED = re.compile(r"протокол|v1\.\d|seed|\b\w+\.py\b|contagion|равновесие ядра|Синтетическ|исследовательск|"
                    r"О модели|Вне диапазона|механизм модели, не реальная|details|7777|base seed", re.I)


def visible(html):
    """Текст, который видит пользователь: HTML без <style>; строки JS (подсказки, подписи) остаются, данные D вырезаны."""
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"const D=\{.*?\};const NS=", "const NS=", html, flags=re.S)


def screen_text(out):
    parts = [visible(out.get("html", ""))] + [visible(h) for h, _ in out.get("frames", [])]
    parts += out.get("captions", []) + out.get("md", []) + out.get("labels", []) + out.get("warnings", [])
    for v in out.get("seg", {}).values(): parts += [v["label"]] + v.get("labels", [])
    return "\n".join(parts)


def banned_hits(txt):
    return sorted({txt[max(0, m.start() - 30): m.end() + 15].replace("\n", " ") for m in BANNED.finditer(txt)})


def hyp_results():
    sys.modules["streamlit"] = make_streamlit({}, {})
    for m in ("hypothesis", "hyp_page", "hyp_view"): sys.modules.pop(m, None)
    import hypothesis as H
    return {mode: H.analyse(mode, n) for mode, n in (("proto", 100), ("free", 50))}


def block_T():
    print("Блок T: пользовательские тексты без технических подписей; раздел «Проверка гипотезы»")
    cfgs = [dict(view=v, topo=t, mech=m, shock=sh, s=sz, net=n, bank=0, alpha=a, story=st)
            for v in ("def", "S") for (t, m, sh, sz, n, a, st) in
            ((0, "none", "one", 10.0, 1, 0.1, None), (1, "sup", "all", 6.0, 7, 0.5, None), (0, "res", "all", 6.5, 1, 0.5, "cliff"),
             (0, "sup", "one", 10.0, 1, 0.5, "chain"), (0, "none", "one", 10.0, 1, 0.5, "all"), (1, "sup", "all", 6.0, 1, 0.5, "common"))]
    seen = dict(def_=0, S=0)
    for c in cfgs:
        for extra in ({}, {"proto": False}):
            out = run_app(**c, **extra); txt = screen_text(out)
            hits = banned_hits(txt)
            ok(not hits, f"{c['view']}, topo {c['topo']}, {c['mech']}, {c['shock']} {c['s']}%, α {c['alpha']}, сценарий {c['story']}"
               f"{', свой бюджет' if extra else ''}: нет технических подписей" + (f" {hits[:4]}" if hits else ""))
            h = out["html"]
            ok('<div class="foot">' not in h and "<details" not in h, "  нет подписи-«подвала» и раскрывающегося блока")
            seen["S" if c["view"] == "S" else "def_"] += 1
    # что должно остаться
    o = run_app(view="def", topo=0, mech="sup", shock="one", s=10.0, net=1)
    md = " ".join(o.get("md", [])); lab = o.get("labels", [])
    ok("Демонстрационные сценарии" in md and "Номер сети" in lab and "Стандартный бюджет поддержки (3% капитала)" in lab
       and "Доля межбанковских активов α" in lab and "Возврат по требованию R" in lab,
       "настройки сохранены: «Номер сети», «Стандартный бюджет поддержки (3% капитала)», α, R; «Демонстрационные сценарии»")
    ok(o["seg"]["view"]["labels"] == ["Дефолты", "Заражение (S)"], f"названия режимов {o['seg']['view']['labels']}")
    oa = run_app(view="def", topo=0, mech="none", shock="one", s=10.0, net=1, alpha=0.1)
    ok(oa["g"]["alpha"] == 0.1 and not any("α" in c_ for c_ in oa.get("captions", [])), "α = 0,1 доступна, предупреждения под ползунком нет")
    os_ = run_app(view="S", topo=0, mech="sup", shock="all", s=2.0, net=1, alpha=0.1)
    cs = " ".join(os_.get("captions", [])); h = os_["html"]
    ok("В режиме S помощь отключена" in cs and "без порога дефолта" in cs, "S: пояснение об отключённой помощи и о непрерывном заражении сохранено")
    ok("при общем шоке 1%" in h and "Режим передачи стресса" in h and "S_ind на выбранном шаге" in h and "% суммарных активов" in h,
       "S: опорная диагностика ρ (общий шок 1%) и метрика текущего шага с единицами")
    D = trace_data(h)
    ok(any("сведены в итог" in c_ for c_ in D["captions"]), "S: подпись о сведённых итерациях сохранена")
    # раздел «Проверка гипотезы»: страница и HTML результатов
    res = hyp_results()
    sys.modules.pop("hyp_page", None)
    for mode in ("proto", "free"):
        out = run_app(section="hyp", extra_state=dict(hyp_mode=mode, _last_hyp_mode=mode, hyp_res=res[mode]))
        txt = screen_text(out); hits = banned_hits(txt)
        ok("html" in out and not hits, f"«Проверка гипотезы», {mode}: нет упоминаний протоколов, версий, seed, файлов" + (f" {hits[:4]}" if hits else ""))
        seg = out.get("seg", {}).get("hyp_mode", {})
        ok(seg.get("labels") == ["Основной эксперимент", "Произвольное число сетей"], f"  переключатель: {seg.get('labels')}")
        caps = " ".join(out.get("captions", []))
        if mode == "proto":
            ok("по заранее заданному правилу: 100 → 300 → 1000" in caps,
               "  правило выбора объёма выборки описано без слова «протокол»")
            ok("Сетка основного эксперимента охватывает α от 0,3 до 0,6" in out["html"] and "не меняет вывод основного эксперимента" in out["html"]
               and "Число сетей выбрано вручную" not in out["html"], "  дополнение α = 0,1 и 0,2 описано как дополнительный расчёт")
        else:
            ok("Результат не заменяет основной эксперимент" in caps and "результат не заменяет основной эксперимент" in out["html"],
               "  ручной режим помечен «не заменяет основной эксперимент»")
        ok("на 100 пилотных сетях, отдельных от сетей основного эксперимента" in out["html"], "  порог δ: пилотные сети описаны без seed")
    return res


# ---------------------------------------------------------------- блоки H и C: headless Chromium
STORIES = {"all": dict(topo=0, mech="none", shock="one", s=10.0, bank=0, net=1),
           "chain": dict(topo=0, mech="sup", shock="one", s=10.0, bank=0, net=1),
           "common": dict(topo=1, mech="sup", shock="all", s=6.0, bank=0, net=1),
           "cliff": dict(topo=0, mech="res", shock="all", s=6.5, bank=0, net=1)}
WIDTHS = [900, 1100, 1280, 1400, 1920]
# режим S: общий шок (много итераций, насыщение), шок одного банка, шок 0 (нет заражения)
S_PAGES = {"all6": dict(topo=0, mech="sup", shock="all", s=6.0, net=1),
           "a01_all2": dict(topo=0, mech="sup", shock="all", s=2.0, net=1, alpha=0.1),
           "one10": dict(topo=0, mech="res", shock="one", s=10.0, net=1, bank=0),
           "core_one15": dict(topo=1, mech="none", shock="one", s=15.0, net=3, bank=4)}

def scenarios(full):
    """Полный перебор: 4 истории + 96 конфигураций (100). Ускоренный: 4 истории + 2 самые высокие без истории."""
    import itertools
    sc = [(f"story_{k}", dict(story=k, **v)) for k, v in STORIES.items()]
    if full:
        for topo, mech, shock, sz, net in itertools.product((0, 1), ("none", "res", "sup"), ("one", "all"),
                                                         (0.5, 6.0, 10.0, 15.0), (1, 3)):
            sc.append((f"t{topo}_{mech}_{shock}_{sz}_n{net}",
                       dict(topo=topo, mech=mech, shock=shock, s=sz, net=net, bank=4 if net == 3 else 0)))
        for topo, shock, sz, net in itertools.product((0, 1), ("one", "all"), (0.5, 6.0, 15.0), (1, 3)):
            sc.append((f"S_t{topo}_{shock}_{sz}_n{net}",
                       dict(view="S", mech="sup", topo=topo, shock=shock, s=sz, net=net, bank=4 if net == 3 else 0)))
    else:
        sc += [("t0_sup_one_0.5_n1", dict(topo=0, mech="sup", shock="one", s=0.5, net=1, bank=0)),
               ("t0_res_one_0.5_n1", dict(topo=0, mech="res", shock="one", s=0.5, net=1, bank=0))]
        sc += [(f"S_{k}", dict(view="S", **v)) for k, v in S_PAGES.items()]
    return sc

def block_HC(full=False):
    print(f"Блок H: высота содержимого фрейма в headless Chromium ({'полный перебор' if full else 'ускоренный набор'})")
    pages = [(n, run_app(**c)["html"]) for n, c in scenarios(full)]
    fh = run_app(**STORIES["all"])["g"]["FRAME_H"]
    aud = run_app(topo=0, mech="sup", shock="all", s=5.0, net=0)["html"]
    sS = run_app(view="S", **S_PAGES["a01_all2"]); DS = trace_data(sS["html"]); TS = len(DS["h"])
    r = run_chrome(pages, WIDTHS, dict(w=1280, audit=aud, risk=[14, 17], click=pages[0][1], i=3, S=sS["html"], St=TS - 1, Si=3), fh,
                   budget_ms=600000 if full else 120000)
    if "error" in r:
        ok(False, "Chromium: " + r["error"][:400]); return
    ok(len(r["h"]) == len(pages) * len(WIDTHS), f"измерено {len(r['h'])} = {len(pages)} сценариев × {len(WIDTHS)} ширин, фрейм {fh} px")
    for w in WIDTHS:
        xs = [x for x in r["h"] if x["w"] == w]; top = max(xs, key=lambda x: x["content"])
        over = [f"{x['name']} {x['h']}" for x in xs if x["h"] > fh or x["content"] > fh]
        ok(not over, f"ширина {w}: scrollHeight ≤ {fh}; высота содержимого до {top['content']} px ({top['name']}), запас {fh - top['content']} px"
           + (f"; превышение: {over[:4]}" if over else ""))
    bad = [f"{x['name']}@{x['w']}" for x in r["h"]
           if not (x["rgFirst"] and x["rgTop"] is not None and x["rgTop"] <= 40 and x["nextTop"] is not None and x["rgBottom"] <= x["nextTop"])]
    ok(not bad, "карточка ρ — первый блок правой панели, наверху фрейма (top ≤ 40 px), выше истории и «Этот шок»" + (f": {bad[:4]}" if bad else ""))
    bad = [f"{x['name']}@{x['w']}" for x in r["h"] if not (x["graphTop"] <= 40 and x["cols"] == 2)]
    ok(not bad, "граф наверху левой колонки, раскладка в две колонки на всех ширинах" + (f": {bad[:4]}" if bad else ""))
    mb = max(x["barBottom"] for x in r["h"])
    ok(mb < 900, f"шаги каскада (кнопка и точки) видны без прокрутки страницы на всех ширинах: низ панели шагов ≤ {mb} px")
    if full:
        t = max(r["h"], key=lambda x: x["content"]); mx = t["content"]
        print(f"  максимум высоты содержимого по {len(r['h'])} замерам: {mx} px ({t['name']}, ширина {t['w']}); "
              f"×1,1 = {mx * 1.1:.0f}; FRAME_H = {fh}")
    print("Блок C: взаимодействие в Chromium (не заменяет проверку в Streamlit)")
    I = r["inter"]
    red, green = I["risk"]["red"], I["risk"]["green"]
    du = I["risk"]["durs"]
    ok(len(du) > 0 and max(du) <= 1000, f"у спасённого банка идут CSS-переходы fill/stroke ({len(du)} шт., длительность ≤ {max(du) if du else '—'} мс), завершены finish()")
    for x in I["risk"]["res"]:
        ok(x["stroke"] == red and x["fill"] != green and "brink" in x["ring"] and x["anim"] == "pulse" and x["dash"] != "none",
           f"спасённый банк {x['i']} на грани после перехода: обводка {x['stroke']} (= --red {red}), заливка {x['fill']} (≠ --green), "
           f"пунктир {x['dash']}, кольцо «{x['ring']}», анимация {x['anim']}")
    ok(I["hit"], "клик в центр узла попадает в узел (elementFromPoint)")
    t = I["tip"]
    ok(t["on"] and "Банк 3" in t["text"] and "Клик: ударить шоком" in t["text"] and t["inside"],
       f"наведение: подсказка видна, внутри графа ({t['w']}×{t['h']} px), есть «Клик: ударить шоком»")
    ok(t["pick"] and t["cursor"] == "pointer", f"курсор над банком: {t['cursor']}")
    ok(I["tipOff"], "уход курсора скрывает подсказку")
    ok(I["clicks"] == [3], f"клик по банку 3 нажимает кнопку .st-key-pick_3 в родительском документе ({I['clicks']})")
    nb = [f"{x['name']}@{x['w']}" for x in r["h"] if not (x["nav"][0] and x["nav"][1] and all(
          b["w"] > 40 and 24 <= b["h"] <= 40 and b["inLeft"] and b["vis"] and b["hit"] for b in x["nav"])
          and x["nav"][0]["text"] == "← Назад" and x["nav"][1]["text"] == "Вперёд →")]
    ok(not nb, "кнопки «← Назад» и «Вперёд →» видимы, в одну строку, внутри левой колонки и не перекрыты, на всех ширинах"
       + (f": {nb[:4]}" if nb else ""))
    nv = I["nav"]["nv"]
    ok(nv[0]["p"] and not nv[0]["n"] and nv[1]["cap"] == nv[0]["cap"], "Chromium: на шаге 0 «← Назад» недоступна, клик по ней ничего не делает")
    ok(nv[2]["cap"] != nv[0]["cap"] and not nv[2]["p"], "Chromium: клик «Вперёд →» листает вперёд")
    ok(nv[3]["n"] and nv[4]["cap"] == nv[3]["cap"], "Chromium: на последнем шаге «Вперёд →» недоступна, клик ничего не делает")
    ok(nv[5]["cap"] != nv[4]["cap"] and not nv[5]["n"], "Chromium: «← Назад» с последнего шага листает назад")
    ok(nv[6]["cap"] == nv[2]["cap"], "Chromium: клик в центр кнопки «Вперёд →» (elementFromPoint) срабатывает")
    pk = I["nav"]["pk"]
    ok(all(pk[:5]), f"Chromium: стрелки в полях родительской страницы (number, textarea, role=slider, role=radiogroup, вложенный элемент ползунка) не листают каскад {pk[:5]}")
    ok(pk[5], "Chromium: стрелка на родительской странице вне полей листает каскад")
    c = I["caps"]
    ok(c[1] != c[0] and c[2] != c[1] and c[3] == c[1] and c[4] == c[3],
       "стрелки: → во фрейме, → в родительском документе, ← назад; в поле ввода стрелки не листают")
    # режим S в настоящем CSS/JS Chromium
    X = I["S"]; sq = X["seq"]; pc = lambda x: f"{x * 100:.2f}".replace(".", ",") + "%"
    ok([q["sNow"] for q in sq[:TS]] == [pc(v) for v in DS["S"]] and sq[0]["p"] and not sq[0]["n"],
       f"Chromium, S: «Вперёд →» проходит {TS} шагов, S_ind на панели = D.S шага ({sq[0]['sNow']} → {sq[TS - 1]['sNow']})")
    ok(sq[TS - 1]["n"] and sq[-2]["sNow"] == sq[TS - 1]["sNow"] and sq[-1]["sNow"] == pc(DS["S"][TS - 2]),
       "Chromium, S: на последнем шаге «Вперёд →» недоступна, «← Назад» возвращает на шаг")
    hT = DS["h"][-1]; tol = DS["sat_tol"]
    bad = [i for i, f in enumerate(X["fills"]) if (hT[i] >= 1 - tol) != ("sat" in f["cls"].split())
           or (hT[i] >= 1 - tol and f["fill"] != X["red"]) or (0.05 < hT[i] < 1 - tol and f["fill"] in (X["red"], X["node"]))
           or (hT[i] == 0 and f["fill"] != X["node"])]
    ok(not bad, f"Chromium, S: заливка узлов по h на равновесии (h ≈ 1 → --red, 0 < h < 1 → промежуточная, h = 0 → --node) {bad[:5]}")
    ok(X["legS"] and X["noteS"] and not X["legD"] and not X["noteD"], "Chromium, S: видна легенда S, легенда дефолтов скрыта")
    ok(X["tipOn"] and "Потеряно капитала, h" in X["tip"] and "Клик: ударить шоком" in X["tip"], "Chromium, S: подсказка показывает h и подсказку о клике")
    ok(X["wt"].startswith("S_ind после шага, % суммарных активов"), f"Chromium, S: подпись графика по шагам «{X['wt'][:40]}…»")


# ---------------------------------------------------------------- блок ST: пошаговая запись S против ядра
def block_ST():
    print("Блок ST: пошаговая запись непрерывного заражения (s_trace.py) против ядра contagion.py")
    import itertools
    from engine import gen_net
    import contagion as C, s_trace as T
    n = 0; errs = []; maxd = 0.0; n_cut = n_sat = 0; its = []
    for topo, net, a, R in itertools.product((0, 1), (0, 1, 3, 7), (0.1, 0.3, 0.5, 0.6), (0.2, 0.4, 0.6)):
        E, A, K = gen_net(topo, net, N=25, alpha=a, base=2026)
        M = C.M_matrix(E, K, R)
        for kind, sz in (("one", 0.02), ("one", 0.1), ("all", 0.0), ("all", 0.01), ("all", 0.05), ("all", 0.12)):
            L0 = np.zeros(25)
            if kind == "one": L0[net % 25] = sz * A[net % 25]
            else: L0 = sz * A
            tag = f"topo{topo} сеть{net} α={a} R={R} {kind} {sz}"
            try: rec = T.s_trace(E, K, A, R, L0)
            except RuntimeError as e: errs.append(f"{tag}: {e}"); continue
            n += 1
            _, Hc = C.propagate_batch(E, K, R, L0[None, :]); Sc = C.induced_S(E, K, A, R, L0[None, :])[0][0]
            if not np.array_equal(rec["h"][-1], Hc[0]): errs.append(f"{tag}: равновесие записи ≠ propagate_batch")
            if rec["S"][-1] != Sc: errs.append(f"{tag}: итоговая S_ind {rec['S'][-1]} ≠ induced_S {Sc}")
            if rec["it"][0] != 0 or rec["it"][-1] != rec["n_iter"] or rec["it"] != sorted(set(rec["it"])):
                errs.append(f"{tag}: номера итераций {rec['it']}")
            # независимый пересчёт каждой показанной итерации в форме h_k = min(1, h_0 + M h_{k-1})
            h0 = np.minimum(1.0, L0 / K); h = h0.copy(); k = 0; base = np.minimum(L0, K).sum()
            for t, it in enumerate(rec["it"]):
                while k < it:
                    hp = h; h = np.minimum(1.0, h0 + M @ h); k += 1
                d = float(np.abs(h - rec["h"][t]).max()); maxd = max(maxd, d)
                if d > 1e-10: errs.append(f"{tag}: шаг {t} (итерация {it}): |Δh| = {d:.2e}")
                Lk = L0 + (1 - R) * (E @ (hp if it > 0 else np.zeros(25)))
                S_ind = (np.minimum(Lk, K).sum() - base) / A.sum() if it > 0 else 0.0
                if abs(S_ind - rec["S"][t]) > 1e-10: errs.append(f"{tag}: шаг {t}: S_ind {rec['S'][t]} ≠ {S_ind}")
                if rec["sat"][t] != int((rec["h"][t] >= 1 - C.SAT_TOL).sum()): errs.append(f"{tag}: шаг {t}: число насыщенных")
            hs = np.array(rec["h"]); Ss = np.array(rec["S"])
            if (np.diff(hs, axis=0) < -1e-15).any() or (np.diff(Ss) < -1e-15).any() or (Ss < 0).any():
                errs.append(f"{tag}: h или S_ind убывают по шагам / S_ind < 0")
            if rec["S"][0] != 0.0: errs.append(f"{tag}: S_ind на шаге шока = {rec['S'][0]} (ожидалось 0)")
            n_cut += rec["it"][-1] - rec["it"][-2] > 1 if len(rec["it"]) > 1 else 0
            n_sat += rec["sat"][-1] > 0; its.append(rec["n_iter"])
    ok(not errs, f"{n} конфигураций: равновесие записи побитно = contagion.propagate_batch, итоговая S_ind = contagion.induced_S, "
       f"каждый показанный шаг пересчитан независимо (|Δh| ≤ {maxd:.1e}), h и S_ind не убывают"
       + ("" if not errs else "\n         " + "\n         ".join(errs[:6])))
    ok(n_cut > 0 and n_sat > 0 and n > 0 and max(its) > T.SHOW_MAX,
       f"перебор покрывает сведение хвоста итераций в итог ({n_cut}), насыщение ({n_sat}), до {max(its)} итераций")
    # несходимость не подменяется: s_trace повторяет MAXIT ядра и бросает RuntimeError
    E, A, K = gen_net(0, 1, N=25, alpha=0.5, base=2026)
    ok(T.s_trace(E, K, A, 0.4, 0.05 * A)["n_iter"] > 1, "контрольная конфигурация требует больше 1 итерации")
    old = C.MAXIT; C.MAXIT = 1
    try:
        T.s_trace(E, K, A, 0.4, 0.05 * A); ok(False, "несходимость (MAXIT = 1) не обнаружена")
    except RuntimeError: ok(True, "несходимость (MAXIT ядра) даёт RuntimeError, а не обрезанную запись")
    finally: C.MAXIT = old


# ---------------------------------------------------------------- блок S: переключатель режима
def check_S_js(h, D, tag, cov):
    pc = lambda x: f"{x * 100:.2f}".replace(".", ",") + "%"
    fm = lambda x, d: f"{x:.{d}f}".replace(".", ",")
    Tn = len(D["h"]); res = run_js(h, range(Tn)); tol = D["sat_tol"]; errs = []
    for t in range(Tn):
        P = res["panel"][t]
        if P["sNow"] != pc(D["S"][t]) or P["satNow"] != f"{D['sat'][t]} из 25" or P["cap"] != D["captions"][t]:
            errs.append(f"t={t}: панель {P}")
        for i in range(25):
            hv = D["h"][t][i]; row = res["steps"][t][i]; node = set(row["node"].split()); ring = set(row["ring"].split())
            sat = hv >= 1 - tol
            cov["sat" if sat else ("off" if hv < 0.02 else ("mid" if hv >= 0.5 else "part"))] += 1
            if ("sat" in node) != sat or "s" not in node: errs.append(f"t={t} банк {i}: класс «{row['node']}» при h = {hv:.4f}")
            exp_r = "off" if hv < 0.02 else ("hi" if sat else ("mid" if hv >= 0.5 else None))
            if (exp_r and exp_r not in ring) or (not exp_r and ring & {"off", "hi", "mid"}): errs.append(f"t={t} банк {i}: кольцо «{row['ring']}» при h = {hv:.4f}")
            if {"brink", "risk", "saved"} & (node | ring): errs.append(f"t={t} банк {i}: классы дефолтов в S")
            want = "весь (h ≈ 1)" if sat else f"{fm(hv * 100, 1)}% (h = {fm(hv, 3)})"
            if f"Потеряно капитала, h</span><b>{want}</b>" not in row["tip"]: errs.append(f"t={t} банк {i}: подсказка без h = {want}")
            if not sat and f"{round(min(hv, 1) * 85)}%" not in row["fill"]: errs.append(f"t={t} банк {i}: заливка «{row['fill']}» при h = {hv:.4f}")
    ok(not errs, f"{tag}: {Tn} шагов × 25 банков: класс, кольцо, заливка и подсказка = h_i шага; панель S_ind и насыщенных = D шага"
       + ("" if not errs else "\n         " + "\n         ".join(errs[:6])))


def block_S():
    print("Блок S: переключатель «Дефолты / Заражение (S)» (шаг 3)")
    from engine import gen_net
    import contagion as C, s_trace as T
    pc = lambda x: f"{x * 100:.2f}".replace(".", ",") + "%"
    fm = lambda x, d: f"{x:.{d}f}".replace(".", ",")
    # переключатель и отключение помощи
    out = run_app(topo=0, mech="sup", shock="all", s=6.0, net=1, view="S")
    sg = out.get("seg", {})
    ok("view" in sg and sg["view"]["options"] == ["def", "S"] and sg["view"]["label"] == "Режим" and not sg["view"]["disabled"],
       f"переключатель «Режим»: {sg.get('view', {}).get('options')}")
    ok(sg.get("mech", {}).get("disabled") is True, "в режиме S переключатель помощи заблокирован")
    caps = " ".join(out.get("captions", []))
    ok("В режиме S помощь отключена" in caps, "в режиме S есть пояснение «помощь отключена»")
    ok(out["g"].get("mech") == "none" and out["state"].get("mech") == "sup",
       f"в режиме S расчёт без помощи (mech = {out['g'].get('mech')}), выбор помощи в state сохранён ({out['state'].get('mech')})")
    dis = out.get("disabled", {})
    ok(dis.get("proto") is True, "в режиме S бюджет поддержки (checkbox proto) заблокирован")
    outg = run_app(topo=0, mech="sup", shock="all", s=6.0, net=1, view="S", proto=False)
    ok(outg.get("disabled", {}).get("Gabs") is True, "в режиме S ползунок бюджета Gabs заблокирован")
    out2 = run_app(topo=0, mech="sup", shock="all", s=6.0, net=1, view="def")
    d2 = out2.get("disabled", {})
    ok(out2["seg"]["mech"]["disabled"] is False and out2["g"]["mech"] == "sup" and d2.get("proto") is False
       and "В режиме S помощь отключена" not in " ".join(out2.get("captions", [])),
       "в режиме «Дефолты» помощь и бюджет снова доступны, выбранная помощь применяется")
    # данные S во фрейме = s_trace
    E, A, Kb = gen_net(0, 1, N=25, alpha=0.5, base=2026)
    rec = T.s_trace(E, Kb, A, 0.4, 0.06 * A)
    D = trace_data(out["html"])
    ok(D.get("mode") == "S" and D["h"] == [[float(x) for x in h] for h in rec["h"]] and D["S"] == rec["S"] and D["it"] == rec["it"],
       f"фрейм S: данные = s_trace без помощи ({len(D.get('h', []))} шагов, итераций ядра {rec['n_iter']})")
    ok('class="mS"' in out["html"] and 'class="mD"' in out2["html"], "класс режима у body: mS / mD")
    # правая панель S
    h = out["html"]; m = metrics_S_ref = C.metrics_S(E, A, Kb, "none", 0.4)
    ok(f'id="sNow">{pc(rec["S"][0])}<' in h and "S_ind на выбранном шаге" in h and "% суммарных активов" in h,
       "панель S: S_ind текущего шага с подписью и единицами (% суммарных активов)")
    ok(f"S_ind = {pc(rec['S'][-1])} активов" in h and "Итог (равновесие, " in h, f"панель S: итог равновесия {pc(rec['S'][-1])}")
    ok(f'{fm(m["A2S"], 3)}</div><div class="lbl">интегральная мера A2S' in h, f"панель S: A2S = contagion.metrics_S ({fm(m['A2S'], 3)})")
    o1 = run_app(topo=0, mech="none", shock="one", s=10.0, net=1, bank=0, view="S")
    ok(f'{fm(m["A1S"], 3)}</div><div class="lbl">интегральная мера A1S' in o1["html"], f"панель S, шок одного банка: A1S = metrics_S ({fm(m['A1S'], 3)})")
    from engine import SGRID
    curve = T.s_curve(E, Kb, A, 0.4, True)
    ok(abs(float((np.diff(SGRID) * (curve[1:] + curve[:-1]) / 2).sum()) - m["A1S"]) < 1e-12, "кривая S_ind(s) одного банка согласована с A1S ядра")
    for nm in ("интегральный масштаб каскада A", "вторичных дефолтов", "упало<br>от шока", "Доля банков, упавших"):
        ok(nm not in h, f"в режиме S нет показателя дефолтов «{nm}»")
    # карточка ρ: опорный шок 1 %, без помощи, отдельно от шага
    o3 = run_app(topo=0, mech="res", shock="all", s=6.0, net=1, view="S")
    rho = f"{C.spectral_radius(E, Kb, 0.4):.2f}".replace(".", ",")
    card = o3["html"][o3["html"].find("Режим передачи стресса"): o3["html"].find('<div class="sec-title">')]
    ok(f'<div class="num">{rho}</div>' in card and "1%" in card and 'id="' not in card,
       f"карточка ρ в S: ρ = {rho} без резервов, опорный шок 1%, не обновляется шагами (нет id)")
    # сценарии
    st_ = run_app(story="chain", view="S", topo=0, mech="sup", shock="one", s=10.0, bank=0, net=1)
    ok('<div class="story">' not in st_["html"] and "Сценарии рассчитаны на режим «Дефолты»" in " ".join(st_.get("captions", [])),
       "в S текст сценария не показан, есть пометка «рассчитаны на режим «Дефолты»»")
    std = run_app(story="chain", view="def", topo=0, mech="sup", shock="one", s=10.0, bank=0, net=1)
    ok('<div class="story">' in std["html"], "в «Дефолтах» тот же сценарий показан (регрессии нет)")
    g = st_["g"]; g["apply_story"]("all")
    ok(st_["state"]["view"] == "def" and st_["state"]["_last_view"] == "def", "выбор сценария из режима S переключает на «Дефолты»")
    # смена режима или параметров пересоздаёт фрейм (новый ключ контейнера) -> анимация остановлена, шаг сброшен
    sigs = {run_app(topo=0, mech="none", shock="all", s=6.0, net=1, view=v)["g"]["sig"] for v in ("def", "S")}
    sigs2 = {run_app(topo=0, mech="none", shock="all", s=x, net=1, view="S", R=R)["g"]["sig"] for x in (6.0, 6.5) for R in (0.4, 0.6)}
    ok(len(sigs) == 2 and len(sigs2) == 4, "ключ фрейма меняется при смене режима и параметров S (фрейм пересоздаётся с шага 0)")
    # JS: узлы, кольца, подсказки, панель по шагам; примеры с частичными потерями (α = 0,1) — иначе при α ≥ 0,3 все насыщены
    cov = dict(off=0, part=0, mid=0, sat=0)
    for tag, cfg in (("общий 6%, α 0,5", dict(topo=0, shock="all", s=6.0, net=1)),
                     ("общий 2%, α 0,1, хвост сведён", dict(topo=0, shock="all", s=2.0, net=1, alpha=0.1)),
                     ("банк 0, 5%, α 0,1, R 0,6, концентрированная, хвост сведён", dict(topo=1, shock="one", s=5.0, net=1, bank=0, alpha=0.1, R=0.6)),
                     ("банк 4, 15%, сеть 3", dict(topo=1, shock="one", s=15.0, net=3, bank=4))):
        oo = run_app(view="S", mech="sup", **cfg); DD = trace_data(oo["html"])
        check_S_js(oo["html"], DD, f"S, {tag}", cov)
    ok(all(v > 0 for v in cov.values()), f"перебор S покрывает все состояния узла: {cov}")
    res = run_js(h, range(len(D["h"]))); Tn = len(D["h"])
    ok("S_ind после шага, % суммарных активов" in res["wv"] and "Сколько банков упало" not in res["wv"]
       and res["wv"].count('class="wc') == Tn, "график по шагам в S: S_ind после шага, подпись величины, столбец на каждый шаг")
    # навигация и защита клавиш в S
    C_ = D["captions"]; nv = run_js(h, [], nav=True)["nav"]; Tn1 = Tn - 1
    ok(nv[0]["cap"] == C_[0] and nv[0]["p"] and not nv[0]["n"] and nv[1]["cap"] == C_[1] and nv[2]["cap"] == C_[0] and nv[3]["cap"] == C_[0],
       "S: «← Назад» недоступна на шаге 0, «Вперёд →» / «← Назад» листают итерации")
    ok(nv[4]["cap"] == C_[Tn1] and nv[4]["n"] and nv[5]["cap"] == C_[Tn1] and nv[6]["cap"] == C_[Tn1 - 1],
       "S: «Вперёд →» доходит до равновесия и становится недоступной, «← Назад» возвращает")
    ok(all(nv[k]["cap"] == C_[1] for k in range(8, 13)) and nv[13]["cap"] == C_[2] and nv[14]["cap"] == C_[1],
       "S: стрелки в полях и ползунках не листают, на странице и на кнопке листают")
    pk = run_js(o1["html"], [], pick_i=3)
    ok(pk["clicks"] == [3] and "Клик: ударить шоком" in pk["pick_tip"], "S: клик по банку 3 нажимает pick_3, подсказка о клике есть")
    ok(C_[-1].startswith(f"Равновесие, итерация {rec['n_iter']}") and C_[0].startswith("Общий шок 6,0%"), f"подписи S: «{C_[0]}» … «{C_[-1]}»")
    # несходимость: сообщение вместо графа
    old = C.MAXIT; C.MAXIT = 1
    try: bad = run_app(topo=0, mech="none", shock="all", s=6.0, net=1, view="S")
    finally: C.MAXIT = old
    ok("html" not in bad and any("не рассчитано" in w for w in bad.get("warnings", [])), "несходимость в S: предупреждение, граф не показан")


HYP_HARNESS = r"""<!doctype html><html><head><meta charset="utf-8"></head><body style="margin:0">
<script id="P" type="application/json">__P__</script><script>
const P=JSON.parse(document.getElementById('P').textContent);
function load(fr,html){return new Promise(r=>{fr.onload=()=>setTimeout(r,60);fr.srcdoc=html})}
(async()=>{const out=[];const fr=document.createElement('iframe');fr.style.border='0';document.body.appendChild(fr);
 for(const w of P.widths){fr.style.width=w+'px';fr.style.height=P.fh+'px';
  for(const p of P.pages){await load(fr,p.html);const d=fr.contentDocument;
   let over=0;d.querySelectorAll('.card,.verdict,table,svg').forEach(e=>{const r=e.getBoundingClientRect();if(r.right>w+1)over++});
   out.push({w,name:p.name,h:d.documentElement.scrollHeight,sw:d.documentElement.scrollWidth,over})}}
 document.body.setAttribute('data-out',JSON.stringify(out))})()</script></body></html>"""


def block_G(res):
    """Раздел «Проверка гипотезы»: высота фрейма результатов (значение из hyp_page.py) и горизонтальный выход за край."""
    print("Блок G: «Проверка гипотезы» в headless Chromium (компоновка)")
    import html as _h
    sys.modules["streamlit"] = make_streamlit({}, {})
    for m in ("hypothesis", "hyp_view"): sys.modules.pop(m, None)
    import hypothesis as H
    from hyp_view import hyp_html
    fh = int(re.search(r"embed\(hyp_html\(.*\), (\d+)\)", open(os.path.join(HERE, "hyp_page.py"), encoding="utf-8").read()).group(1))
    pages = [dict(name=f"{m}_{th}", html=hyp_html(r, H.verdict(r), H.precomputed(), th)) for m, r in res.items() for th in ("dark", "light")]
    P = json.dumps(dict(pages=pages, widths=WIDTHS, fh=fh), ensure_ascii=False).replace("</", "<\\/")
    with tempfile.TemporaryDirectory() as d:
        hp = os.path.join(d, "h.html"); open(hp, "w", encoding="utf-8").write(HYP_HARNESS.replace("__P__", P))
        r = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=2000,1100",
                            "--virtual-time-budget=60000", "--dump-dom", "file://" + hp], capture_output=True, text=True, timeout=300)
    m = re.search(r'data-out="([^"]*)"', r.stdout)
    if not m: ok(False, "Chromium не вернул замеры раздела гипотезы"); return
    out = json.loads(_h.unescape(m.group(1)))
    ok(len(out) == len(pages) * len(WIDTHS), f"измерено {len(out)} = {len(pages)} страниц × {len(WIDTHS)} ширин, фрейм {fh} px")
    # scrollHeight не меньше высоты фрейма, поэтому отдельно меряем содержимое во фрейме высотой 600 px
    P2 = json.dumps(dict(pages=pages, widths=WIDTHS, fh=600), ensure_ascii=False).replace("</", "<\\/")
    with tempfile.TemporaryDirectory() as d:
        hp = os.path.join(d, "h.html"); open(hp, "w", encoding="utf-8").write(HYP_HARNESS.replace("__P__", P2))
        r2 = subprocess.run([CHROME, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--window-size=2000,1100",
                             "--virtual-time-budget=60000", "--dump-dom", "file://" + hp], capture_output=True, text=True, timeout=300)
    cont = {(o["w"], o["name"]): o["h"] for o in json.loads(_h.unescape(re.search(r'data-out="([^"]*)"', r2.stdout).group(1)))}
    mx = max(cont.values()); arg = max(cont, key=cont.get)
    print(f"  максимум содержимого по {len(cont)} замерам: {mx} px ({arg[1]}, ширина {arg[0]}); ×1,1 = {round(mx * 1.1)}; высота фрейма {fh}")
    ok(mx <= fh, f"содержимое раздела гипотезы ({mx} px) помещается во фрейм {fh} px")
    for w in WIDTHS:
        rows = [o for o in out if o["w"] == w]; top = max(rows, key=lambda o: cont[(o["w"], o["name"])])
        top = dict(top, h=cont[(top["w"], top["name"])])
        ok(all(o["h"] <= fh for o in rows) and all(o["sw"] <= w and o["over"] == 0 for o in rows),
           f"ширина {w}: высота до {top['h']} px ({top['name']}) ≤ {fh}, по горизонтали ничего не выходит за край")


def main():
    print("Компиляция")
    for f in ("app.py", "viz.py", "cascade_trace.py", "hyp_page.py", "hyp_view.py", "check_ui.py"):
        try: compile(open(os.path.join(HERE, f), encoding="utf-8").read(), f, "exec"); ok(True, f)
        except SyntaxError as e: ok(False, f"{f}: {e}")
    if NODE is None:
        print("Node не найден: JS не проверен"); sys.exit(2)
    print(f"Node: {subprocess.run([NODE, '--version'], capture_output=True, text=True).stdout.strip()}")
    full = "--full-height" in sys.argv
    if full:
        if CHROME is None: print("Chromium не найден (KS_CHROME): высота не проверена"); sys.exit(2)
        print(f"Chromium: {CHROME}"); block_HC(full=True); block_G(hyp_results())
        print("ИТОГ: " + ("ВСЁ ПРОЙДЕНО" if not FAIL else f"ОШИБОК {len(FAIL)}")); sys.exit(1 if FAIL else 0)
    block_R(); block_V(); block_J(); hyp = block_T(); block_ST(); block_S()
    if CHROME is None:
        print("Chromium не найден (задайте KS_CHROME): высота и взаимодействие в браузере не проверены"); sys.exit(2)
    print(f"Chromium: {CHROME}")
    block_HC(full=False); block_G(hyp)
    print("ИТОГ: " + ("ВСЁ ПРОЙДЕНО" if not FAIL else f"ОШИБОК {len(FAIL)}"))
    sys.exit(1 if FAIL else 0)

if __name__ == "__main__":
    main()
