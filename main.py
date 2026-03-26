"""
Supply Chain Intelligence v3.0 — Backend API
=============================================
OptiGuide Architecture Extension (arXiv 2307.03875v2)
Built by Atharva | Franz Edelman 2026

NEW in v3.0:
- External Intelligence Engine: Serper.dev live disruption monitoring + NLP scoring
- Open-Meteo weather risk for all hub locations (free, no API key required)
- PuLP MIP Solver — replaces greedy allocation (implements arXiv §2.4 formulation)
- NetworkX route optimization with disruption + weather composite penalties
- EWMA-based 7-day prediction engine for cost, lead time, and unmet demand risk
- SQLite caching layer for all external data (intelligent TTL management)
- APScheduler: background intelligence + weather refresh every 3 hours
- All v2 endpoints preserved for backward compatibility
"""

import os, json, re, math, time, uuid, sqlite3, random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests

# ── Optional heavy deps — graceful fallback if not yet installed ──────────────
try:
    from pulp import (LpProblem, LpVariable, lpSum, LpMinimize,
                      PULP_CBC_CMD, value as lp_value, LpStatus)
    PULP_AVAILABLE = True
except ImportError:
    PULP_AVAILABLE = False

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    SCHEDULER_AVAILABLE = True
except ImportError:
    SCHEDULER_AVAILABLE = False

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════
SERPER_API_KEY  = os.environ.get("SERPER_API_KEY", "")          # serper.dev — 2500 free/mo
HF_API_TOKEN    = os.environ.get("HF_API_TOKEN", "")            # HuggingFace (unchanged)
LLAMA_MODEL     = "meta-llama/Meta-Llama-3.1-8B-Instruct"
FALLBACK_MODEL  = "mistralai/Mistral-7B-Instruct-v0.3"
HF_API_URL      = f"https://api-inference.huggingface.co/models/{LLAMA_MODEL}"
HF_FALLBACK_URL = f"https://api-inference.huggingface.co/models/{FALLBACK_MODEL}"
DB_PATH         = os.environ.get("SQLITE_DB_PATH", "sc_intelligence.db")
INTEL_REFRESH_H = int(os.environ.get("INTEL_REFRESH_HOURS", "3"))

