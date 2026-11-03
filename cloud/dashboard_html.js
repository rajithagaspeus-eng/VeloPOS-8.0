// The owner's phone page. Plain HTML/JS; data is fetched from /api/snap/<shop>?t=<token> and written with textContent only.
// NOTE: keep this file free of backticks, ${ and backslashes (it is one template literal).
export default `<!doctype html>
<html lang="si"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0f766e">
<title>VeloPOS Dashboard</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--text:#14212b;--muted:#5d6b78;--line:#e2e8ee;--accent:#0f766e;--bad:#b42318;--good:#067647;--bar:#0f766e;--bar2:#9fd8d2}
@media(prefers-color-scheme:dark){:root{--bg:#0e1519;--card:#162027;--text:#e8eff3;--muted:#98a8b4;--line:#243540;--accent:#3dc2b3;--bad:#ff8a80;--good:#57d38c;--bar:#3dc2b3;--bar2:#1f5b55}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.4 system-ui,-apple-system,"Segoe UI","Iskoola Pota","Nirmala UI",Roboto,sans-serif}
main{max-width:720px;margin:0 auto;padding:16px}
h1{font-size:20px;margin:4px 0 0}
.sub{color:var(--muted);font-size:13px;margin:2px 0 14px}
.warn{background:#fff3cd;color:#664d03;border-radius:10px;padding:10px 12px;margin:0 0 12px;font-size:14px}
@media(prefers-color-scheme:dark){.warn{background:#3a2f0b;color:#ffe08a}}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-bottom:10px}
.k{color:var(--muted);font-size:12px}
.v{font-size:22px;font-weight:700;margin-top:2px;word-break:break-word}
.v.neg{color:var(--bad)}
h2{font-size:14px;margin:0 0 8px;color:var(--muted);font-weight:600}
.row{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-top:1px solid var(--line);font-size:15px}
.row:first-of-type{border-top:0}
.row span:last-child{font-weight:600;white-space:nowrap}
.tabs{display:flex;gap:6px;margin-bottom:8px}
.tabs button{flex:1;border:1px solid var(--line);background:transparent;color:var(--text);border-radius:8px;padding:6px;font:inherit;font-size:13px}
.tabs button.on{background:var(--accent);color:#fff;border-color:var(--accent)}
svg{width:100%;height:150px;display:block}
.empty{color:var(--muted);font-size:14px}
.msg{text-align:center;margin:60px 12px;color:var(--muted)}
</style></head>
<body><main id="app"><div class="msg" id="msg">Loading...</div></main>
<script>
(function(){
var parts=location.pathname.split("/"),shop=parts[2]||"",tok=new URLSearchParams(location.search).get("t")||"";
var app=document.getElementById("app"),snap=null,upd=0,range=7;
function el(tag,cls,text){var e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}
function money(n){return Number(n||0).toLocaleString("en-LK",{minimumFractionDigits:0,maximumFractionDigits:2})}
function ago(sec){var m=Math.round(sec/60);if(m<1)return "just now";if(m<60)return m+" min ago";var h=Math.round(m/60);return h<24?h+" h ago":Math.round(h/24)+" d ago"}
function say(t){app.textContent="";app.appendChild(el("div","msg",t))}
function kpi(parent,k,v,neg){var c=el("div","card");c.appendChild(el("div","k",k));c.appendChild(el("div","v"+(neg?" neg":""),v));parent.appendChild(c)}
function listCard(title,rows,emptyText){
  var c=el("div","card");c.appendChild(el("h2","",title));
  if(!rows.length){c.appendChild(el("div","empty",emptyText))}
  rows.forEach(function(r){var d=el("div","row");d.appendChild(el("span","",r[0]));d.appendChild(el("span","",r[1]));c.appendChild(d)});
  return c}
function chart(days,cur){
  var NS="http://www.w3.org/2000/svg",s=document.createElementNS(NS,"svg");s.setAttribute("viewBox","0 0 300 150");
  var max=Math.max.apply(null,days.map(function(d){return Math.max(d.revenue,0)}).concat([1]));
  var w=300/days.length,bw=Math.max(2,w-(days.length>14?1:6));
  days.forEach(function(d,i){
    var h=Math.max(0,d.revenue)/max*120,r=document.createElementNS(NS,"rect");
    r.setAttribute("x",i*w+(w-bw)/2);r.setAttribute("y",130-h);r.setAttribute("width",bw);r.setAttribute("height",h);
    r.setAttribute("rx",2);r.setAttribute("fill",i===days.length-1?"var(--bar)":"var(--bar2)");
    var t=document.createElementNS(NS,"title");t.textContent=d.d+": "+cur+" "+money(d.revenue);r.appendChild(t);s.appendChild(r)});
  var a=document.createElementNS(NS,"text");a.setAttribute("x","0");a.setAttribute("y","146");a.setAttribute("fill","var(--muted)");a.setAttribute("font-size","10");a.textContent=days[0].d.slice(5);s.appendChild(a);
  var b=document.createElementNS(NS,"text");b.setAttribute("x","300");b.setAttribute("y","146");b.setAttribute("text-anchor","end");b.setAttribute("fill","var(--muted)");b.setAttribute("font-size","10");b.textContent=days[days.length-1].d.slice(5);s.appendChild(b);
  return s}
function render(){
  var cur=snap.cur||"Rs.",t=snap.today;app.textContent="";
  app.appendChild(el("h1","",snap.shop||"VeloPOS"));
  var age=Date.now()/1000-upd;
  app.appendChild(el("div","sub",snap.date+"  |  updated "+ago(age)));
  if(age>7200)app.appendChild(el("div","warn","The shop PC has not sent an update for a while (it may be switched off or offline). Figures below are from the last update."));
  var g=el("div","grid");
  kpi(g,"අද විකුණුම් / Sales today",cur+" "+money(t.revenue));
  kpi(g,"ලාභය / Profit",cur+" "+money(t.profit),t.profit<0);
  kpi(g,"බිල් ගණන / Bills",String(t.bills));
  kpi(g,"වියදම් / Expenses",cur+" "+money(t.expenses));
  app.appendChild(g);
  var pm=Object.keys(t.methods||{}).map(function(k){return [k,cur+" "+money(t.methods[k])]});
  app.appendChild(listCard("ගෙවීම් ක්‍රම / Payment methods",pm,"No sales yet today."));
  var c=el("div","card"),tabs=el("div","tabs");
  [7,30].forEach(function(n){var b=el("button",range===n?"on":"",n+" days");b.onclick=function(){range=n;render()};tabs.appendChild(b)});
  c.appendChild(el("h2","","විකුණුම් / Sales"));c.appendChild(tabs);
  var ds=snap.days.slice(-range);c.appendChild(chart(ds,cur));
  var sum=ds.reduce(function(a,d){return a+d.revenue},0),pr=ds.reduce(function(a,d){return a+d.profit},0);
  c.appendChild(el("div","sub","Total "+cur+" "+money(sum)+"  |  Profit "+cur+" "+money(pr)));
  app.appendChild(c);
  app.appendChild(listCard("වැඩිපුරම විකුණුණු (දවස් 7) / Top items (7 days)",snap.top.map(function(x){return [x.n,cur+" "+money(x.t)]}),"No sales in the last 7 days."));
  app.appendChild(listCard("තොග අඩුයි / Low stock",snap.low.map(function(x){return [x.n,String(x.q)]}),"Nothing is low."));
  app.appendChild(listCard("ණය / Credit owed to you",snap.credit.count?[[snap.credit.count+" customers",cur+" "+money(snap.credit.total)]]:[],"No outstanding credit."));
}
function load(){
  if(!/^[0-9a-f]{16}$/.test(shop)||!tok){say("This link is not valid.");return}
  fetch("/api/snap/"+shop+"?t="+encodeURIComponent(tok),{cache:"no-store"}).then(function(r){
    if(r.status===402){say("The dashboard subscription has ended. Please contact your VeloPOS provider.");return null}
    if(r.status===404){if(!snap)say("No data yet, or the link is no longer valid. Open the link from the POS Settings again.");return null}
    return r.json()}).then(function(j){if(j&&j.snap){snap=j.snap;upd=j.updated;render()}}).catch(function(){if(!snap)say("Cannot connect. Check your internet.")})}
load();setInterval(load,60000);
})();
</script></body></html>`;
