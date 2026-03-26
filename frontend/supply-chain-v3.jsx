const { useState, useEffect, useRef, useCallback } = React;

/*
 * SUPPLY CHAIN INTELLIGENCE v3.0
 * OptiGuide Architecture Extension · arXiv 2307.03875v2
 * Built by Atharva
 *
 * v3 additions:
 *  - Leaflet.js interactive world map (CartoDB dark tiles)
 *  - Live Disruption Feed (Serper.dev intelligence)
 *  - Open-Meteo weather overlays on hub nodes
 *  - PuLP MIP solver (backend) + greedy JS fallback
 *  - NetworkX route optimization with disruption penalties
 *  - EWMA 7-day prediction panel
 */

// ─── API BASE ──────────────────────────────────────────────────────────────────
// ⚠️  BEFORE DEPLOYING: replace "" with your Render backend URL
//     e.g.  const API_BASE = "https://supply-chain-v3.onrender.com";
//     Leave as "" only for local dev (backend on localhost:8000).
const API_BASE = "https://supply-chain-api-knkv.onrender.com";

// ─── STATIC DATA (mirrors backend SyntheticDataConnector) ─────
const WH = [
  {id:"WH-PHX",name:"Phoenix Hub",loc:"Phoenix, AZ",lat:33.45,lng:-112.07,cap:12000,stk:9200,type:"Primary DC",spec:"UPS & Thermal",reg:"NA"},
  {id:"WH-CLT",name:"Charlotte",loc:"Charlotte, NC",lat:35.23,lng:-80.84,cap:8500,stk:6100,type:"Regional DC",spec:"Power Distribution",reg:"NA"},
  {id:"WH-SJC",name:"San Jose",loc:"San Jose, CA",lat:37.34,lng:-121.89,cap:6000,stk:4800,type:"Regional DC",spec:"Cooling Systems",reg:"NA"},
  {id:"WH-DFW",name:"Dallas Mega",loc:"Dallas, TX",lat:32.78,lng:-96.80,cap:15000,stk:11500,type:"Primary DC",spec:"Full Portfolio",reg:"NA"},
  {id:"WH-CHI",name:"Chicago North",loc:"Chicago, IL",lat:41.88,lng:-87.63,cap:7000,stk:5300,type:"Regional DC",spec:"IT Infra",reg:"NA"},
  {id:"WH-MUM",name:"Mumbai Gateway",loc:"Mumbai, India",lat:19.08,lng:72.88,cap:10000,stk:7600,type:"Intl Hub",spec:"APAC Distribution",reg:"APAC"},
  {id:"WH-SNG",name:"Singapore Hub",loc:"Singapore",lat:1.35,lng:103.82,cap:9000,stk:6900,type:"Intl Hub",spec:"APAC Cooling",reg:"APAC"},
  {id:"WH-FRA",name:"Frankfurt",loc:"Frankfurt, DE",lat:50.11,lng:8.68,cap:8000,stk:5500,type:"Intl Hub",spec:"EMEA Distribution",reg:"EMEA"},
];
const CU = [
  {id:"C-AWS-VA",name:"AWS Virginia",loc:"Ashburn, VA",lat:39.04,lng:-77.47,dem:2400,pri:"Critical",seg:"Hyperscale",sla:3},
  {id:"C-MSFT-WA",name:"Microsoft Quincy",loc:"Quincy, WA",lat:47.23,lng:-119.85,dem:1800,pri:"Critical",seg:"Hyperscale",sla:4},
  {id:"C-META-OR",name:"Meta Prineville",loc:"Prineville, OR",lat:44.30,lng:-120.73,dem:1500,pri:"High",seg:"Hyperscale",sla:4},
  {id:"C-GOOG-SC",name:"Google SC",loc:"The Dalles, OR",lat:45.59,lng:-121.18,dem:2000,pri:"Critical",seg:"Hyperscale",sla:3},
  {id:"C-EQX-SV",name:"Equinix SV5",loc:"San Jose, CA",lat:37.39,lng:-121.95,dem:800,pri:"High",seg:"Colocation",sla:2},
  {id:"C-DLR-TX",name:"Digital Realty",loc:"Dallas, TX",lat:32.82,lng:-96.75,dem:950,pri:"High",seg:"Colocation",sla:2},
  {id:"C-REL-MUM",name:"Reliance Jio DC",loc:"Navi Mumbai",lat:19.03,lng:73.03,dem:1200,pri:"High",seg:"Telecom",sla:5},
  {id:"C-SING-TEL",name:"Singtel DC",loc:"Singapore",lat:1.30,lng:103.85,dem:700,pri:"Medium",seg:"Telecom",sla:5},
  {id:"C-EQNX-FRA",name:"Equinix FR5",loc:"Frankfurt, DE",lat:50.08,lng:8.72,dem:650,pri:"Medium",seg:"Colocation",sla:3},
  {id:"C-JPM-NJ",name:"JPMorgan Metro",loc:"Jersey City, NJ",lat:40.73,lng:-74.04,dem:500,pri:"Critical",seg:"Enterprise",sla:2},
];
const RT = [
  {id:"R001",fr:"WH-CLT",to:"C-AWS-VA",dist:400,cpu:12.5,lead:1,tar:0,mode:"Ground"},
  {id:"R002",fr:"WH-DFW",to:"C-AWS-VA",dist:1300,cpu:28,lead:3,tar:0,mode:"Ground"},
  {id:"R003",fr:"WH-PHX",to:"C-MSFT-WA",dist:1400,cpu:31,lead:3,tar:0,mode:"Ground"},
  {id:"R004",fr:"WH-SJC",to:"C-MSFT-WA",dist:800,cpu:19.5,lead:2,tar:0,mode:"Ground"},
  {id:"R005",fr:"WH-SJC",to:"C-META-OR",dist:550,cpu:15,lead:2,tar:0,mode:"Ground"},
  {id:"R006",fr:"WH-SJC",to:"C-GOOG-SC",dist:600,cpu:16,lead:2,tar:0,mode:"Ground"},
  {id:"R007",fr:"WH-DFW",to:"C-GOOG-SC",dist:1800,cpu:35,lead:4,tar:0,mode:"Ground"},
  {id:"R008",fr:"WH-SJC",to:"C-EQX-SV",dist:10,cpu:3,lead:0.5,tar:0,mode:"Local"},
  {id:"R009",fr:"WH-DFW",to:"C-DLR-TX",dist:15,cpu:3.5,lead:0.5,tar:0,mode:"Local"},
  {id:"R010",fr:"WH-MUM",to:"C-REL-MUM",dist:30,cpu:4,lead:1,tar:5,mode:"Local"},
  {id:"R011",fr:"WH-SNG",to:"C-SING-TEL",dist:20,cpu:5,lead:1,tar:3,mode:"Local"},
  {id:"R012",fr:"WH-FRA",to:"C-EQNX-FRA",dist:15,cpu:4.5,lead:0.5,tar:2,mode:"Local"},
  {id:"R013",fr:"WH-CLT",to:"C-JPM-NJ",dist:600,cpu:18,lead:2,tar:0,mode:"Ground"},
  {id:"R014",fr:"WH-PHX",to:"C-DLR-TX",dist:1000,cpu:24,lead:3,tar:0,mode:"Ground"},
  {id:"R015",fr:"WH-CHI",to:"C-AWS-VA",dist:700,cpu:20,lead:2,tar:0,mode:"Ground"},
  {id:"R016",fr:"WH-CHI",to:"C-JPM-NJ",dist:790,cpu:21,lead:2,tar:0,mode:"Ground"},
  {id:"R017",fr:"WH-DFW",to:"C-META-OR",dist:1900,cpu:38,lead:4,tar:0,mode:"Ground"},
  {id:"R018",fr:"WH-SNG",to:"C-REL-MUM",dist:3900,cpu:65,lead:7,tar:8,mode:"Ocean"},
  {id:"R019",fr:"WH-FRA",to:"C-SING-TEL",dist:10000,cpu:85,lead:14,tar:6,mode:"Ocean"},
  {id:"R020",fr:"WH-MUM",to:"C-SING-TEL",dist:3200,cpu:55,lead:5,tar:4,mode:"Ocean"},
];

// ─── THEME ────────────────────────────────────────────────────
const K = {
  bg:"#060a14",sf:"#0c1221",sfh:"#111b2e",bd:"rgba(255,255,255,0.06)",bdh:"rgba(0,201,167,0.25)",
  tx:"#e2e8f0",tm:"rgba(255,255,255,0.4)",tf:"rgba(255,255,255,0.2)",
  ac:"#00C9A7",ag:"rgba(0,201,167,0.12)",bl:"#38bdf8",
  rd:"#f87171",or:"#fb923c",yl:"#fbbf24",pr:"#a78bfa",
  mn:"'JetBrains Mono',monospace",sn:"'DM Sans',system-ui,sans-serif",ds:"'Space Grotesk',sans-serif",
};