app = FastAPI(
    title="Supply Chain Intelligence API v3.0",
    description="MIP Optimization · Live Intelligence · Predictive Analytics · OptiGuide",
    version="3.0.0",
)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════════════════════
# SQLITE CACHE
# ═══════════════════════════════════════════════════════════════════════════════
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS intelligence_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hub_id TEXT NOT NULL, title TEXT, snippet TEXT,
        source TEXT, link TEXT, category TEXT DEFAULT 'General',
        risk_score REAL DEFAULT 0.2, fetched_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS weather_cache (
        hub_id TEXT PRIMARY KEY,
        weather_json TEXT NOT NULL, fetched_at TEXT NOT NULL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS route_cache (
        cache_key TEXT PRIMARY KEY,
        result_json TEXT NOT NULL, fetched_at TEXT NOT NULL
    )""")
    conn.commit(); conn.close()

init_db()

# ═══════════════════════════════════════════════════════════════════════════════
# DATA CONNECTOR ARCHITECTURE (unchanged from v2)
# ═══════════════════════════════════════════════════════════════════════════════
class DataConnector:
    def get_warehouses(self) -> List[Dict]: raise NotImplementedError
    def get_customers(self) -> List[Dict]: raise NotImplementedError
    def get_routes(self) -> List[Dict]: raise NotImplementedError
    def get_products(self) -> List[Dict]: raise NotImplementedError
    def get_inventory_levels(self) -> Dict[str, int]: raise NotImplementedError
    def get_active_orders(self) -> List[Dict]: return []
    def get_disruption_feeds(self) -> List[Dict]: return []
    @property
    def connector_type(self) -> str: return "base"
    @property
    def connector_name(self) -> str: return "Base Connector"


class SyntheticDataConnector(DataConnector):
    """Synthetic data modeled on Vertiv's global DC infrastructure supply chain."""
    @property
    def connector_type(self): return "synthetic"
    @property
    def connector_name(self): return "Synthetic (Vertiv-modeled) v3"

    def get_warehouses(self):
        return [
            {"id":"WH-PHX","name":"Phoenix Hub","location":"Phoenix, AZ","lat":33.45,"lng":-112.07,"capacity":12000,"currentStock":9200,"type":"Primary DC","specialization":"UPS & Thermal","operatingCostPerUnit":2.1,"region":"NA"},
            {"id":"WH-CLT","name":"Charlotte Facility","location":"Charlotte, NC","lat":35.23,"lng":-80.84,"capacity":8500,"currentStock":6100,"type":"Regional DC","specialization":"Power Distribution","operatingCostPerUnit":1.8,"region":"NA"},
            {"id":"WH-SJC","name":"San Jose Center","location":"San Jose, CA","lat":37.34,"lng":-121.89,"capacity":6000,"currentStock":4800,"type":"Regional DC","specialization":"Cooling Systems","operatingCostPerUnit":2.5,"region":"NA"},
            {"id":"WH-DFW","name":"Dallas Mega Hub","location":"Dallas, TX","lat":32.78,"lng":-96.80,"capacity":15000,"currentStock":11500,"type":"Primary DC","specialization":"Full Portfolio","operatingCostPerUnit":1.6,"region":"NA"},
            {"id":"WH-CHI","name":"Chicago North","location":"Chicago, IL","lat":41.88,"lng":-87.63,"capacity":7000,"currentStock":5300,"type":"Regional DC","specialization":"IT Infrastructure","operatingCostPerUnit":1.9,"region":"NA"},
            {"id":"WH-MUM","name":"Mumbai Gateway","location":"Mumbai, India","lat":19.08,"lng":72.88,"capacity":10000,"currentStock":7600,"type":"International Hub","specialization":"APAC Distribution","operatingCostPerUnit":1.2,"region":"APAC"},
            {"id":"WH-SNG","name":"Singapore Hub","location":"Singapore","lat":1.35,"lng":103.82,"capacity":9000,"currentStock":6900,"type":"International Hub","specialization":"APAC Cooling","operatingCostPerUnit":2.0,"region":"APAC"},
            {"id":"WH-FRA","name":"Frankfurt Center","location":"Frankfurt, Germany","lat":50.11,"lng":8.68,"capacity":8000,"currentStock":5500,"type":"International Hub","specialization":"EMEA Distribution","operatingCostPerUnit":2.3,"region":"EMEA"},
        ]

    def get_customers(self):
        return [
            {"id":"C-AWS-VA","name":"AWS Virginia","location":"Ashburn, VA","lat":39.04,"lng":-77.47,"demandUnits":2400,"priority":"Critical","segment":"Hyperscale","slaLeadDays":3},
            {"id":"C-MSFT-WA","name":"Microsoft Quincy","location":"Quincy, WA","lat":47.23,"lng":-119.85,"demandUnits":1800,"priority":"Critical","segment":"Hyperscale","slaLeadDays":4},
            {"id":"C-META-OR","name":"Meta Prineville","location":"Prineville, OR","lat":44.30,"lng":-120.73,"demandUnits":1500,"priority":"High","segment":"Hyperscale","slaLeadDays":4},
            {"id":"C-GOOG-SC","name":"Google SC","location":"The Dalles, OR","lat":45.59,"lng":-121.18,"demandUnits":2000,"priority":"Critical","segment":"Hyperscale","slaLeadDays":3},
            {"id":"C-EQX-SV","name":"Equinix SV5","location":"San Jose, CA","lat":37.39,"lng":-121.95,"demandUnits":800,"priority":"High","segment":"Colocation","slaLeadDays":2},
            {"id":"C-DLR-TX","name":"Digital Realty TX","location":"Dallas, TX","lat":32.82,"lng":-96.75,"demandUnits":950,"priority":"High","segment":"Colocation","slaLeadDays":2},
            {"id":"C-REL-MUM","name":"Reliance Jio DC","location":"Navi Mumbai, India","lat":19.03,"lng":73.03,"demandUnits":1200,"priority":"High","segment":"Telecom","slaLeadDays":5},
            {"id":"C-SING-TEL","name":"Singtel DC","location":"Singapore","lat":1.30,"lng":103.85,"demandUnits":700,"priority":"Medium","segment":"Telecom","slaLeadDays":5},
            {"id":"C-EQNX-FRA","name":"Equinix FR5","location":"Frankfurt, Germany","lat":50.08,"lng":8.72,"demandUnits":650,"priority":"Medium","segment":"Colocation","slaLeadDays":3},
            {"id":"C-JPM-NJ","name":"JPMorgan Metro","location":"Jersey City, NJ","lat":40.73,"lng":-74.04,"demandUnits":500,"priority":"Critical","segment":"Enterprise","slaLeadDays":2},
        ]

    def get_routes(self):
        return [
            {"id":"R001","from":"WH-CLT","to":"C-AWS-VA","distance":400,"costPerUnit":12.5,"leadTimeDays":1,"tariffPct":0,"mode":"Ground"},
            {"id":"R002","from":"WH-DFW","to":"C-AWS-VA","distance":1300,"costPerUnit":28.0,"leadTimeDays":3,"tariffPct":0,"mode":"Ground"},
            {"id":"R003","from":"WH-PHX","to":"C-MSFT-WA","distance":1400,"costPerUnit":31.0,"leadTimeDays":3,"tariffPct":0,"mode":"Ground"},
            {"id":"R004","from":"WH-SJC","to":"C-MSFT-WA","distance":800,"costPerUnit":19.5,"leadTimeDays":2,"tariffPct":0,"mode":"Ground"},
            {"id":"R005","from":"WH-SJC","to":"C-META-OR","distance":550,"costPerUnit":15.0,"leadTimeDays":2,"tariffPct":0,"mode":"Ground"},
            {"id":"R006","from":"WH-SJC","to":"C-GOOG-SC","distance":600,"costPerUnit":16.0,"leadTimeDays":2,"tariffPct":0,"mode":"Ground"},
            {"id":"R007","from":"WH-DFW","to":"C-GOOG-SC","distance":1800,"costPerUnit":35.0,"leadTimeDays":4,"tariffPct":0,"mode":"Ground"},
            {"id":"R008","from":"WH-SJC","to":"C-EQX-SV","distance":10,"costPerUnit":3.0,"leadTimeDays":0.5,"tariffPct":0,"mode":"Local"},
            {"id":"R009","from":"WH-DFW","to":"C-DLR-TX","distance":15,"costPerUnit":3.5,"leadTimeDays":0.5,"tariffPct":0,"mode":"Local"},
            {"id":"R010","from":"WH-MUM","to":"C-REL-MUM","distance":30,"costPerUnit":4.0,"leadTimeDays":1,"tariffPct":5,"mode":"Local"},
            {"id":"R011","from":"WH-SNG","to":"C-SING-TEL","distance":20,"costPerUnit":5.0,"leadTimeDays":1,"tariffPct":3,"mode":"Local"},
            {"id":"R012","from":"WH-FRA","to":"C-EQNX-FRA","distance":15,"costPerUnit":4.5,"leadTimeDays":0.5,"tariffPct":2,"mode":"Local"},
            {"id":"R013","from":"WH-CLT","to":"C-JPM-NJ","distance":600,"costPerUnit":18.0,"leadTimeDays":2,"tariffPct":0,"mode":"Ground"},
            {"id":"R014","from":"WH-PHX","to":"C-DLR-TX","distance":1000,"costPerUnit":24.0,"leadTimeDays":3,"tariffPct":0,"mode":"Ground"},
            {"id":"R015","from":"WH-CHI","to":"C-AWS-VA","distance":700,"costPerUnit":20.0,"leadTimeDays":2,"tariffPct":0,"mode":"Ground"},
            {"id":"R016","from":"WH-CHI","to":"C-JPM-NJ","distance":790,"costPerUnit":21.0,"leadTimeDays":2,"tariffPct":0,"mode":"Ground"},
            {"id":"R017","from":"WH-DFW","to":"C-META-OR","distance":1900,"costPerUnit":38.0,"leadTimeDays":4,"tariffPct":0,"mode":"Ground"},
            {"id":"R018","from":"WH-SNG","to":"C-REL-MUM","distance":3900,"costPerUnit":65.0,"leadTimeDays":7,"tariffPct":8,"mode":"Ocean"},
            {"id":"R019","from":"WH-FRA","to":"C-SING-TEL","distance":10000,"costPerUnit":85.0,"leadTimeDays":14,"tariffPct":6,"mode":"Ocean"},
            {"id":"R020","from":"WH-MUM","to":"C-SING-TEL","distance":3200,"costPerUnit":55.0,"leadTimeDays":5,"tariffPct":4,"mode":"Ocean"},
        ]

    def get_products(self):
        return [
            {"id":"P-UPS","name":"Liebert UPS Systems","category":"Power Protection","unitCost":8500},
            {"id":"P-PDU","name":"Power Distribution Units","category":"Power Distribution","unitCost":3200},
            {"id":"P-COOL","name":"Liebert Cooling Units","category":"Thermal Management","unitCost":15000},
            {"id":"P-RACK","name":"VR Rack Systems","category":"IT Infrastructure","unitCost":2800},
            {"id":"P-MON","name":"Trellis Monitoring","category":"Software/Monitoring","unitCost":500},
        ]

    def get_inventory_levels(self):
        return {w["id"]: w["currentStock"] for w in self.get_warehouses()}


ACTIVE_CONNECTOR: DataConnector = SyntheticDataConnector()
WAREHOUSES  = ACTIVE_CONNECTOR.get_warehouses()
CUSTOMERS   = ACTIVE_CONNECTOR.get_customers()
ROUTES      = ACTIVE_CONNECTOR.get_routes()
PRODUCTS    = ACTIVE_CONNECTOR.get_products()
WH_MAP      = {w["id"]: w for w in WAREHOUSES}
CUST_MAP    = {c["id"]: c for c in CUSTOMERS}
ROUTE_MAP   = {r["id"]: r for r in ROUTES}
SEGMENT_MAP = {
    "hyperscale": ["C-AWS-VA","C-MSFT-WA","C-META-OR","C-GOOG-SC"],
    "colocation":  ["C-EQX-SV","C-DLR-TX","C-EQNX-FRA"],
    "telecom":     ["C-REL-MUM","C-SING-TEL"],
    "enterprise":  ["C-JPM-NJ"],
}

# ═══════════════════════════════════════════════════════════════════════════════
# EXTERNAL INTELLIGENCE: NLP KEYWORD CLASSIFIER
# ═══════════════════════════════════════════════════════════════════════════════
DISRUPTION_KEYWORDS = {
    "Weather":     ["typhoon","hurricane","flood","storm","earthquake","cyclone","snow","fog","heat wave","tornado"],
    "Logistics":   ["port congestion","strike","backlog","delay","shutdown","closure","blockage","capacity crunch","vessel waiting"],
    "Geopolitical":["tariff","sanction","trade war","export ban","import restriction","political","conflict","embargo"],
    "Supply":      ["shortage","out of stock","supply disruption","material shortage","chip shortage","component delay","allocation"],
    "Security":    ["cyber","ransomware","attack","breach","hack","system outage","it incident"],
}
SEVERITY_BOOST  = ["critical","severe","major","significant","emergency","urgent","record","unprecedented"]
SEVERITY_REDUCE = ["minor","slight","potential","possible","expected","resolved","normal","recovered"]

def classify_and_score(text: str):
    t = text.lower()
    cat_scores = {cat: sum(1 for kw in kws if kw in t) for cat, kws in DISRUPTION_KEYWORDS.items()}
    best_cat   = max(cat_scores, key=cat_scores.get) if max(cat_scores.values()) > 0 else "General"
    base       = 0.45
    base      += sum(0.08 for w in SEVERITY_BOOST if w in t)
    base      -= sum(0.07 for w in SEVERITY_REDUCE if w in t)
    return best_cat, round(min(0.95, max(0.1, base)), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# SERPER INTELLIGENCE SERVICE
# ═══════════════════════════════════════════════════════════════════════════════
HUB_QUERIES = {
    "WH-PHX": ["Phoenix Arizona logistics disruption freight","Arizona supply chain delays"],
    "WH-CLT": ["Charlotte NC port freight disruption","Southeast US logistics strike"],
    "WH-SJC": ["Los Angeles Long Beach port congestion delay","Bay Area logistics disruption"],
    "WH-DFW": ["Dallas Fort Worth freight rail logistics disruption","Texas supply chain"],
    "WH-CHI": ["Chicago intermodal rail freight disruption","Midwest logistics capacity"],
    "WH-MUM": ["Mumbai JNPT port disruption congestion","India supply chain logistics"],
    "WH-SNG": ["Singapore port congestion shipping delay","Straits of Malacca disruption"],
    "WH-FRA": ["Frankfurt logistics disruption Europe freight","European supply chain strike"],
}

STATIC_INTEL_FALLBACK = [
    {"hub_id":"WH-SNG","title":"Singapore Strait: 15% Rise in Vessel Waiting Times","snippet":"Port Authority Singapore reports container backlog; average anchorage wait increased to 18 hours amid APAC trade surge.","source":"Lloyd's List","category":"Logistics","riskScore":0.72,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-MUM","title":"Mumbai JNPT Faces Monsoon-Related Delays","snippet":"Intermittent operations at Jawaharlal Nehru Port Trust; 3-5 day berthing delays expected through season.","source":"Shipping Gazette","category":"Weather","riskScore":0.65,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-FRA","title":"European Freight Rates Rising on Labor Talks","snippet":"Port worker negotiations in Germany and Netherlands raise strike risk; spot rates on intra-EU lanes up 12%.","source":"FreightWaves","category":"Logistics","riskScore":0.58,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-DFW","title":"Texas Rail Corridor Capacity Constrained","snippet":"Union Pacific reports 8% decline in freight velocity across Dallas corridor; 2-day processing delays at mega-hub.","source":"Railway Age","category":"Logistics","riskScore":0.61,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-SJC","title":"LA/Long Beach Dwell Times Averaging 4.2 Days","snippet":"Container dwell times at San Pedro Bay ports exceed 4-day threshold vs 2.8d baseline; equipment shortages cited.","source":"Port of LA","category":"Logistics","riskScore":0.69,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-PHX","title":"Southwest US Extreme Heat Affecting Ground Freight","snippet":"Trucking firms limiting peak-afternoon operations across Arizona and Nevada amid heat advisories.","source":"NOAA","category":"Weather","riskScore":0.45,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-CHI","title":"Chicago Intermodal at 94% Baseline Throughput","snippet":"Following rail labor negotiations, Chicago hub operations have largely normalized. Minor congestion persists on I-80.","source":"Progressive Railroading","category":"Logistics","riskScore":0.28,"date":"Live feed unavailable — configure SERPER_API_KEY"},
    {"hub_id":"WH-CLT","title":"Southeast US Corridor Performing Above Average","snippet":"Charlotte and Atlanta DCs reporting above-baseline throughput; no significant disruptions on Eastern Seaboard.","source":"DC Velocity","category":"General","riskScore":0.15,"date":"Live feed unavailable — configure SERPER_API_KEY"},
]

def _fetch_serper(hub_id: str, queries: List[str]) -> List[Dict]:
    if not SERPER_API_KEY:
        return []
    results = []
    for q in queries[:2]:  # 2 queries/hub × 8 hubs = 16 searches per refresh
        try:
            r = requests.post(
                "https://google.serper.dev/news",
                headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": q, "num": 4, "gl": "us"},
                timeout=10,
            )
            if r.status_code == 200:
                for item in r.json().get("news", []):
                    cat, score = classify_and_score(item.get("title","") + " " + item.get("snippet",""))
                    if score >= 0.3:
                        results.append({
                            "hub_id": hub_id,
                            "title":   item.get("title","")[:120],
                            "snippet": item.get("snippet","")[:240],
                            "source":  item.get("source",""),
                            "link":    item.get("link",""),
                            "date":    item.get("date",""),
                            "category": cat,
                            "riskScore": score,
                        })
        except Exception as e:
            print(f"[Serper] Error for {hub_id}: {e}")
        time.sleep(0.3)
    return results

def _cache_intel(hub_id: str, items: List[Dict]):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("DELETE FROM intelligence_cache WHERE hub_id=?", (hub_id,))
    now = datetime.utcnow().isoformat()
    for it in items:
        c.execute(
            "INSERT INTO intelligence_cache (hub_id,title,snippet,source,link,category,risk_score,fetched_at) VALUES (?,?,?,?,?,?,?,?)",
            (hub_id, it["title"], it["snippet"], it["source"], it.get("link",""), it["category"], it["riskScore"], now)
        )
    conn.commit(); conn.close()

def _read_intel_cache(max_age_h: int = 6) -> List[Dict]:
    conn   = sqlite3.connect(DB_PATH)
    c      = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(hours=max_age_h)).isoformat()
    c.execute("SELECT hub_id,title,snippet,source,link,category,risk_score,fetched_at FROM intelligence_cache WHERE fetched_at>?", (cutoff,))
    rows = c.fetchall(); conn.close()
    return [{"hub_id":r[0],"title":r[1],"snippet":r[2],"source":r[3],"link":r[4],
              "category":r[5],"riskScore":r[6],"date":r[7][:10]} for r in rows]

def refresh_intelligence():
    """Background job: pull fresh Serper intelligence for all hubs."""
    print(f"[Intel] Refresh at {datetime.utcnow().isoformat()}")
    for hub_id, queries in HUB_QUERIES.items():
        items = _fetch_serper(hub_id, queries)
        if items:
            _cache_intel(hub_id, items)
    print(f"[Intel] Done")

def get_live_intelligence() -> List[Dict]:
    cached = _read_intel_cache(max_age_h=6)
    if cached:
        return sorted(cached, key=lambda x: x.get("riskScore", 0), reverse=True)
    return sorted(STATIC_INTEL_FALLBACK, key=lambda x: x.get("riskScore", 0), reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# OPEN-METEO WEATHER SERVICE  (free · no API key · WMO standard codes)
# ═══════════════════════════════════════════════════════════════════════════════
WMO_SEVERITY = {
    0:0.0, 1:0.05, 2:0.1, 3:0.15,
    45:0.25, 48:0.30,
    51:0.20, 53:0.25, 55:0.35,
    61:0.30, 63:0.45, 65:0.60,
    71:0.40, 73:0.50, 75:0.65,
    77:0.55, 80:0.35, 81:0.45, 82:0.60,
    85:0.50, 86:0.65,
    95:0.70, 96:0.80, 99:0.90,
}
WMO_DESC = {
    0:"Clear skies",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",
    45:"Foggy",48:"Icy fog",51:"Light drizzle",61:"Light rain",
    63:"Moderate rain",65:"Heavy rain",71:"Light snow",80:"Rain showers",
    95:"Thunderstorm",96:"Thunderstorm+hail",99:"Severe thunderstorm",
}

def _fetch_weather(hub_id: str, lat: float, lng: float) -> Dict:
    try:
        r = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={"latitude":lat,"longitude":lng,
                    "current":"temperature_2m,wind_speed_10m,weather_code,precipitation",
                    "forecast_days":1,"timezone":"auto"},
            timeout=8,
        )
        if r.status_code == 200:
            d    = r.json().get("current", {})
            code = d.get("weather_code", 0)
            wind = d.get("wind_speed_10m", 0)
            sev  = WMO_SEVERITY.get(code, 0.1) + min(0.4, wind / 100)
            sev  = round(min(1.0, sev), 3)
            return {
                "hub_id": hub_id,
                "temperature": d.get("temperature_2m"),
                "windSpeed": wind,
                "precipitation": d.get("precipitation", 0),
                "weatherCode": code,
                "description": WMO_DESC.get(code, "Unknown"),
                "severity": sev,
                "leadTimeImpact": round(sev * 0.28, 3),
                "costImpact": round(sev * 0.14, 3),
                "fetchedAt": datetime.utcnow().isoformat() + "Z",
            }
    except Exception as e:
        print(f"[Weather] Error for {hub_id}: {e}")
    return {"hub_id":hub_id,"temperature":None,"windSpeed":None,"precipitation":0,
            "weatherCode":None,"description":"Unavailable","severity":0,
            "leadTimeImpact":0,"costImpact":0,"fetchedAt":datetime.utcnow().isoformat()+"Z"}

def refresh_weather():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    for wh in WAREHOUSES:
        w = _fetch_weather(wh["id"], wh["lat"], wh["lng"])
        c.execute("INSERT OR REPLACE INTO weather_cache VALUES (?,?,?)",
                  (wh["id"], json.dumps(w), now))
        time.sleep(0.15)
    conn.commit(); conn.close()

def get_live_weather() -> List[Dict]:
    conn   = sqlite3.connect(DB_PATH)
    c      = conn.cursor()
    cutoff = (datetime.utcnow() - timedelta(hours=1)).isoformat()
    c.execute("SELECT weather_json FROM weather_cache WHERE fetched_at>?", (cutoff,))
    rows = c.fetchall(); conn.close()
    if len(rows) >= len(WAREHOUSES) * 0.6:
        return [json.loads(r[0]) for r in rows]
    # Cache miss — fetch live
    refresh_weather()
    conn   = sqlite3.connect(DB_PATH)
    c      = conn.cursor()
    c.execute("SELECT weather_json FROM weather_cache")
    rows = c.fetchall(); conn.close()
    return [json.loads(r[0]) for r in rows]


# ═══════════════════════════════════════════════════════════════════════════════
# HUB DISRUPTION SCORES  (intelligence + weather → per-hub float 0-1)
# ═══════════════════════════════════════════════════════════════════════════════
def compute_hub_scores(intel: List[Dict], weather: List[Dict]) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    for e in intel:
        h = e.get("hub_id")
        if h:
            scores[h] = min(1.0, scores.get(h, 0) + e.get("riskScore", 0) * 0.55)
    for w in weather:
        h = w.get("hub_id")
        if h:
            scores[h] = min(1.0, scores.get(h, 0) + w.get("severity", 0) * 0.30)
    return {k: round(v, 3) for k, v in scores.items()}


# ═══════════════════════════════════════════════════════════════════════════════
# PuLP MIP SOLVER  (arXiv 2307.03875 §2.4 Transportation Problem)
# ═══════════════════════════════════════════════════════════════════════════════
def _solve_mip(warehouses, customers, routes, modifiers=None, hub_scores=None):
    modifiers  = modifiers or {}
    hub_scores = hub_scores or {}

    disabled_wh  = set(modifiers.get("disabled_warehouses", []))
    disabled_rt  = set(modifiers.get("disabled_routes", []))
    tariff_mod   = modifiers.get("tariff_modifier", {})
    demand_mod   = modifiers.get("demand_modifier", {})
    capacity_mod = modifiers.get("capacity_modifier", {})

    active_wh = {
        w["id"]: {**w, "effectiveStock": max(0, w["currentStock"] + capacity_mod.get(w["id"], 0))}
        for w in warehouses if w["id"] not in disabled_wh
    }

    route_costs = {}
    route_obj   = {}
    for r in routes:
        if r["id"] in disabled_rt or r["from"] not in active_wh:
            continue
        t_mod  = tariff_mod.get(r["id"], tariff_mod.get(r["from"], 0))
        eff_t  = r["tariffPct"] + t_mod
        base_c = r["costPerUnit"] * (1 + eff_t / 100)
        # Disruption surcharge: intelligence + weather signal from hub
        disrupt_surcharge = hub_scores.get(r["from"], 0) * r["costPerUnit"] * 0.45
        route_costs[r["id"]] = round(base_c + disrupt_surcharge, 4)
        route_obj[r["id"]]   = r

    if not route_costs:
        return _empty()

    prob  = LpProblem("sc_v3_mip", LpMinimize)
    x     = {rid: LpVariable(f"x_{rid}", lowBound=0) for rid in route_costs}
    slack = {c["id"]: LpVariable(f"s_{c['id']}", lowBound=0) for c in customers}

    UNMET_PENALTY = 999_999
    prob += lpSum(x[rid] * route_costs[rid] for rid in x) + \
           lpSum(slack[cid] * UNMET_PENALTY for cid in slack)

    # Capacity constraints (arXiv eq. "supplier capacity constraint")
    for wh_id, wh in active_wh.items():
        wh_routes = [rid for rid in route_costs if route_obj[rid]["from"] == wh_id]
        if wh_routes:
            prob += lpSum(x[rid] for rid in wh_routes) <= wh["effectiveStock"], f"cap_{wh_id}"

    # Demand constraints (arXiv eq. "demand constraint" with slack = unmet demand)
    for cu in customers:
        dem  = max(0, cu["demandUnits"] + demand_mod.get(cu["id"], 0))
        c_rt = [rid for rid in route_costs if route_obj[rid]["to"] == cu["id"]]
        if c_rt:
            prob += lpSum(x[rid] for rid in c_rt) + slack[cu["id"]] == dem, f"dem_{cu['id']}"
        else:
            prob += slack[cu["id"]] == dem, f"dem_noroute_{cu['id']}"

    prob.solve(PULP_CBC_CMD(msg=0, timeLimit=15))

    allocs, wh_usage = [], {}
    total_cost = total_units = 0

    for wh_id, wh in active_wh.items():
        wh_usage[wh_id] = {"id":wh_id,"name":wh["name"],
                           "capacity":wh["effectiveStock"],"stock":wh["effectiveStock"],
                           "allocated":0,"remaining":wh["effectiveStock"],"utilization":0}

    for rid, var in x.items():
        units = lp_value(var) or 0
        if units < 0.5:
            continue
        r    = route_obj[rid]
        wh   = active_wh.get(r["from"], {})
        cu   = CUST_MAP.get(r["to"], {})
        cost = units * route_costs[rid]
        allocs.append({
            "route":rid,"from":r["from"],"to":r["to"],
            "fromName":wh.get("name",r["from"]),"toName":cu.get("name",r["to"]),
            "units":round(units),"cost":round(cost,2),"costPerUnit":route_costs[rid],
            "leadTimeDays":r["leadTimeDays"],"mode":r["mode"],"distance":r["distance"],
            "disruptionSurcharge":round(hub_scores.get(r["from"],0)*r["costPerUnit"]*0.45,2),
        })
        wu = wh_usage.get(r["from"])
        if wu:
            wu["allocated"] += round(units)
        total_cost  += cost
        total_units += round(units)

    for wu in wh_usage.values():
        wu["remaining"] = max(0, wu["capacity"] - wu["allocated"])
        wu["utilization"] = round(wu["allocated"] / wu["capacity"] * 100, 1) if wu["capacity"] > 0 else 0

    unmet    = sum(lp_value(s) or 0 for s in slack.values())
    avg_lead = sum(a["leadTimeDays"]*a["units"] for a in allocs) / max(total_units, 1)

    sla_violations = []
    for cu in customers:
        cu_allocs = [a for a in allocs if a["to"] == cu["id"]]
        if not cu_allocs:
            continue
        max_lead = max(a["leadTimeDays"] for a in cu_allocs)
        if max_lead > cu.get("slaLeadDays", 999):
            sla_violations.append({"customer":cu["name"],"customerId":cu["id"],
                "sla":cu["slaLeadDays"],"actualLead":max_lead,"priority":cu["priority"]})

    return {
        "totalCost":round(total_cost,2),"totalUnits":total_units,
        "unmetDemand":round(unmet),"avgLeadTime":round(avg_lead,1),
        "routeCount":len(allocs),"allocations":allocs,
        "warehouseUsage":list(wh_usage.values()),"slaViolations":sla_violations,
        "solverStatus":LpStatus.get(prob.status,"Unknown"),"solverEngine":"PuLP-CBC (MIP)",
    }


def _solve_greedy(warehouses, customers, routes, modifiers=None, hub_scores=None):
    """Greedy fallback solver — identical logic to v2 but accepts hub_scores param."""
    modifiers  = modifiers or {}
    hub_scores = hub_scores or {}
    disabled_wh  = set(modifiers.get("disabled_warehouses", []))
    disabled_rt  = set(modifiers.get("disabled_routes", []))
    tariff_mod   = modifiers.get("tariff_modifier", {})
    demand_mod   = modifiers.get("demand_modifier", {})
    capacity_mod = modifiers.get("capacity_modifier", {})

    wh_state = {}
    for w in warehouses:
        if w["id"] in disabled_wh: continue
        eff = max(0, w["currentStock"] + capacity_mod.get(w["id"], 0))
        wh_state[w["id"]] = {**w,"effectiveCapacity":eff,"effectiveStock":eff,"allocated":0,"remaining":eff}

    sorted_cu = sorted(customers, key=lambda c: {"Critical":0,"High":1,"Medium":2,"Low":3}.get(c["priority"],3))
    allocs, total_cost, total_units, unmet, sla_v = [], 0, 0, 0, []

    for cu in sorted_cu:
        dem = max(0, cu["demandUnits"] + demand_mod.get(cu["id"], 0))
        avail = []
        for r in routes:
            if r["to"] != cu["id"] or r["id"] in disabled_rt or r["from"] not in wh_state: continue
            t_mod = tariff_mod.get(r["id"], tariff_mod.get(r["from"], 0))
            eff_t = r["tariffPct"] + t_mod
            eff_c = r["costPerUnit"] * (1 + eff_t/100) + hub_scores.get(r["from"],0)*r["costPerUnit"]*0.45
            avail.append({**r,"effectiveCost":round(eff_c,2)})
        avail.sort(key=lambda r: r["effectiveCost"])

        max_lead = 0
        for r in avail:
            if dem <= 0: break
            wh = wh_state.get(r["from"])
            if not wh or wh["remaining"] <= 0: continue
            ship = min(dem, wh["remaining"])
            cost = ship * r["effectiveCost"]
            allocs.append({"route":r["id"],"from":r["from"],"to":cu["id"],
                "fromName":wh["name"],"toName":cu["name"],
                "units":ship,"cost":round(cost,2),"costPerUnit":r["effectiveCost"],
                "leadTimeDays":r["leadTimeDays"],"mode":r["mode"],"distance":r["distance"]})
            wh["allocated"] += ship; wh["remaining"] -= ship
            total_cost += cost; total_units += ship; dem -= ship
            max_lead = max(max_lead, r["leadTimeDays"])
        if dem > 0: unmet += dem
        if max_lead > cu.get("slaLeadDays", 999) and max_lead > 0:
            sla_v.append({"customer":cu["name"],"customerId":cu["id"],
                "sla":cu["slaLeadDays"],"actualLead":max_lead,"priority":cu["priority"]})

    avg_lead = sum(a["leadTimeDays"]*a["units"] for a in allocs) / max(total_units, 1)
    wh_usage = [{"id":k,"name":v["name"],"capacity":v["effectiveCapacity"],
        "stock":v["effectiveStock"],"allocated":v["allocated"],"remaining":v["remaining"],
        "utilization":round(v["allocated"]/v["effectiveCapacity"]*100,1) if v["effectiveCapacity"]>0 else 0}
        for k,v in wh_state.items()]
    return {"totalCost":round(total_cost,2),"totalUnits":total_units,"unmetDemand":round(unmet),
        "avgLeadTime":round(avg_lead,1),"routeCount":len(allocs),"allocations":allocs,
        "warehouseUsage":wh_usage,"slaViolations":sla_v,
        "solverStatus":"Greedy (PuLP not installed)","solverEngine":"Greedy"}

def _empty():
    return {"totalCost":0,"totalUnits":0,"unmetDemand":0,"avgLeadTime":0,"routeCount":0,
            "allocations":[],"warehouseUsage":[],"slaViolations":[],"solverStatus":"NO_ROUTES","solverEngine":"None"}

def run_optimization(modifiers=None, hub_scores=None):
    """Unified solver entry point — MIP if PuLP installed, greedy fallback."""
    if PULP_AVAILABLE:
        return _solve_mip(WAREHOUSES, CUSTOMERS, ROUTES, modifiers, hub_scores)
    return _solve_greedy(WAREHOUSES, CUSTOMERS, ROUTES, modifiers, hub_scores)


# ═══════════════════════════════════════════════════════════════════════════════
# NETWORKX ROUTE OPTIMIZER
# ═══════════════════════════════════════════════════════════════════════════════
def _build_graph(hub_scores=None, weather=None):
    hub_scores = hub_scores or {}
    weather_map = {w["hub_id"]: w for w in (weather or [])}
    G = nx.DiGraph()
    for wh in WAREHOUSES: G.add_node(wh["id"], node_type="warehouse", **wh)
    for cu in CUSTOMERS:  G.add_node(cu["id"], node_type="customer",  **cu)
    for r in ROUTES:
        disrupt  = hub_scores.get(r["from"], 0)
        w_impact = weather_map.get(r["from"], {}).get("costImpact", 0)
        weight   = (r["costPerUnit"] * (1 + r["tariffPct"]/100)
                    + disrupt * r["costPerUnit"] * 0.6
                    + w_impact * r["costPerUnit"]
                    + r["leadTimeDays"] * 2.8)
        G.add_edge(r["from"], r["to"], weight=round(weight,2), route_id=r["id"],
                   base_cost=r["costPerUnit"], disruption_penalty=round(disrupt*r["costPerUnit"]*0.6,2),
                   lead_time=r["leadTimeDays"], mode=r["mode"])
    return G

def get_optimal_routes(hub_scores=None, weather=None) -> List[Dict]:
    if not NX_AVAILABLE:
        return []
    G = _build_graph(hub_scores, weather)
    recs = []
    for cu in CUSTOMERS:
        edges = [(u,v,d) for u,v,d in G.in_edges(cu["id"], data=True)]
        if not edges: continue
        edges.sort(key=lambda e: e[2]["weight"])
        best = edges[0]
        reroute = None
        if len(edges) > 1:
            second = edges[1]
            if second[2].get("disruption_penalty",0) < best[2].get("disruption_penalty",0) * 0.8:
                savings = round(best[2]["weight"] - second[2]["weight"], 2)
                reroute = {"warehouse":second[0],"warehouseName":WH_MAP.get(second[0],{}).get("name",""),
                           "saving":savings,"leadTime":second[2]["lead_time"],"mode":second[2]["mode"]}
        recs.append({
            "customer":cu["id"],"customerName":cu["name"],
            "optimalWarehouse":best[0],"optimalWarehouseName":WH_MAP.get(best[0],{}).get("name",""),
            "effectiveCost":best[2]["weight"],"baseCost":best[2]["base_cost"],
            "disruptionPenalty":best[2].get("disruption_penalty",0),
            "leadTime":best[2]["lead_time"],"mode":best[2]["mode"],
            "reroute":reroute,
            "isRerouted": reroute is not None and best[2].get("disruption_penalty",0) > 4,
        })
    return recs


# ═══════════════════════════════════════════════════════════════════════════════
# PREDICTION ENGINE  (EWMA + disruption/weather stress signal)
# ═══════════════════════════════════════════════════════════════════════════════
def generate_predictions(baseline, intel: List[Dict], weather: List[Dict]) -> Dict:
    avg_risk    = sum(e.get("riskScore",0) for e in intel)/max(len(intel),1)
    max_risk    = max((e.get("riskScore",0) for e in intel), default=0)
    intel_sig   = avg_risk * 0.35 + max_risk * 0.65
    weather_sig = sum(w.get("severity",0) for w in weather)/max(len(weather),1)
    stress      = round(intel_sig * 0.68 + weather_sig * 0.32, 3)

    base_cost = baseline["totalCost"]
    base_lead = baseline["avgLeadTime"]
    alpha = 0.3   # EWMA factor
    sm_c, sm_l = base_cost, base_lead
    forecast = []
    for i in range(7):
        esc   = 1 + stress * 0.045 * i
        noise = 1 + random.uniform(-0.018, 0.018)
        raw_c = base_cost * esc * noise * (1 + stress * 0.12)
        raw_l = base_lead * esc * noise * (1 + stress * 0.18)
        sm_c  = alpha * raw_c + (1-alpha) * sm_c
        sm_l  = alpha * raw_l + (1-alpha) * sm_l
        forecast.append({
            "day": i+1,
            "date": (datetime.utcnow()+timedelta(days=i)).strftime("%b %d"),
            "cost": round(sm_c,0),
            "leadTime": round(sm_l,2),
            "unmetRisk": round(min(1.0, stress*(1+i*0.07)*noise),3),
            "costChange": round((sm_c-base_cost)/base_cost*100,1),
        })

    risk_level = "HIGH" if stress>0.58 else "MEDIUM" if stress>0.32 else "LOW"
    risk_color = {"HIGH":"#f87171","MEDIUM":"#fb923c","LOW":"#00C9A7"}[risk_level]

    top_factors = []
    for e in sorted(intel, key=lambda x: x.get("riskScore",0), reverse=True)[:3]:
        top_factors.append({"type":e.get("category","Logistics"),
                            "hub":e.get("hub_id",""),"desc":e.get("title","")[:70],
                            "score":e.get("riskScore",0)})
    for w in sorted(weather, key=lambda x: x.get("severity",0), reverse=True)[:2]:
        if w.get("severity",0) > 0.25:
            top_factors.append({"type":"Weather","hub":w.get("hub_id",""),
                "desc":f"{WH_MAP.get(w['hub_id'],{}).get('name',w['hub_id'])}: {w.get('description','')}",
                "score":w.get("severity",0)})

    return {
        "forecast": forecast,
        "stressScore": stress, "intelSignal": round(intel_sig,3), "weatherSignal": round(weather_sig,3),
        "riskLevel": risk_level, "riskColor": risk_color,
        "topFactors": sorted(top_factors, key=lambda x: x["score"], reverse=True)[:4],
        "baselineCost": base_cost, "baselineLead": base_lead,
        "day7Cost": forecast[-1]["cost"] if forecast else base_cost,
        "day7Lead": forecast[-1]["leadTime"] if forecast else base_lead,
        "costTrend7d": round((forecast[-1]["cost"]-base_cost)/base_cost*100,1) if forecast else 0,
        "generatedAt": datetime.utcnow().isoformat()+"Z",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND SCHEDULER
# ═══════════════════════════════════════════════════════════════════════════════
if SCHEDULER_AVAILABLE:
    _sched = BackgroundScheduler(timezone="UTC")
    _sched.add_job(refresh_intelligence, "interval", hours=INTEL_REFRESH_H, id="intel_refresh")
    _sched.add_job(refresh_weather,      "interval", hours=1,               id="weather_refresh")
    _sched.start()
    print(f"[Scheduler] Intel refresh every {INTEL_REFRESH_H}h · Weather every 1h")


# ═══════════════════════════════════════════════════════════════════════════════
# LLM (unchanged from v2)
# ═══════════════════════════════════════════════════════════════════════════════
def call_llama(prompt: str, max_tokens: int = 512, temperature: float = 0.1) -> Optional[str]:
    if not HF_API_TOKEN:
        return None
    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": max_tokens,
               "temperature": temperature, "return_full_text": False, "do_sample": temperature > 0}}
    for url in [HF_API_URL, HF_FALLBACK_URL]:
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 200:
                result = r.json()
                if isinstance(result, list) and result:
                    return result[0].get("generated_text","").strip()
            elif r.status_code == 503:
                time.sleep(5)
                r = requests.post(url, headers=headers, json=payload, timeout=60)
                if r.status_code == 200:
                    result = r.json()
                    if isinstance(result, list) and result:
                        return result[0].get("generated_text","").strip()
        except Exception as e:
            print(f"[LLM] Error at {url}: {e}")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# INTENT PARSER (unchanged from v2)
# ═══════════════════════════════════════════════════════════════════════════════
WH_NAME_MAP = {
    "phoenix":"WH-PHX","phx":"WH-PHX","charlotte":"WH-CLT","clt":"WH-CLT",
    "san jose":"WH-SJC","sjc":"WH-SJC","dallas":"WH-DFW","dfw":"WH-DFW",
    "chicago":"WH-CHI","chi":"WH-CHI","mumbai":"WH-MUM","mum":"WH-MUM",
    "singapore":"WH-SNG","sng":"WH-SNG","frankfurt":"WH-FRA","fra":"WH-FRA",
}
CUST_NAME_MAP = {
    "aws":"C-AWS-VA","amazon":"C-AWS-VA","microsoft":"C-MSFT-WA","msft":"C-MSFT-WA",
    "meta":"C-META-OR","facebook":"C-META-OR","google":"C-GOOG-SC","goog":"C-GOOG-SC",
    "equinix sv":"C-EQX-SV","digital realty":"C-DLR-TX","dlr":"C-DLR-TX",
    "reliance":"C-REL-MUM","jio":"C-REL-MUM","singtel":"C-SING-TEL",
    "equinix frankfurt":"C-EQNX-FRA","jpmorgan":"C-JPM-NJ","jpm":"C-JPM-NJ",
}