// ─── CATEGORY ICONS/COLORS ────────────────────────────────────
const CAT_META = {
  Weather:    {icon:"🌀",color:"#38bdf8"},
  Logistics:  {icon:"🚢",color:"#fb923c"},
  Geopolitical:{icon:"📋",color:"#fbbf24"},
  Supply:     {icon:"⚡",color:"#f87171"},
  Security:   {icon:"🔒",color:"#a78bfa"},
  General:    {icon:"📰",color:"rgba(255,255,255,0.4)"},
};

// ─── CLIENT-SIDE GREEDY SOLVER (backend fallback) ─────────────
function solveGreedy(mods = {}) {
  const tm=mods.tariffModifier||{},dm=mods.demandModifier||{},cm=mods.capacityModifier||{};
  const dR=mods.disabledRoutes||[],dW=mods.disabledWarehouses||[];
  let tc=0,tu=0,um=0;
  const alloc=[],sla=[],wu={};
  WH.forEach(w=>{
    if(dW.includes(w.id))return;
    const c=Math.max(0,w.cap+(cm[w.id]||0));
    wu[w.id]={...w,capacity:c,allocated:0,remaining:Math.min(w.stk,c)};
  });
  const sorted=[...CU].sort((a,b)=>({Critical:0,High:1,Medium:2,Low:3}[a.pri]||3)-({Critical:0,High:1,Medium:2,Low:3}[b.pri]||3));
  for(const cu of sorted){
    let rem=cu.dem+(dm[cu.id]||0);
    if(rem<=0)continue;
    const av=RT.filter(r=>r.to===cu.id&&!dR.includes(r.id)&&!dW.includes(r.fr)&&wu[r.fr])
      .map(r=>{const t=r.tar+(tm[r.id]||tm[r.fr]||0);return{...r,ec:r.cpu*(1+t/100),et:t};})
      .sort((a,b)=>a.ec-b.ec);
    let ml=0;
    for(const r of av){
      if(rem<=0)break;
      const w=wu[r.fr];
      if(!w||w.remaining<=0)continue;
      const s=Math.min(rem,w.remaining),c=s*r.ec;
      alloc.push({from:r.fr,to:r.to,fromName:w.name,toName:cu.name,units:s,cost:c,costPerUnit:r.ec,leadTimeDays:r.lead,mode:r.mode,distance:r.dist});
      w.allocated+=s;w.remaining-=s;tc+=c;tu+=s;rem-=s;ml=Math.max(ml,r.lead);
    }
    if(rem>0)um+=rem;
    if(ml>(cu.sla||999))sla.push({customer:cu.name,sla:cu.sla,actual:ml,priority:cu.pri});
  }
  const al=tu>0?alloc.reduce((s,a)=>s+a.leadTimeDays*a.units,0)/tu:0;
  return{totalCost:Math.round(tc),totalUnits:tu,unmetDemand:um,avgLeadTime:Math.round(al*10)/10,
    allocations:alloc,warehouseUsage:Object.values(wu),routeCount:alloc.length,slaViolations:sla,
    solverEngine:"Greedy (client-side)"};
}

// ─── API HOOKS ────────────────────────────────────────────────
function useApi(endpoint, refreshMs = 0) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetch_ = useCallback(async () => {
    if (!API_BASE && !endpoint.startsWith("/api/v3")) { setLoading(false); return; }
    try {
      setLoading(true);
      const r = await fetch(`${API_BASE}${endpoint}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
      setError(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [endpoint]);

  useEffect(() => {
    fetch_();
    if (refreshMs > 0) {
      const id = setInterval(fetch_, refreshMs);
      return () => clearInterval(id);
    }
  }, [fetch_, refreshMs]);

  return { data, loading, error, refetch: fetch_ };
}

// ─── SPARKLINE ────────────────────────────────────────────────
function Sparkline({ values, color = K.ac, height = 36, width = 120 }) {
  if (!values || values.length < 2) return null;
  const min = Math.min(...values), max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => [
    (i / (values.length - 1)) * width,
    height - ((v - min) / range) * height * 0.85 - height * 0.05,
  ]);
  const d = pts.map((p, i) => `${i === 0 ? "M" : "L"}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id={`sg-${color.replace("#","")}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${d} L${width} ${height} L0 ${height} Z`} fill={`url(#sg-${color.replace("#","")})`} />
      <path d={d} stroke={color} strokeWidth={1.5} fill="none" />
      {pts.map((p, i) => <circle key={i} cx={p[0]} cy={p[1]} r={i === pts.length - 1 ? 3 : 1.5} fill={color} />)}
    </svg>
  );
}

// ─── BADGE ────────────────────────────────────────────────────
function Badge({ children, color = K.ac, small }) {
  return (
    <span style={{ display:"inline-flex",padding:small?"1px 5px":"2px 7px",borderRadius:4,
      fontSize:small?9:10,fontFamily:K.mn,fontWeight:500,color,background:`${color}18` }}>
      {children}
    </span>
  );
}

// ─── STAT CARD ────────────────────────────────────────────────
function Stat({ label, value, sub, trend, color = K.ac, compact }) {
  return (
    <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:12,
      padding:compact?"10px 12px":"14px 16px",flex:1,minWidth:compact?110:140 }}>
      <div style={{ fontSize:9,textTransform:"uppercase",letterSpacing:1.5,color:K.tm,marginBottom:3,fontFamily:K.mn }}>{label}</div>
      <div style={{ fontSize:compact?20:24,fontWeight:700,color,fontFamily:K.ds,lineHeight:1.1 }}>{value}</div>
      {sub&&<div style={{ fontSize:10,color:K.tm,marginTop:2 }}>{sub}</div>}
      {trend!==undefined&&trend!==0&&(
        <div style={{ fontSize:10,marginTop:3,color:trend>0?K.rd:K.ac,fontFamily:K.mn }}>
          {trend>0?"▲":"▼"} {Math.abs(trend)}%
        </div>
      )}
    </div>
  );
}