def parse_intent_rules(q: str) -> dict:
    q_l = q.lower()
    wh_pattern   = "|".join(re.escape(k) for k in sorted(WH_NAME_MAP, key=len, reverse=True))
    cust_pattern = "|".join(re.escape(k) for k in sorted(CUST_NAME_MAP, key=len, reverse=True))
    m = re.search(rf"tariff.{{0,20}}?(\d+)%.{{0,30}}?({wh_pattern}|all)", q_l)
    if m:
        pct = int(m.group(1)); loc = m.group(2)
        wh_id = WH_NAME_MAP.get(loc, "ALL" if loc == "all" else None)
        return {"action":"tariff_change","percentage":pct,"direction":"increase","warehouse_id":wh_id or "ALL"}
    m = re.search(rf"demand.{{0,20}}?(increase|surge|drop|fall).{{0,10}}?(\d+)%", q_l)
    if m:
        direction = "increase" if m.group(1) in ("increase","surge") else "decrease"
        return {"action":"demand_change","percentage":int(m.group(2)),"direction":direction,"target":"all","target_type":"segment"}
    m = re.search(rf"(shut down|close|disable).{{0,20}}?({wh_pattern})", q_l)
    if m:
        return {"action":"warehouse_shutdown","warehouse_id":WH_NAME_MAP.get(m.group(2))}
    m = re.search(rf"(reduce|cut).{{0,20}}?capacity.{{0,20}}?({wh_pattern}).{{0,10}}?(\d+)%", q_l)
    if m:
        return {"action":"capacity_change","warehouse_id":WH_NAME_MAP.get(m.group(2)),"percentage":int(m.group(3)),"direction":"decrease"}
    if any(w in q_l for w in ["baseline","current","status","how are","overview"]):
        return {"action":"baseline"}
    return {"action":"general_question"}

def parse_intent_llm(q: str) -> dict:
    prompt = f"""<|begin_of_turn|>system
You parse supply chain what-if queries. Return JSON only with these keys:
action: tariff_change|demand_change|warehouse_shutdown|capacity_change|baseline|general_question
percentage: number (if applicable), direction: increase|decrease, warehouse_id: WH-PHX|WH-CLT|WH-SJC|WH-DFW|WH-CHI|WH-MUM|WH-SNG|WH-FRA|ALL
target: customer segment, target_type: segment|customer
<|end_of_turn|>
<|begin_of_turn|>user
Query: {q}
<|end_of_turn|>
<|begin_of_turn|>assistant
"""
    raw = call_llama(prompt, max_tokens=100, temperature=0.05)
    if raw:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except:
                pass
    return parse_intent_rules(q)

def build_modifiers(intent: dict) -> dict:
    mods = {}
    action = intent.get("action")
    if action == "tariff_change":
        pct  = intent.get("percentage",0)
        wh   = intent.get("warehouse_id")
        val  = pct if intent.get("direction","increase")=="increase" else -pct
        mods["tariff_modifier"] = {r["id"]:val for r in ROUTES} if wh=="ALL" else {wh:val} if wh else {}
    elif action == "demand_change":
        pct  = intent.get("percentage",0)/100
        mult = pct if intent.get("direction","increase")=="increase" else -pct
        tgt  = intent.get("target","all")
        mods["demand_modifier"] = {c["id"]: round(c["demandUnits"]*mult) for c in CUSTOMERS} if tgt=="all" else \
                                  {cid: round(CUST_MAP[cid]["demandUnits"]*mult) for cid in SEGMENT_MAP.get(tgt,[]) if cid in CUST_MAP}
    elif action == "warehouse_shutdown":
        wh = intent.get("warehouse_id")
        if wh: mods["disabled_warehouses"] = [wh]
    elif action == "capacity_change":
        wh  = intent.get("warehouse_id")
        pct = intent.get("percentage",0)
        if wh and wh in WH_MAP:
            chg = round(WH_MAP[wh]["capacity"]*pct/100)
            mods["capacity_modifier"] = {wh: -chg if intent.get("direction","decrease")=="decrease" else chg}
    return mods