// ─── WAREHOUSE BARS ───────────────────────────────────────────
function Bars({ usage }) {
  if (!usage) return null;
  return (
    <div style={{ display:"flex",flexDirection:"column",gap:5 }}>
      {usage.filter(w=>w.allocated>0||w.remaining>0).map(w=>{
        const p=w.capacity>0?Math.round(w.allocated/w.capacity*100):0;
        return (
          <div key={w.id} style={{ display:"flex",alignItems:"center",gap:8 }}>
            <div style={{ width:85,fontSize:10,color:K.tm,fontFamily:K.mn,flexShrink:0 }}>{w.name}</div>
            <div style={{ flex:1,height:8,background:"rgba(255,255,255,0.04)",borderRadius:4,overflow:"hidden" }}>
              <div style={{ height:"100%",width:`${p}%`,borderRadius:4,transition:"width .6s",
                background:p>85?`linear-gradient(90deg,${K.or},${K.rd})`:p>60?`linear-gradient(90deg,${K.ac},${K.yl})`:`linear-gradient(90deg,${K.ac},${K.bl})` }} />
            </div>
            <div style={{ width:30,fontSize:9,color:K.tm,textAlign:"right",fontFamily:K.mn }}>{p}%</div>
          </div>
        );
      })}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// LEAFLET MAP  ← the v3 hero feature
// ═══════════════════════════════════════════════════════════════
function LeafletMap({ allocations, hubScores, weatherData, optimizedRoutes, onNodeClick }) {
  const containerRef = useRef(null);
  const mapRef       = useRef(null);
  const layersRef    = useRef([]);

  // Boot Leaflet via CDN (works without build system changes)
  useEffect(() => {
    const CSS_ID = "leaflet-v3-css";
    if (!document.getElementById(CSS_ID)) {
      const lk = document.createElement("link");
      lk.id = CSS_ID; lk.rel = "stylesheet";
      lk.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      document.head.appendChild(lk);
    }

    const boot = () => {
      if (mapRef.current || !containerRef.current) return;
      const L = window.L;
      const map = L.map(containerRef.current, {
        center: [25, 5], zoom: 2,
        zoomControl: false, attributionControl: false,
        minZoom: 2, maxZoom: 12,
      });
      L.tileLayer(
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        { attribution: "©OpenStreetMap ©CARTO", maxZoom: 19 }
      ).addTo(map);
      L.control.zoom({ position: "bottomright" }).addTo(map);
      mapRef.current = map;
      drawLayers();
    };

    if (window.L) {
      boot();
    } else {
      const sc = document.createElement("script");
      sc.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
      sc.onload = boot;
      document.head.appendChild(sc);
    }
    return () => {
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, []);

  // Redraw whenever data changes
  useEffect(() => { if (mapRef.current) drawLayers(); },
    [allocations, hubScores, weatherData, optimizedRoutes]);

  function drawLayers() {
    const L = window.L;
    if (!L || !mapRef.current) return;
    layersRef.current.forEach(l => l.remove());
    layersRef.current = [];

    const alloc = allocations || [];
    const scores = hubScores || {};
    const wMap = Object.fromEntries(WH.map(w=>[w.id,w]));
    const cMap = Object.fromEntries(CU.map(c=>[c.id,c]));
    const wDataMap = Object.fromEntries((weatherData||[]).map(w=>[w.hub_id,w]));

    // ── Route lines ──────────────────────────────────────────
    const routesDrawn = new Set();
    const routesToDraw = alloc.length > 0 ? alloc : RT.map(r=>({
      from:r.fr, to:r.to, units:0, mode:r.mode
    }));

    routesToDraw.forEach(a => {
      const key = `${a.from}-${a.to}`;
      if (routesDrawn.has(key)) return;
      routesDrawn.add(key);

      const src = wMap[a.from];
      const dst = cMap[a.to];
      if (!src || !dst) return;

      const disrupted = (scores[a.from] || 0) > 0.5;
      const isOcean   = a.mode === "Ocean";
      const color     = disrupted ? K.rd : isOcean ? "#60a5fa" : K.ac;
      const weight    = a.units > 500 ? 2.5 : 1.5;
      const dashArr   = isOcean ? "6 4" : null;

      // Curved arc: midpoint offset for visual clarity
      const midLat = (src.lat + dst.lat) / 2 + (isOcean ? 8 : 3);
      const midLng = (src.lng + dst.lng) / 2;

      const pts = [[src.lat, src.lng], [midLat, midLng], [dst.lat, dst.lng]];
      const line = L.polyline(pts, {
        color, weight, opacity: disrupted ? 0.9 : 0.55,
        dashArray: dashArr, smoothFactor: 2,
      }).addTo(mapRef.current);

      if (a.units > 0) {
        line.bindTooltip(
          `<b>${src.name} → ${cMap[a.to]?.name || a.to}</b><br>${a.units.toLocaleString()} units · ${a.mode}`,
          { sticky: true, className: "sc-tooltip" }
        );
      }
      layersRef.current.push(line);
    });

    // ── Warehouse nodes ──────────────────────────────────────
    WH.forEach(wh => {
      const score  = scores[wh.id] || 0;
      const weather = wDataMap[wh.id] || {};
      const color  = score > 0.7 ? K.rd : score > 0.4 ? K.or : K.ac;
      const radius = 14 + Math.round(score * 8);

      const icon = L.divIcon({
        className: "",
        html: `<div style="
          width:${radius}px;height:${radius}px;border-radius:50%;
          background:${color}22;border:2px solid ${color};
          display:flex;align-items:center;justify-content:center;
          box-shadow:0 0 ${score > 0.5 ? 16 : 8}px ${color}${score > 0.5 ? "88" : "44"};
          cursor:pointer;position:relative;">
          <div style="width:6px;height:6px;border-radius:50%;background:${color}"></div>
          ${score > 0.5 ? `<div style="position:absolute;top:-1px;right:-1px;width:8px;height:8px;border-radius:50%;background:${K.rd};border:1px solid ${K.bg};animation:pulse-dot 1.4s infinite;"></div>` : ""}
        </div>
        <div style="color:${K.tx};font-size:9px;font-family:${K.mn};text-align:center;margin-top:2px;white-space:nowrap;text-shadow:0 0 4px #000">${wh.name}</div>`,
        iconSize: [radius + 30, radius + 18],
        iconAnchor: [radius / 2 + 15, radius / 2 + 2],
      });

      const marker = L.marker([wh.lat, wh.lng], { icon })
        .addTo(mapRef.current)
        .on("click", () => onNodeClick && onNodeClick({ type: "warehouse", ...wh, score, weather }));

      const weatherDesc = weather.description || "–";
      const temp = weather.temperature != null ? `${weather.temperature}°C` : "–";
      marker.bindPopup(`
        <div style="font-family:${K.mn};font-size:11px;color:#111;min-width:200px">
          <b style="font-size:13px">${wh.name}</b><br>
          <span style="color:#666">${wh.loc} · ${wh.type}</span><br><br>
          <b>Capacity:</b> ${wh.stk.toLocaleString()} / ${wh.cap.toLocaleString()}<br>
          <b>Disruption Score:</b> <span style="color:${color}">${(score*100).toFixed(0)}%</span><br>
          <b>Weather:</b> ${weatherDesc} · ${temp} · ${weather.windSpeed || 0} km/h<br>
          <b>Lead Impact:</b> +${((weather.leadTimeImpact||0)*100).toFixed(0)}% · Cost Impact: +${((weather.costImpact||0)*100).toFixed(0)}%
        </div>
      `);
      layersRef.current.push(marker);
    });

    // ── Customer nodes ───────────────────────────────────────
    CU.forEach(cu => {
      const optRoute = (optimizedRoutes || []).find(r => r.customer === cu.id);
      const isRerouted = optRoute?.isRerouted;
      const color = cu.pri === "Critical" ? K.or : cu.pri === "High" ? K.yl : K.tf.replace("rgba","rgb").replace(",0.2","");

      const icon = L.divIcon({
        className: "",
        html: `<div style="
          width:10px;height:10px;border-radius:50%;
          background:${color}33;border:1.5px solid ${color};
          box-shadow:0 0 6px ${color}44;cursor:pointer;
          ${isRerouted ? `outline:2px solid ${K.rd};outline-offset:2px;` : ""}">
        </div>
        <div style="color:${K.tm};font-size:8px;font-family:${K.mn};text-align:center;margin-top:1px;white-space:nowrap;text-shadow:0 0 4px #000">${cu.name.split(" ")[0]}</div>`,
        iconSize: [60, 22],
        iconAnchor: [30, 5],
      });

      const marker = L.marker([cu.lat, cu.lng], { icon })
        .addTo(mapRef.current)
        .on("click", () => onNodeClick && onNodeClick({ type: "customer", ...cu, optRoute }));

      marker.bindPopup(`
        <div style="font-family:${K.mn};font-size:11px;color:#111;min-width:180px">
          <b style="font-size:13px">${cu.name}</b><br>
          <span style="color:#666">${cu.loc} · ${cu.seg}</span><br><br>
          <b>Demand:</b> ${cu.dem.toLocaleString()} units<br>
          <b>Priority:</b> ${cu.pri} · SLA: ${cu.sla}d<br>
          ${optRoute ? `<b>Optimal WH:</b> ${optRoute.optimalWarehouseName}<br>
          <b>Mode:</b> ${optRoute.mode} · ${optRoute.leadTime}d lead<br>
          ${isRerouted ? `<span style="color:#ef4444"><b>⚠ Rerouted</b> — disruption at primary WH</span>` : ""}` : ""}
        </div>
      `);
      layersRef.current.push(marker);
    });

    // Inject pulse animation CSS once
    if (!document.getElementById("sc-pulse-css")) {
      const style = document.createElement("style");
      style.id = "sc-pulse-css";
      style.textContent = `
        @keyframes pulse-dot { 0%,100%{opacity:1;transform:scale(1)} 50%{opacity:.4;transform:scale(1.5)} }
        .sc-tooltip { background:#0c1221!important; border:1px solid rgba(0,201,167,.3)!important; color:#e2e8f0!important; font-family:'JetBrains Mono',monospace!important; font-size:11px!important; border-radius:6px!important; box-shadow:0 4px 20px rgba(0,0,0,.6)!important; }
        .leaflet-popup-content-wrapper { background:#0c1221!important; border:1px solid rgba(0,201,167,.25)!important; border-radius:10px!important; box-shadow:0 8px 32px rgba(0,0,0,.7)!important; }
        .leaflet-popup-tip { background:#0c1221!important; }
      `;
      document.head.appendChild(style);
    }
  }

  return (
    <div ref={containerRef}
      style={{ width:"100%",height:"100%",borderRadius:12,overflow:"hidden",
               background:K.bg,position:"relative" }} />
  );
}

// ═══════════════════════════════════════════════════════════════
// DISRUPTION FEED PANEL
// ═══════════════════════════════════════════════════════════════
function DisruptionFeed({ events, hubScores, isLive, onRefresh }) {
  const [selected, setSelected] = useState(null);

  if (!events || events.length === 0) return (
    <div style={{ height:"100%",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",gap:8 }}>
      <div style={{ fontSize:24 }}>📡</div>
      <div style={{ fontSize:11,color:K.tm,fontFamily:K.mn,textAlign:"center" }}>
        {isLive ? "Loading intelligence..." : "Configure SERPER_API_KEY\nfor live disruption data"}
      </div>
    </div>
  );

  return (
    <div style={{ height:"100%",display:"flex",flexDirection:"column",gap:0 }}>
      {/* Header */}
      <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:10 }}>
        <div style={{ fontSize:10,fontFamily:K.mn,color:K.tm,textTransform:"uppercase",letterSpacing:1.5 }}>
          Disruption Feed
        </div>
        <div style={{ display:"flex",alignItems:"center",gap:6 }}>
          {isLive && (
            <div style={{ display:"flex",alignItems:"center",gap:4 }}>
              <div style={{ width:6,height:6,borderRadius:"50%",background:K.ac,
                            boxShadow:`0 0 8px ${K.ac}`,animation:"pulse-dot 2s infinite" }} />
              <span style={{ fontSize:9,color:K.ac,fontFamily:K.mn }}>LIVE</span>
            </div>
          )}
          <button onClick={onRefresh}
            style={{ background:"none",border:`1px solid ${K.bd}`,borderRadius:6,
                     padding:"2px 8px",color:K.tm,fontSize:9,fontFamily:K.mn,cursor:"pointer" }}>
            ↻
          </button>
        </div>
      </div>

      {/* Events list */}
      <div style={{ flex:1,overflowY:"auto",display:"flex",flexDirection:"column",gap:6 }}>
        {events.map((ev, i) => {
          const meta = CAT_META[ev.category] || CAT_META.General;
          const score = ev.riskScore || 0;
          const scoreColor = score > 0.65 ? K.rd : score > 0.4 ? K.or : K.ac;
          const wh = WH.find(w => w.id === ev.hub_id);
          const isSelected = selected === i;

          return (
            <div key={i} onClick={() => setSelected(isSelected ? null : i)}
              style={{ background:isSelected?K.sfh:K.sf,border:`1px solid ${isSelected?K.bdh:K.bd}`,
                       borderRadius:8,padding:"8px 10px",cursor:"pointer",
                       transition:"all .2s",borderLeft:`3px solid ${scoreColor}` }}>
              <div style={{ display:"flex",justifyContent:"space-between",alignItems:"flex-start",gap:8 }}>
                <div style={{ display:"flex",alignItems:"center",gap:6,flex:1,minWidth:0 }}>
                  <span style={{ fontSize:14 }}>{meta.icon}</span>
                  <div style={{ flex:1,minWidth:0 }}>
                    <div style={{ fontSize:10,fontFamily:K.mn,color:K.tx,lineHeight:1.3,
                                  overflow:"hidden",textOverflow:"ellipsis",
                                  display:"-webkit-box",WebkitLineClamp:2,WebkitBoxOrient:"vertical" }}>
                      {ev.title}
                    </div>
                    <div style={{ fontSize:9,color:K.tm,marginTop:2,fontFamily:K.mn }}>
                      {wh?.name || ev.hub_id} · {ev.source}
                    </div>
                  </div>
                </div>
                <div style={{ textAlign:"right",flexShrink:0 }}>
                  <div style={{ fontSize:13,fontWeight:700,color:scoreColor,fontFamily:K.ds }}>
                    {(score*100).toFixed(0)}
                  </div>
                  <div style={{ fontSize:8,color:K.tm,fontFamily:K.mn }}>risk</div>
                </div>
              </div>
              {isSelected && (
                <div style={{ marginTop:8,paddingTop:8,borderTop:`1px solid ${K.bd}` }}>
                  <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,lineHeight:1.5 }}>{ev.snippet}</div>
                  <div style={{ marginTop:6,display:"flex",gap:6,flexWrap:"wrap" }}>
                    <Badge color={meta.color} small>{ev.category}</Badge>
                    {ev.date && <Badge color={K.tm} small>{ev.date}</Badge>}
                    {score > 0.6 && <Badge color={K.rd} small>ACTION REQUIRED</Badge>}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// PREDICTION PANEL
// ═══════════════════════════════════════════════════════════════
function PredictionPanel({ predictions, baseline }) {
  if (!predictions) {
    // Build client-side predictions from static signals as fallback
    const fb = { stressScore:0.28,riskLevel:"LOW",riskColor:K.ac,
      forecast:Array.from({length:7},(_,i)=>({day:i+1,cost:(baseline?.totalCost||168000)*(1+i*0.008),leadTime:(baseline?.avgLeadTime||1.6)*(1+i*0.005),unmetRisk:0.05+i*0.02})),
      topFactors:[],costTrend7d:3.2,day7Cost:(baseline?.totalCost||168000)*1.05 };
    predictions = fb;
  }

  const { forecast=[], riskLevel="LOW", riskColor=K.ac, stressScore=0, topFactors=[], costTrend7d=0 } = predictions;
  const costValues = forecast.map(d => d.cost);
  const leadValues = forecast.map(d => d.leadTime);

  return (
    <div style={{ display:"flex",flexDirection:"column",gap:10,height:"100%" }}>
      {/* Risk Level */}
      <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center" }}>
        <div style={{ fontSize:10,fontFamily:K.mn,color:K.tm,textTransform:"uppercase",letterSpacing:1.5 }}>
          7-Day Forecast
        </div>
        <div style={{ display:"flex",alignItems:"center",gap:8 }}>
          <div style={{ width:8,height:8,borderRadius:"50%",background:riskColor,boxShadow:`0 0 10px ${riskColor}` }} />
          <span style={{ fontSize:11,fontFamily:K.mn,color:riskColor,fontWeight:700 }}>{riskLevel} RISK</span>
        </div>
      </div>

      {/* Stress Score */}
      <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:8,padding:"8px 10px" }}>
        <div style={{ display:"flex",justifyContent:"space-between",marginBottom:6 }}>
          <span style={{ fontSize:9,color:K.tm,fontFamily:K.mn }}>COMBINED STRESS</span>
          <span style={{ fontSize:12,fontWeight:700,color:riskColor,fontFamily:K.ds }}>{(stressScore*100).toFixed(0)}%</span>
        </div>
        <div style={{ height:4,background:"rgba(255,255,255,0.04)",borderRadius:2,overflow:"hidden" }}>
          <div style={{ height:"100%",width:`${stressScore*100}%`,background:`linear-gradient(90deg,${riskColor},${riskColor}aa)`,
                        borderRadius:2,transition:"width .8s" }} />
        </div>
      </div>

      {/* Cost sparkline */}
      <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:8,padding:"8px 10px" }}>
        <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:6 }}>
          <span style={{ fontSize:9,color:K.tm,fontFamily:K.mn }}>COST TREND</span>
          <span style={{ fontSize:10,fontFamily:K.mn,color:costTrend7d>0?K.rd:K.ac }}>
            {costTrend7d>0?"▲":"▼"} {Math.abs(costTrend7d).toFixed(1)}% day 7
          </span>
        </div>
        <Sparkline values={costValues} color={costTrend7d>3?K.rd:costTrend7d>0?K.or:K.ac} height={38} width={200} />
        <div style={{ display:"flex",justifyContent:"space-between",marginTop:4 }}>
          {forecast.filter((_,i)=>i%2===0).map(d=>(
            <span key={d.day} style={{ fontSize:8,color:K.tf,fontFamily:K.mn }}>{d.date}</span>
          ))}
        </div>
      </div>

      {/* Lead time sparkline */}
      <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:8,padding:"8px 10px" }}>
        <div style={{ marginBottom:6 }}>
          <span style={{ fontSize:9,color:K.tm,fontFamily:K.mn }}>LEAD TIME TREND</span>
        </div>
        <Sparkline values={leadValues} color={K.bl} height={30} width={200} />
      </div>

      {/* Risk factors */}
      {topFactors.length > 0 && (
        <div style={{ flex:1,overflow:"hidden" }}>
          <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,marginBottom:6,textTransform:"uppercase",letterSpacing:1 }}>
            Top Risk Factors
          </div>
          <div style={{ display:"flex",flexDirection:"column",gap:4 }}>
            {topFactors.map((f,i) => {
              const meta = CAT_META[f.type] || CAT_META.General;
              return (
                <div key={i} style={{ display:"flex",alignItems:"center",gap:8,
                  background:K.sf,border:`1px solid ${K.bd}`,borderRadius:6,padding:"5px 8px" }}>
                  <span style={{ fontSize:11 }}>{meta.icon}</span>
                  <div style={{ flex:1,minWidth:0 }}>
                    <div style={{ fontSize:9,color:K.tx,fontFamily:K.mn,
                      overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap" }}>{f.desc}</div>
                    <div style={{ fontSize:8,color:K.tm,fontFamily:K.mn }}>{f.hub}</div>
                  </div>
                  <span style={{ fontSize:10,fontWeight:700,color:meta.color,fontFamily:K.ds }}>
                    {(f.score*100).toFixed(0)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// ROUTE OPTIMIZATION PANEL
// ═══════════════════════════════════════════════════════════════
function RoutePanel({ optimizedRoutes, hubScores }) {
  if (!optimizedRoutes || optimizedRoutes.length === 0) return (
    <div style={{ fontSize:10,color:K.tm,fontFamily:K.mn,padding:"8px 0" }}>
      Backend route optimizer offline. Using client-side solver.
    </div>
  );

  const rerouted = optimizedRoutes.filter(r => r.isRerouted);
  return (
    <div style={{ display:"flex",flexDirection:"column",gap:6 }}>
      <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center" }}>
        <span style={{ fontSize:9,color:K.tm,fontFamily:K.mn,textTransform:"uppercase",letterSpacing:1 }}>Active Reroutes</span>
        {rerouted.length > 0 && <Badge color={K.rd}>{rerouted.length} REROUTED</Badge>}
      </div>
      {rerouted.slice(0,4).map((r,i) => (
        <div key={i} style={{ background:K.sf,border:`1px solid rgba(248,113,113,.3)`,borderRadius:8,
                              padding:"7px 10px",borderLeft:`3px solid ${K.rd}` }}>
          <div style={{ fontSize:10,color:K.tx,fontFamily:K.mn,marginBottom:3 }}>{r.customerName}</div>
          <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn }}>
            → {r.optimalWarehouseName} · {r.mode} · {r.leadTime}d
          </div>
          {r.disruptionPenalty > 0 && (
            <div style={{ fontSize:8,color:K.rd,marginTop:2,fontFamily:K.mn }}>
              ↑ ${r.disruptionPenalty?.toFixed(0)}/unit disruption surcharge
            </div>
          )}
        </div>
      ))}
      {rerouted.length === 0 && (
        <div style={{ fontSize:10,color:K.ac,fontFamily:K.mn }}>✓ All routes optimal — no disruption reroutes</div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// NODE DETAIL DRAWER
// ═══════════════════════════════════════════════════════════════
function NodeDrawer({ node, onClose }) {
  if (!node) return null;
  const isWH = node.type === "warehouse";
  const color = isWH ? K.ac : K.or;
  return (
    <div style={{ position:"absolute",top:0,right:0,height:"100%",width:260,
                  background:K.sf,border:`1px solid ${K.bdh}`,borderRadius:"0 12px 12px 0",
                  zIndex:1000,padding:16,display:"flex",flexDirection:"column",gap:12 }}>
      <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center" }}>
        <Badge color={color}>{isWH?"WAREHOUSE":"CUSTOMER"}</Badge>
        <button onClick={onClose} style={{ background:"none",border:"none",color:K.tm,fontSize:18,cursor:"pointer",lineHeight:1 }}>×</button>
      </div>
      <div>
        <div style={{ fontSize:18,fontWeight:700,color:K.tx,fontFamily:K.ds }}>{node.name}</div>
        <div style={{ fontSize:11,color:K.tm,fontFamily:K.mn }}>{node.loc || node.location}</div>
      </div>
      {isWH ? (
        <>
          <div style={{ display:"flex",flexDirection:"column",gap:6 }}>
            {[
              ["Type",node.type],["Spec",node.spec||node.specialization],
              ["Stock",`${(node.stk||node.currentStock||0).toLocaleString()} / ${(node.cap||node.capacity||0).toLocaleString()}`],
              ["Region",node.reg||node.region],
            ].map(([k,v])=>(
              <div key={k} style={{ display:"flex",justifyContent:"space-between" }}>
                <span style={{ fontSize:10,color:K.tm,fontFamily:K.mn }}>{k}</span>
                <span style={{ fontSize:10,color:K.tx,fontFamily:K.mn }}>{v}</span>
              </div>
            ))}
          </div>
          {node.score !== undefined && (
            <div style={{ background:K.sfh,border:`1px solid ${K.bd}`,borderRadius:8,padding:"8px 10px" }}>
              <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,marginBottom:4 }}>DISRUPTION SCORE</div>
              <div style={{ fontSize:22,fontWeight:700,color:node.score>0.6?K.rd:node.score>0.35?K.or:K.ac,fontFamily:K.ds }}>
                {(node.score*100).toFixed(0)}%
              </div>
              <div style={{ height:4,background:"rgba(255,255,255,.04)",borderRadius:2,marginTop:6 }}>
                <div style={{ height:"100%",width:`${node.score*100}%`,background:node.score>0.6?K.rd:node.score>0.35?K.or:K.ac,borderRadius:2 }} />
              </div>
            </div>
          )}
          {node.weather && node.weather.description !== "Unavailable" && (
            <div style={{ background:K.sfh,border:`1px solid ${K.bd}`,borderRadius:8,padding:"8px 10px" }}>
              <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,marginBottom:4 }}>LIVE WEATHER</div>
              <div style={{ fontSize:12,color:K.tx,fontFamily:K.mn }}>{node.weather.description}</div>
              <div style={{ fontSize:10,color:K.tm,fontFamily:K.mn,marginTop:4 }}>
                {node.weather.temperature}°C · {node.weather.windSpeed} km/h
              </div>
            </div>
          )}
        </>
      ) : (
        <div style={{ display:"flex",flexDirection:"column",gap:6 }}>
          {[
            ["Demand",`${(node.dem||node.demandUnits||0).toLocaleString()} units`],
            ["Priority",node.pri||node.priority],
            ["Segment",node.seg||node.segment],
            ["SLA",`${node.sla||node.slaLeadDays}d`],
          ].map(([k,v])=>(
            <div key={k} style={{ display:"flex",justifyContent:"space-between" }}>
              <span style={{ fontSize:10,color:K.tm,fontFamily:K.mn }}>{k}</span>
              <span style={{ fontSize:10,color:K.tx,fontFamily:K.mn }}>{v}</span>
            </div>
          ))}
          {node.optRoute?.isRerouted && (
            <div style={{ background:"rgba(248,113,113,.08)",border:`1px solid rgba(248,113,113,.3)`,borderRadius:8,padding:"8px 10px",marginTop:4 }}>
              <div style={{ fontSize:9,color:K.rd,fontFamily:K.mn,marginBottom:3 }}>⚠ REROUTED</div>
              <div style={{ fontSize:10,color:K.tx,fontFamily:K.mn }}>→ {node.optRoute.optimalWarehouseName}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// SCENARIO PLANNER (from v2, preserved)
// ═══════════════════════════════════════════════════════════════
const SCENARIOS = [
  {label:"Singapore shutdown",q:"shut down singapore",icon:"🔒"},
  {label:"APAC tariff +25%",q:"tariff increase 25% from singapore",icon:"📋"},
  {label:"Hyperscale demand +20%",q:"demand increase 20% hyperscale",icon:"⚡"},
  {label:"Mumbai -40% capacity",q:"reduce capacity at mumbai by 40%",icon:"🌀"},
  {label:"Chicago rail strike",q:"shut down chicago",icon:"🚂"},
  {label:"Frankfurt down",q:"shut down frankfurt",icon:"🔒"},
];

function ScenarioPlanner({ onResult }) {
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState("");

  const run = async (query) => {
    setLoading(true); setMsg("");
    try {
      if (API_BASE) {
        const r = await fetch(`${API_BASE}/query`, {
          method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({query})
        });
        const d = await r.json();
        onResult?.(d);
        setMsg(d.explanation || "Done");
      } else {
        // Client-side fallback
        const mods = parseQueryClient(query);
        const result = solveGreedy(mods);
        onResult?.({ scenario:result, baseline:solveGreedy(), is_scenario:true });
        setMsg(`Client simulation complete — ${result.totalUnits.toLocaleString()} units, $${result.totalCost.toLocaleString()} cost`);
      }
    } catch (e) {
      setMsg(`Error: ${e.message}`);
    }
    setLoading(false);
  };

  const parseQueryClient = (q) => {
    const l = q.toLowerCase(), mods = {};
    if (l.includes("shut down") || l.includes("disable")) {
      const wh = WH.find(w => l.includes(w.name.toLowerCase().split(" ")[0].toLowerCase()) || l.includes(w.id.toLowerCase().split("-")[1]));
      if (wh) mods.disabledWarehouses = [wh.id];
    }
    const m = l.match(/tariff.+?(\d+)%/); if (m) mods.tariffModifier = Object.fromEntries(RT.map(r=>[r.id,parseInt(m[1])]));
    const d = l.match(/demand.+?(\d+)%/); if (d) mods.demandModifier = Object.fromEntries(CU.map(c=>[c.id,Math.round(c.dem*parseInt(d[1])/100)]));
    const cp = l.match(/(?:reduce|cut).+?(\d+)%/); if (cp) {
      const wh = WH.find(w => l.includes(w.name.toLowerCase().split(" ")[0]));
      if (wh) mods.capacityModifier = {[wh.id]:-Math.round(wh.cap*parseInt(cp[1])/100)};
    }
    return mods;
  };

  return (
    <div style={{ display:"flex",flexDirection:"column",gap:10 }}>
      <div style={{ display:"flex",gap:6,flexWrap:"wrap" }}>
        {SCENARIOS.map((s,i)=>(
          <button key={i} onClick={()=>{setQ(s.q);run(s.q);}}
            style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:8,padding:"5px 10px",
                     color:K.tx,fontSize:10,fontFamily:K.mn,cursor:"pointer",whiteSpace:"nowrap" }}>
            {s.icon} {s.label}
          </button>
        ))}
      </div>
      <div style={{ display:"flex",gap:8 }}>
        <input value={q} onChange={e=>setQ(e.target.value)}
          onKeyDown={e=>e.key==="Enter"&&q&&run(q)}
          placeholder='e.g. "tariff increase 30% from Singapore"'
          style={{ flex:1,background:K.sfh,border:`1px solid ${K.bd}`,borderRadius:8,
                   padding:"8px 12px",color:K.tx,fontSize:11,fontFamily:K.mn,outline:"none" }} />
        <button onClick={()=>q&&run(q)} disabled={loading}
          style={{ background:K.ac,border:"none",borderRadius:8,padding:"8px 16px",
                   color:K.bg,fontSize:11,fontFamily:K.mn,fontWeight:700,cursor:"pointer" }}>
          {loading?"...":"Run"}
        </button>
      </div>
      {msg && (
        <div style={{ fontSize:10,color:K.tm,fontFamily:K.mn,padding:"6px 10px",
                      background:K.sfh,borderRadius:6,lineHeight:1.5 }}>{msg}</div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// MAIN APP
// ═══════════════════════════════════════════════════════════════
function App() {
  const [baseline, setBaseline] = useState(() => solveGreedy());
  const [scenario, setScenario] = useState(null);
  const [activeTab, setActiveTab] = useState("map");
  const [selectedNode, setSelectedNode] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(new Date());

  // v3 data hooks
  const { data: intelData,  refetch: refetchIntel  } = useApi(`${API_BASE}/api/v3/intelligence`, 300_000);
  const { data: weatherData                         } = useApi(`${API_BASE}/api/v3/weather`,      3_600_000);
  const { data: optData                             } = useApi(`${API_BASE}/api/v3/optimize`,     300_000);
  const { data: predData                            } = useApi(`${API_BASE}/api/v3/predictions`,  300_000);
  const { data: backendBaseline                     } = useApi(`${API_BASE}/baseline`);

  useEffect(() => {
    if (backendBaseline?.totalCost) setBaseline(backendBaseline);
  }, [backendBaseline]);

  const current = scenario || baseline;
  const intel   = intelData?.events   || [];
  const hubScores = intelData?.hubScores || {};
  const weather = weatherData?.hubs   || [];
  const optRoutes = optData?.routes   || [];

  // Refresh handler
  const handleRefresh = async () => {
    if (API_BASE) {
      try { await fetch(`${API_BASE}/api/v3/refresh`, {method:"POST"}); } catch (_) {}
    }
    refetchIntel();
    setLastRefresh(new Date());
  };

  const handleScenarioResult = (result) => {
    if (result.scenario) setScenario(result.scenario);
    if (result.baseline)  setBaseline(result.baseline);
  };

  // KPI deltas vs baseline
  const costDelta  = scenario ? Math.round((scenario.totalCost - baseline.totalCost) / baseline.totalCost * 100) : 0;
  const leadDelta  = scenario ? Math.round((scenario.avgLeadTime - baseline.avgLeadTime) / baseline.avgLeadTime * 100) : 0;
  const highRisk   = intel.filter(e => e.riskScore > 0.6).length;
  const rerouteCount = optData?.rerouteCount || 0;

  const TABS = ["map","intelligence","predictions","optimizer","scenarios","network"];

  return (
    <div style={{ background:K.bg,color:K.tx,fontFamily:K.sn,minHeight:"100vh",
                  display:"flex",flexDirection:"column",height:"100vh",overflow:"hidden" }}>

      {/* ── TOP HEADER BAR ─────────────────────────────── */}
      <div style={{ padding:"10px 20px",borderBottom:`1px solid ${K.bd}`,
                    display:"flex",alignItems:"center",justifyContent:"space-between",
                    background:K.sf,flexShrink:0 }}>
        <div style={{ display:"flex",alignItems:"center",gap:16 }}>
          <div style={{ display:"flex",alignItems:"center",gap:8 }}>
            <div style={{ width:28,height:28,borderRadius:8,background:K.ac,
                          display:"flex",alignItems:"center",justifyContent:"center",
                          fontSize:14,fontWeight:700,color:K.bg,fontFamily:K.ds }}>SC</div>
            <div>
              <div style={{ fontSize:13,fontWeight:700,color:K.tx,fontFamily:K.ds,lineHeight:1 }}>
                Supply Chain Intelligence
              </div>
              <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,letterSpacing:1 }}>v3.0 · OptiGuide · Built by Atharva</div>
            </div>
          </div>
        </div>

        {/* KPI pills */}
        <div style={{ display:"flex",gap:8,alignItems:"center" }}>
          {[
            {label:"COST",value:`$${Math.round(current.totalCost/1000)}K`,delta:costDelta,color:K.ac},
            {label:"UNITS",value:current.totalUnits?.toLocaleString(),color:K.bl},
            {label:"LEAD",value:`${current.avgLeadTime}d`,delta:leadDelta,color:K.yl},
            {label:"UNMET",value:current.unmetDemand||0,color:current.unmetDemand>0?K.rd:K.ac},
            {label:"ALERTS",value:highRisk,color:highRisk>0?K.rd:K.ac},
          ].map(k=>(
            <div key={k.label} style={{ background:K.sfh,border:`1px solid ${K.bd}`,borderRadius:8,
                                        padding:"4px 10px",textAlign:"center" }}>
              <div style={{ fontSize:8,color:K.tm,fontFamily:K.mn,letterSpacing:1.2 }}>{k.label}</div>
              <div style={{ fontSize:16,fontWeight:700,color:k.color,fontFamily:K.ds,lineHeight:1.1 }}>{k.value}</div>
              {k.delta!==undefined&&k.delta!==0&&(
                <div style={{ fontSize:8,color:k.delta>0?K.rd:K.ac,fontFamily:K.mn }}>
                  {k.delta>0?"▲":"▼"}{Math.abs(k.delta)}%
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Nav tabs */}
        <div style={{ display:"flex",gap:4 }}>
          {TABS.map(t=>(
            <button key={t} onClick={()=>setActiveTab(t)}
              style={{ background:activeTab===t?K.ac:"none",border:`1px solid ${activeTab===t?K.ac:K.bd}`,
                       borderRadius:6,padding:"4px 10px",color:activeTab===t?K.bg:K.tm,
                       fontSize:9,fontFamily:K.mn,cursor:"pointer",textTransform:"uppercase",letterSpacing:1 }}>
              {t}
            </button>
          ))}
        </div>
      </div>

      {/* ── MAIN CONTENT ───────────────────────────────── */}
      <div style={{ flex:1,overflow:"hidden",display:"flex",gap:0,position:"relative" }}>

        {/* MAP TAB — the hero view */}
        {activeTab === "map" && (
          <div style={{ display:"flex",flex:1,gap:0,overflow:"hidden",position:"relative" }}>

            {/* Left: Disruption Feed */}
            <div style={{ width:270,borderRight:`1px solid ${K.bd}`,padding:14,overflowY:"auto",flexShrink:0 }}>
              <DisruptionFeed
                events={intel}
                hubScores={hubScores}
                isLive={intelData?.liveDataActive || false}
                onRefresh={handleRefresh}
              />
            </div>

            {/* Center: Leaflet Map */}
            <div style={{ flex:1,position:"relative",overflow:"hidden" }}>
              <LeafletMap
                allocations={current.allocations}
                hubScores={hubScores}
                weatherData={weather}
                optimizedRoutes={optRoutes}
                onNodeClick={setSelectedNode}
              />

              {/* Map legend overlay */}
              <div style={{ position:"absolute",bottom:16,left:16,background:"rgba(6,10,20,.85)",
                            border:`1px solid ${K.bd}`,borderRadius:8,padding:"8px 12px",zIndex:500 }}>
                <div style={{ display:"flex",gap:14,alignItems:"center" }}>
                  {[
                    {color:K.ac,label:"Active route"},
                    {color:"#60a5fa",label:"Ocean route"},
                    {color:K.rd,label:"Disrupted / rerouted"},
                    {color:K.or,label:"High disruption hub"},
                  ].map(l=>(
                    <div key={l.label} style={{ display:"flex",alignItems:"center",gap:5 }}>
                      <div style={{ width:20,height:2,background:l.color,borderRadius:1 }} />
                      <span style={{ fontSize:9,color:K.tm,fontFamily:K.mn }}>{l.label}</span>
                    </div>
                  ))}
                  <div style={{ fontSize:9,color:K.tf,fontFamily:K.mn }}>
                    Solver: {current.solverEngine || "Greedy (client)"}
                  </div>
                </div>
              </div>

              {/* Reroute status bar */}
              {rerouteCount > 0 && (
                <div style={{ position:"absolute",top:12,left:"50%",transform:"translateX(-50%)",
                              background:"rgba(248,113,113,.12)",border:`1px solid rgba(248,113,113,.4)`,
                              borderRadius:8,padding:"6px 14px",zIndex:500,display:"flex",alignItems:"center",gap:8 }}>
                  <div style={{ width:6,height:6,borderRadius:"50%",background:K.rd }} />
                  <span style={{ fontSize:10,fontFamily:K.mn,color:K.rd }}>
                    AUTO-REROUTED — {rerouteCount} route{rerouteCount!==1?"s":""} redirected due to live disruption signals
                  </span>
                </div>
              )}

              {/* Node drawer */}
              {selectedNode && (
                <div style={{ position:"absolute",top:0,right:0,height:"100%",zIndex:600 }}>
                  <NodeDrawer node={selectedNode} onClose={() => setSelectedNode(null)} />
                </div>
              )}
            </div>

            {/* Right: Predictions */}
            <div style={{ width:240,borderLeft:`1px solid ${K.bd}`,padding:14,overflowY:"auto",flexShrink:0 }}>
              <PredictionPanel predictions={predData} baseline={baseline} />
            </div>
          </div>
        )}

        {/* INTELLIGENCE TAB */}
        {activeTab === "intelligence" && (
          <div style={{ flex:1,padding:20,overflowY:"auto" }}>
            <div style={{ display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:16 }}>
              <div>
                <div style={{ fontSize:16,fontWeight:700,color:K.tx,fontFamily:K.ds }}>Live Disruption Intelligence</div>
                <div style={{ fontSize:11,color:K.tm,fontFamily:K.mn,marginTop:2 }}>
                  Powered by Serper.dev · {intel.length} events · Last refresh {lastRefresh.toLocaleTimeString()}
                  {!intelData?.liveDataActive && " · Set SERPER_API_KEY for live data"}
                </div>
              </div>
              <button onClick={handleRefresh}
                style={{ background:K.ac,border:"none",borderRadius:8,padding:"8px 16px",
                         color:K.bg,fontSize:11,fontFamily:K.mn,fontWeight:700,cursor:"pointer" }}>
                ↻ Refresh
              </button>
            </div>

            {/* Hub scores */}
            <div style={{ display:"flex",gap:8,flexWrap:"wrap",marginBottom:16 }}>
              {WH.map(wh => {
                const score = hubScores[wh.id] || 0;
                const color = score > 0.6 ? K.rd : score > 0.35 ? K.or : K.ac;
                return (
                  <div key={wh.id} style={{ background:K.sf,border:`1px solid ${color}33`,borderRadius:8,
                                            padding:"8px 12px",minWidth:120,flex:1 }}>
                    <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,marginBottom:4 }}>{wh.name}</div>
                    <div style={{ fontSize:20,fontWeight:700,color,fontFamily:K.ds }}>{(score*100).toFixed(0)}%</div>
                    <div style={{ height:3,background:"rgba(255,255,255,.04)",borderRadius:2,marginTop:5 }}>
                      <div style={{ height:"100%",width:`${score*100}%`,background:color,borderRadius:2 }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Event cards */}
            <div style={{ display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(320px,1fr))",gap:12 }}>
              {intel.map((ev,i) => {
                const meta = CAT_META[ev.category] || CAT_META.General;
                const score = ev.riskScore || 0;
                const color = score > 0.65 ? K.rd : score > 0.4 ? K.or : K.ac;
                const wh = WH.find(w => w.id === ev.hub_id);
                return (
                  <div key={i} style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:10,
                                        padding:14,borderLeft:`4px solid ${color}` }}>
                    <div style={{ display:"flex",justifyContent:"space-between",marginBottom:8 }}>
                      <div style={{ display:"flex",alignItems:"center",gap:8 }}>
                        <span style={{ fontSize:18 }}>{meta.icon}</span>
                        <div>
                          <Badge color={meta.color}>{ev.category}</Badge>
                          {wh && <span style={{ fontSize:9,color:K.tm,fontFamily:K.mn,marginLeft:6 }}>{wh.name}</span>}
                        </div>
                      </div>
                      <div style={{ fontSize:20,fontWeight:700,color,fontFamily:K.ds }}>{(score*100).toFixed(0)}</div>
                    </div>
                    <div style={{ fontSize:11,color:K.tx,fontFamily:K.mn,lineHeight:1.5,marginBottom:6 }}>{ev.title}</div>
                    <div style={{ fontSize:10,color:K.tm,fontFamily:K.mn,lineHeight:1.5 }}>{ev.snippet}</div>
                    <div style={{ marginTop:8,display:"flex",justifyContent:"space-between" }}>
                      <span style={{ fontSize:9,color:K.tf,fontFamily:K.mn }}>{ev.source}</span>
                      <span style={{ fontSize:9,color:K.tf,fontFamily:K.mn }}>{ev.date}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* PREDICTIONS TAB */}
        {activeTab === "predictions" && (
          <div style={{ flex:1,padding:20,overflowY:"auto",maxWidth:900,margin:"0 auto",width:"100%" }}>
            <div style={{ fontSize:16,fontWeight:700,color:K.tx,fontFamily:K.ds,marginBottom:4 }}>7-Day Predictive Analytics</div>
            <div style={{ fontSize:11,color:K.tm,fontFamily:K.mn,marginBottom:20 }}>
              EWMA forecast · Signal = 68% intelligence + 32% weather · Updated every 5 min
            </div>
            {predData ? (
              <>
                <div style={{ display:"grid",gridTemplateColumns:"repeat(3,1fr)",gap:12,marginBottom:20 }}>
                  <Stat label="Risk Level" value={predData.riskLevel} color={predData.riskColor} />
                  <Stat label="Stress Score" value={`${(predData.stressScore*100).toFixed(0)}%`} color={predData.riskColor} />
                  <Stat label="7-Day Cost Trend" value={`${predData.costTrend7d>0?"+":""}${predData.costTrend7d}%`} color={predData.costTrend7d>5?K.rd:predData.costTrend7d>0?K.or:K.ac} />
                </div>
                <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:12,padding:20,marginBottom:16 }}>
                  <div style={{ fontSize:12,fontWeight:700,color:K.tx,fontFamily:K.ds,marginBottom:12 }}>Daily Forecast</div>
                  <div style={{ display:"grid",gridTemplateColumns:"repeat(7,1fr)",gap:8 }}>
                    {predData.forecast.map((d,i)=>{
                      const riskColor = d.unmetRisk>0.5?K.rd:d.unmetRisk>0.3?K.or:K.ac;
                      return (
                        <div key={i} style={{ background:K.sfh,border:`1px solid ${K.bd}`,borderRadius:8,padding:"10px 8px",textAlign:"center" }}>
                          <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn }}>{d.date}</div>
                          <div style={{ fontSize:14,fontWeight:700,color:d.costChange>3?K.rd:d.costChange>0?K.or:K.ac,fontFamily:K.ds,marginTop:4 }}>
                            ${Math.round(d.cost/1000)}K
                          </div>
                          <div style={{ fontSize:9,color:K.tm,fontFamily:K.mn,marginTop:2 }}>{d.leadTime}d lead</div>
                          <div style={{ marginTop:6,height:3,background:"rgba(255,255,255,.04)",borderRadius:2 }}>
                            <div style={{ height:"100%",width:`${d.unmetRisk*100}%`,background:riskColor,borderRadius:2 }} />
                          </div>
                          <div style={{ fontSize:8,color:riskColor,fontFamily:K.mn,marginTop:2 }}>{(d.unmetRisk*100).toFixed(0)}% risk</div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <div style={{ color:K.tm,fontFamily:K.mn,fontSize:12 }}>Connect backend to enable predictions.</div>
            )}
          </div>
        )}

        {/* OPTIMIZER TAB */}
        {activeTab === "optimizer" && (
          <div style={{ flex:1,padding:20,overflowY:"auto" }}>
            <div style={{ fontSize:16,fontWeight:700,color:K.tx,fontFamily:K.ds,marginBottom:4 }}>Route Optimization</div>
            <div style={{ fontSize:11,color:K.tm,fontFamily:K.mn,marginBottom:16 }}>
              NetworkX Dijkstra · Composite weight = base cost + disruption penalty + weather penalty + lead time
            </div>
            <RoutePanel optimizedRoutes={optRoutes} hubScores={hubScores} />
            {optRoutes.length > 0 && (
              <div style={{ marginTop:20,display:"grid",gridTemplateColumns:"repeat(auto-fill,minmax(280px,1fr))",gap:10 }}>
                {optRoutes.map((r,i) => {
                  const color = r.isRerouted ? K.rd : r.disruptionPenalty > 5 ? K.or : K.ac;
                  return (
                    <div key={i} style={{ background:K.sf,border:`1px solid ${color}33`,borderRadius:10,padding:12,borderLeft:`3px solid ${color}` }}>
                      <div style={{ fontSize:11,fontWeight:700,color:K.tx,fontFamily:K.ds,marginBottom:4 }}>{r.customerName}</div>
                      <div style={{ fontSize:10,color:K.tm,fontFamily:K.mn,marginBottom:6 }}>→ {r.optimalWarehouseName}</div>
                      <div style={{ display:"flex",gap:8,flexWrap:"wrap" }}>
                        <Badge color={K.bl} small>{r.mode}</Badge>
                        <Badge color={K.yl} small>{r.leadTime}d lead</Badge>
                        {r.disruptionPenalty > 0 && <Badge color={K.or} small>+${r.disruptionPenalty?.toFixed(0)} disruption</Badge>}
                        {r.isRerouted && <Badge color={K.rd} small>REROUTED</Badge>}
                      </div>
                      {r.reroute && (
                        <div style={{ marginTop:8,padding:"6px 8px",background:K.sfh,borderRadius:6 }}>
                          <div style={{ fontSize:9,color:K.ac,fontFamily:K.mn }}>
                            Alt: {r.reroute.warehouseName} saves ${r.reroute.saving?.toFixed(0)}/unit
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* SCENARIOS TAB */}
        {activeTab === "scenarios" && (
          <div style={{ flex:1,padding:20,overflowY:"auto",maxWidth:900,margin:"0 auto",width:"100%" }}>
            <div style={{ fontSize:16,fontWeight:700,color:K.tx,fontFamily:K.ds,marginBottom:4 }}>What-If Scenario Planner</div>
            <div style={{ fontSize:11,color:K.tm,fontFamily:K.mn,marginBottom:16 }}>
              OptiGuide-style what-if analysis · MIP solver (backend) or greedy fallback (client)
            </div>
            <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:12,padding:16,marginBottom:16 }}>
              <ScenarioPlanner onResult={handleScenarioResult} />
            </div>
            {scenario && (
              <>
                <div style={{ display:"grid",gridTemplateColumns:"repeat(4,1fr)",gap:12,marginBottom:16 }}>
                  <Stat label="Cost" value={`$${Math.round(scenario.totalCost/1000)}K`} trend={costDelta} color={K.ac} />
                  <Stat label="Units" value={scenario.totalUnits?.toLocaleString()} color={K.bl} />
                  <Stat label="Lead" value={`${scenario.avgLeadTime}d`} trend={leadDelta} color={K.yl} />
                  <Stat label="Unmet" value={scenario.unmetDemand||0} color={scenario.unmetDemand>0?K.rd:K.ac} />
                </div>
                <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:12,padding:16,marginBottom:12 }}>
                  <div style={{ fontSize:12,fontWeight:700,fontFamily:K.ds,marginBottom:10 }}>Warehouse Utilization</div>
                  <Bars usage={scenario.warehouseUsage} />
                </div>
                {scenario.slaViolations?.length > 0 && (
                  <div style={{ background:"rgba(248,113,113,.08)",border:`1px solid rgba(248,113,113,.3)`,borderRadius:12,padding:14 }}>
                    <div style={{ fontSize:12,fontWeight:700,color:K.rd,fontFamily:K.ds,marginBottom:8 }}>SLA Violations</div>
                    {scenario.slaViolations.map((v,i)=>(
                      <div key={i} style={{ display:"flex",justifyContent:"space-between",fontSize:10,fontFamily:K.mn,color:K.tx,padding:"4px 0",borderBottom:`1px solid ${K.bd}` }}>
                        <span>{v.customer}</span>
                        <span style={{ color:K.rd }}>SLA {v.sla}d · Actual {v.actualLead}d</span>
                      </div>
                    ))}
                  </div>
                )}
                <div style={{ marginTop:12,fontSize:9,color:K.tf,fontFamily:K.mn }}>
                  Solver: {scenario.solverEngine || "client-side greedy"}
                  {scenario.solverStatus && ` · Status: ${scenario.solverStatus}`}
                </div>
              </>
            )}
          </div>
        )}

        {/* NETWORK TAB */}
        {activeTab === "network" && (
          <div style={{ flex:1,padding:20,overflowY:"auto" }}>
            <div style={{ fontSize:16,fontWeight:700,color:K.tx,fontFamily:K.ds,marginBottom:16 }}>Network Data</div>
            <div style={{ display:"grid",gridTemplateColumns:"1fr 1fr",gap:16 }}>
              <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:12,padding:14 }}>
                <div style={{ fontSize:12,fontWeight:700,fontFamily:K.ds,marginBottom:10 }}>Warehouses ({WH.length})</div>
                {WH.map(w=>(
                  <div key={w.id} style={{ display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:`1px solid ${K.bd}`,fontSize:10,fontFamily:K.mn }}>
                    <div>
                      <span style={{ color:K.tx }}>{w.name}</span>
                      <span style={{ color:K.tm,marginLeft:8 }}>{w.loc}</span>
                    </div>
                    <div style={{ color:K.tm }}>{w.stk.toLocaleString()} / {w.cap.toLocaleString()}</div>
                  </div>
                ))}
              </div>
              <div style={{ background:K.sf,border:`1px solid ${K.bd}`,borderRadius:12,padding:14 }}>
                <div style={{ fontSize:12,fontWeight:700,fontFamily:K.ds,marginBottom:10 }}>Customers ({CU.length})</div>
                {CU.map(c=>(
                  <div key={c.id} style={{ display:"flex",justifyContent:"space-between",padding:"5px 0",borderBottom:`1px solid ${K.bd}`,fontSize:10,fontFamily:K.mn }}>
                    <div>
                      <span style={{ color:K.tx }}>{c.name}</span>
                      <span style={{ color:K.tm,marginLeft:8,fontSize:9 }}>{c.pri}</span>
                    </div>
                    <span style={{ color:K.tm }}>{c.dem.toLocaleString()} units</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ── BOTTOM STATUS BAR ──────────────────────────── */}
      <div style={{ padding:"5px 20px",borderTop:`1px solid ${K.bd}`,background:K.sf,flexShrink:0,
                    display:"flex",alignItems:"center",justifyContent:"space-between" }}>
        <div style={{ display:"flex",gap:16,alignItems:"center" }}>
          <span style={{ fontSize:9,fontFamily:K.mn,color:K.tm }}>
            Solver: {current.solverEngine || "Greedy (client)"}
          </span>
          {rerouteCount > 0 && (
            <span style={{ fontSize:9,fontFamily:K.mn,color:K.rd }}>
              AUTO-REROUTED · {rerouteCount} route{rerouteCount!==1?"s":""} redirected
            </span>
          )}
          {highRisk > 0 && (
            <span style={{ fontSize:9,fontFamily:K.mn,color:K.or }}>
              {highRisk} HIGH-RISK EVENT{highRisk!==1?"S":""} ACTIVE
            </span>
          )}
        </div>
        <div style={{ display:"flex",gap:12,alignItems:"center" }}>
          <span style={{ fontSize:9,fontFamily:K.mn,color:K.tf }}>
            Intel: {intelData?.liveDataActive ? "🟢 LIVE" : "🟡 STATIC"} ·
            Weather: {weather.length > 0 ? "🟢 LIVE" : "⏳"} ·
            Routes: {optRoutes.length > 0 ? "🟢 ACTIVE" : "–"} ·
            {lastRefresh.toLocaleTimeString()}
          </span>
        </div>
      </div>

    </div>
  );
}

// Mount app
const _root = ReactDOM.createRoot(document.getElementById("root"));
_root.render(React.createElement(App));