# ═══════════════════════════════════════════════════════════════════════════════
# DISRUPTION DETECTION (v2 templates — enhanced by live intel)
# ═══════════════════════════════════════════════════════════════════════════════
DISRUPTION_TEMPLATES = [
    {"type":"Typhoon Warning","severity":0.85,"region":"APAC","affectedWH":["WH-SNG","WH-MUM"],"category":"Weather","description":"Tropical cyclone approaching SE Asia; port operations at risk"},
    {"type":"Port Congestion","severity":0.72,"region":"NA","affectedWH":["WH-SJC"],"category":"Logistics","description":"LA/Long Beach port backlog exceeding 14-day wait times"},
    {"type":"Tariff Escalation","severity":0.68,"region":"APAC","affectedWH":["WH-SNG","WH-MUM"],"category":"Geopolitical","description":"New 25% tariff on semiconductor equipment from APAC origins"},
    {"type":"Semiconductor Shortage","severity":0.91,"region":"Global","affectedWH":["WH-DFW","WH-PHX"],"category":"Supply","description":"Critical UPS component shortage; lead times extended to 16 weeks"},
    {"type":"Rail Strike","severity":0.65,"region":"NA","affectedWH":["WH-CHI","WH-DFW"],"category":"Logistics","description":"Potential freight rail disruption across US midwest corridor"},
    {"type":"Cyber Incident","severity":0.82,"region":"EMEA","affectedWH":["WH-FRA"],"category":"Security","description":"Ransomware targeting European logistics management systems"},
]

def compute_risk_score(event: dict, baseline: dict) -> float:
    aff_routes = [r for r in ROUTES if r["from"] in event["affectedWH"]]
    aff_demand = sum(CUST_MAP.get(r["to"],{}).get("demandUnits",0) for r in aff_routes)
    total_dem  = sum(c["demandUnits"] for c in CUSTOMERS)
    crit_count = sum(1 for r in aff_routes if CUST_MAP.get(r["to"],{}).get("priority")=="Critical")
    return round(event["severity"]*0.4 + (aff_demand/max(total_dem,1))*0.35 + min(1.0,crit_count/4)*0.25, 3)

def simulate_disruption_impact(event: dict, baseline: dict) -> dict:
    mods = {}
    cat  = event.get("category","")
    if cat in ("Weather","Security"):
        mods["disabled_warehouses"] = event["affectedWH"]
    elif cat == "Geopolitical":
        mods["tariff_modifier"] = {wh:25 for wh in event["affectedWH"]}
    elif cat == "Supply":
        mods["capacity_modifier"] = {wh:-round(WH_MAP[wh]["capacity"]*0.4) for wh in event["affectedWH"] if wh in WH_MAP}
    elif cat == "Demand":
        mods["demand_modifier"] = {c["id"]:round(c["demandUnits"]*0.3) for c in CUSTOMERS if c["segment"]=="Hyperscale"}
    else:
        mods["capacity_modifier"] = {wh:-round(WH_MAP[wh]["capacity"]*0.3) for wh in event["affectedWH"] if wh in WH_MAP}
    scenario = run_optimization(mods)
    cost_delta = (scenario["totalCost"]-baseline["totalCost"])/baseline["totalCost"]*100 if baseline["totalCost"]>0 else 0
    lead_delta = (scenario["avgLeadTime"]-baseline["avgLeadTime"])/baseline["avgLeadTime"]*100 if baseline["avgLeadTime"]>0 else 0
    return {"scenario":scenario,"costDelta":round(cost_delta,1),"leadDelta":round(lead_delta,1),"modifiers":mods}

def generate_alerts(baseline: dict) -> List[Dict]:
    alerts = []
    for t in DISRUPTION_TEMPLATES:
        rs = compute_risk_score(t, baseline)
        alerts.append({"id":f"ALT-{uuid.uuid4().hex[:8].upper()}","type":t["type"],
            "severity":t["severity"],"riskScore":rs,"region":t["region"],
            "affectedWH":t["affectedWH"],"category":t["category"],"description":t["description"],
            "status":"active" if rs>0.7 else "monitoring",
            "timestamp":(datetime.utcnow()-timedelta(hours=int(hash(t["type"])%72))).isoformat()+"Z",
            "requiresAction":rs>0.7})
    return sorted(alerts, key=lambda a: a["riskScore"], reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# EXPLANATION + REPORT (unchanged from v2)
# ═══════════════════════════════════════════════════════════════════════════════
def generate_explanation(intent, baseline, scenario):
    action = intent.get("action","unknown")
    if action=="tariff_change":
        wh = WH_MAP.get(intent.get("warehouse_id",""),{}).get("name","multiple")
        desc = f"Tariff +{intent.get('percentage',0)}% on routes from {wh}"
    elif action=="demand_change":
        desc = f"Demand {'up' if intent.get('direction')=='increase' else 'down'} {intent.get('percentage',0)}% for {intent.get('target','all')}"
    elif action=="warehouse_shutdown":
        desc = f"Shutdown: {WH_MAP.get(intent.get('warehouse_id',''),{}).get('name','unknown')}"
    else:
        desc = "Baseline analysis"
    c_d = (scenario["totalCost"]-baseline["totalCost"])/baseline["totalCost"]*100 if baseline["totalCost"]>0 else 0
    l_d = (scenario["avgLeadTime"]-baseline["avgLeadTime"])/baseline["avgLeadTime"]*100 if baseline["avgLeadTime"]>0 else 0
    prompt = f"""<|begin_of_turn|>system\nYou are a senior supply chain analyst. Respond in 3-4 concise sentences.\n<|end_of_turn|>\n<|begin_of_turn|>user\nScenario: {desc}\nCost: ${baseline['totalCost']:,.0f} → ${scenario['totalCost']:,.0f} ({c_d:+.1f}%)\nLead: {baseline['avgLeadTime']:.1f}d → {scenario['avgLeadTime']:.1f}d ({l_d:+.1f}%)\nUnmet: {scenario['unmetDemand']:,} units | SLAs at risk: {len(scenario['slaViolations'])}\n<|end_of_turn|>\n<|begin_of_turn|>assistant\n"""
    llm = call_llama(prompt, max_tokens=250, temperature=0.1)
    if llm: return llm
    parts = [f"Cost {'increased' if c_d>0 else 'decreased'} {abs(c_d):.1f}% (${baseline['totalCost']:,.0f}→${scenario['totalCost']:,.0f})."]
    if abs(l_d)>0.5: parts.append(f"Lead time {'up' if l_d>0 else 'down'} {abs(l_d):.1f}% to {scenario['avgLeadTime']:.1f}d.")
    parts.append(f"{'⚠ ' + str(scenario['unmetDemand']) + ' units unmet.' if scenario['unmetDemand']>0 else 'All demand fulfilled.'}")
    return " ".join(parts)


# ═══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ═══════════════════════════════════════════════════════════════════════════════
class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    explanation: str; intent: dict; baseline: dict
    scenario: Optional[dict] = None; is_scenario: bool = False

class SimulateRequest(BaseModel):
    event_type: str; affected_warehouses: List[str] = Field(default_factory=list)
    category: str = "Weather"; severity: float = 0.8

class ReportRequest(BaseModel):
    scenarioName: str; modifiers: Optional[dict] = None


# ═══════════════════════════════════════════════════════════════════════════════
# BASELINE (computed once at startup, enriched with live disruption scores)
# ═══════════════════════════════════════════════════════════════════════════════
BASELINE = run_optimization()
LAST_INTEL_REFRESH = datetime.utcnow()


# ═══════════════════════════════════════════════════════════════════════════════
# ── API ENDPOINTS ─────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return {"status":"ok","service":"Supply Chain Intelligence API","version":"3.0.0",
            "solver":"PuLP-MIP" if PULP_AVAILABLE else "Greedy",
            "networkx":NX_AVAILABLE,"scheduler":SCHEDULER_AVAILABLE,
            "serper_configured":bool(SERPER_API_KEY),
            "features":["mip-optimization","live-intelligence","weather","route-optimization","predictions"]}

@app.get("/health")
def health():
    return {"status":"healthy","version":"3.0.0","llm_configured":bool(HF_API_TOKEN),
            "serper_configured":bool(SERPER_API_KEY),"solver":"PuLP" if PULP_AVAILABLE else "Greedy",
            "networkx":NX_AVAILABLE}

@app.get("/baseline")
def get_baseline():
    return BASELINE

@app.get("/network")
def get_network():
    return {"warehouses":WAREHOUSES,"customers":CUSTOMERS,"routes":ROUTES,"products":PRODUCTS}


# ── v2 compatible endpoints ────────────────────────────────────────────────────
@app.post("/query", response_model=QueryResponse)
def handle_query(req: QueryRequest):
    q = req.query.strip()
    if not q: raise HTTPException(400, "Query cannot be empty")
    intent = parse_intent_llm(q)
    action = intent.get("action","general_question")
    if action == "baseline":
        return QueryResponse(explanation=f"Baseline: ${BASELINE['totalCost']:,.0f} cost · {BASELINE['totalUnits']:,} units · {BASELINE['avgLeadTime']:.1f}d avg lead · {BASELINE['unmetDemand']} unmet. Solver: {BASELINE.get('solverEngine','N/A')}",
                             intent=intent, baseline=BASELINE, scenario=BASELINE, is_scenario=True)
    if action == "general_question":
        return QueryResponse(explanation=f"Network: {len(CUSTOMERS)} customers · {len(WAREHOUSES)} DCs · Solver: {BASELINE.get('solverEngine','N/A')}. Try: 'tariff increase 30% from Singapore', 'demand surge 20% all', 'shut down Mumbai'.",
                             intent=intent, baseline=BASELINE, is_scenario=False)
    mods     = build_modifiers(intent)
    scenario = run_optimization(mods)
    return QueryResponse(explanation=generate_explanation(intent,BASELINE,scenario),
                         intent=intent, baseline=BASELINE, scenario=scenario, is_scenario=True)

@app.get("/api/alerts")
def get_alerts(status:Optional[str]=None, region:Optional[str]=None, min_risk:Optional[float]=None):
    alerts = generate_alerts(BASELINE)
    if status:   alerts = [a for a in alerts if a["status"]==status]
    if region:   alerts = [a for a in alerts if a["region"]==region]
    if min_risk is not None: alerts = [a for a in alerts if a["riskScore"]>=min_risk]
    return {"alerts":alerts,"totalCount":len(alerts),"activeCount":sum(1 for a in alerts if a["status"]=="active"),
            "timestamp":datetime.utcnow().isoformat()+"Z"}

@app.post("/api/alerts/simulate")
def simulate_alert(req: SimulateRequest):
    event = {"type":req.event_type,"severity":req.severity,"region":"Custom",
             "affectedWH":req.affected_warehouses,"category":req.category,"description":f"Sim: {req.event_type}"}
    if not event["affectedWH"]: raise HTTPException(400,"affected_warehouses required")
    for wh in event["affectedWH"]:
        if wh not in WH_MAP: raise HTTPException(400,f"Invalid WH: {wh}")
    rs     = compute_risk_score(event, BASELINE)
    impact = simulate_disruption_impact(event, BASELINE)
    return {"event":event,"riskScore":rs,"impact":{"costDelta":impact["costDelta"],"leadDelta":impact["leadDelta"],
        "unmetDemand":impact["scenario"]["unmetDemand"],"slaViolations":impact["scenario"]["slaViolations"]},
        "scenario":impact["scenario"],"baseline":BASELINE}

@app.post("/api/reports")
def generate_report(req: ReportRequest):
    if not req.scenarioName: raise HTTPException(400,"scenarioName required")
    if req.modifiers:
        scenario = run_optimization(req.modifiers)
    else:
        intent = parse_intent_rules(req.scenarioName)
        scenario = run_optimization(build_modifiers(intent)) if intent["action"]!="general_question" else BASELINE
    c_d = (scenario["totalCost"]-BASELINE["totalCost"])/BASELINE["totalCost"]*100 if BASELINE["totalCost"]>0 else 0
    l_d = (scenario["avgLeadTime"]-BASELINE["avgLeadTime"])/BASELINE["avgLeadTime"]*100 if BASELINE["avgLeadTime"]>0 else 0
    ff  = round(scenario["totalUnits"]/sum(c["demandUnits"] for c in CUSTOMERS)*100,1) if CUSTOMERS else 0
    return {"reportId":f"RPT-{uuid.uuid4().hex[:8].upper()}",
        "report":{"title":f"Strategy: {req.scenarioName}","timestamp":datetime.utcnow().isoformat()+"Z",
            "summary":f"Cost {'↑' if c_d>0 else '↓'}{abs(c_d):.1f}% (${BASELINE['totalCost']:,.0f}→${scenario['totalCost']:,.0f}). {'⚠ '+str(scenario['unmetDemand'])+' unmet.' if scenario['unmetDemand']>0 else 'Full demand coverage.'} Lead {scenario['avgLeadTime']:.1f}d ({l_d:+.1f}%).",
            "metrics":{"costDelta":round(c_d,1),"leadDelta":round(l_d,1),"fulfillmentRate":ff,
                "routeCount":scenario["routeCount"],"unmetDemand":scenario["unmetDemand"]},
            "warehouseUsage":scenario["warehouseUsage"],"slaViolations":scenario["slaViolations"],
            "allocations":scenario["allocations"][:15]},
        "scenario":scenario,"baseline":BASELINE}

@app.get("/api/connector")
def get_connector():
    return {"type":ACTIVE_CONNECTOR.connector_type,"name":ACTIVE_CONNECTOR.connector_name,"status":"active",
            "capabilities":["warehouses","customers","routes","products","inventory_levels"]}


# ── v3 NEW endpoints ───────────────────────────────────────────────────────────

@app.get("/api/v3/intelligence")
def get_intelligence(hub_id: Optional[str] = None):
    """
    Live disruption intelligence from Serper.dev (or high-quality static fallback).
    Returns scored events per hub with category, risk score, and source attribution.
    Configure SERPER_API_KEY env var to enable live data (serper.dev — 2500 free/mo).
    """
    events = get_live_intelligence()
    if hub_id:
        events = [e for e in events if e.get("hub_id") == hub_id]
    hub_scores = compute_hub_scores(events, [])
    return {
        "events": events,
        "hubScores": hub_scores,
        "totalEvents": len(events),
        "highRiskCount": sum(1 for e in events if e.get("riskScore",0) > 0.6),
        "liveDataActive": bool(SERPER_API_KEY),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

@app.get("/api/v3/weather")
def get_weather():
    """
    Live weather for all hub locations via Open-Meteo (free · no API key).
    Returns WMO weather codes, wind speed, precipitation, severity score,
    and computed lead-time / cost impact percentages.
    """
    weather = get_live_weather()
    return {
        "hubs": weather,
        "maxSeverity": max((w.get("severity",0) for w in weather), default=0),
        "avgSeverity": round(sum(w.get("severity",0) for w in weather)/max(len(weather),1), 3),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

@app.get("/api/v3/optimize")
def get_route_optimization():
    """
    NetworkX-powered route optimization with live disruption + weather penalties.
    Returns optimal warehouse assignment per customer, disruption surcharges,
    and reroute recommendations when a better path exists.
    """
    intel   = get_live_intelligence()
    weather = get_live_weather()
    scores  = compute_hub_scores(intel, weather)
    routes  = get_optimal_routes(hub_scores=scores, weather=weather)
    reroute_count = sum(1 for r in routes if r.get("isRerouted"))
    return {
        "routes": routes,
        "hubScores": scores,
        "rerouteCount": reroute_count,
        "solverAvailable": NX_AVAILABLE,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

@app.get("/api/v3/predictions")
def get_predictions():
    """
    7-day EWMA forecast for cost, lead time, and unmet demand risk.
    Signal = 68% disruption intelligence + 32% weather severity.
    Returns forecast array, risk level (HIGH/MEDIUM/LOW), and top risk factors.
    """
    intel    = get_live_intelligence()
    weather  = get_live_weather()
    baseline = run_optimization(hub_scores=compute_hub_scores(intel, weather))
    preds    = generate_predictions(baseline, intel, weather)
    return preds

@app.post("/api/v3/refresh")
async def trigger_refresh(bg: BackgroundTasks):
    """Manually trigger intelligence + weather refresh (useful for demos)."""
    bg.add_task(refresh_intelligence)
    bg.add_task(refresh_weather)
    return {"status":"refresh_scheduled","timestamp":datetime.utcnow().isoformat()+"Z"}

@app.get("/api/v3/status")
def get_v3_status():
    """Full v3 system status — useful for dashboard health widget."""
    intel   = get_live_intelligence()
    weather = get_live_weather()
    scores  = compute_hub_scores(intel, weather)
    return {
        "version": "3.0.0",
        "solver": "PuLP-MIP" if PULP_AVAILABLE else "Greedy",
        "networkx": NX_AVAILABLE,
        "scheduler": SCHEDULER_AVAILABLE,
        "serper": bool(SERPER_API_KEY),
        "intelEvents": len(intel),
        "weatherHubs": len(weather),
        "highRiskHubs": [k for k,v in scores.items() if v > 0.6],
        "hubScores": scores,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/v3/test-serper")
def test_serper_connection():
    """Debug endpoint — tests Serper connectivity and returns raw response."""
    if not SERPER_API_KEY:
        return {"configured": False, "error": "SERPER_API_KEY not set"}
    try:
        r = requests.post(
            "https://google.serper.dev/news",
            headers={"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"},
            json={"q": "Singapore port disruption", "num": 2, "gl": "us"},
            timeout=10,
        )
        return {
            "configured": True,
            "status_code": r.status_code,
            "response_preview": str(r.text)[:500],
            "key_prefix": SERPER_API_KEY[:8] + "...",
        }
    except Exception as e:
        return {"configured": True, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
