"""
Supply Chain Intelligence v2.0 — Backend API
==============================================
Architecture: OptiGuide (arXiv 2307.03875) + IFS Framework
Franz Edelman 2026 Finalist — Microsoft Research

NEW in v2.0:
- /api/alerts     → Disruption detection + risk scoring
- /api/reports    → AI strategy report generation
- /api/simulate   → Impact simulation for disruption events
- Plug-and-play data connector architecture for ERP/SCM integration

Built by Atharva | Simplified by Atharva
"""

import os
import json
import re
import math
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import requests

# ============================================================
# CONFIG
# ============================================================

HF_API_TOKEN = os.environ.get("HF_API_TOKEN", "")
LLAMA_MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
FALLBACK_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
HF_API_URL = f"https://api-inference.huggingface.co/models/{LLAMA_MODEL}"
HF_FALLBACK_URL = f"https://api-inference.huggingface.co/models/{FALLBACK_MODEL}"

app = FastAPI(
    title="Supply Chain Intelligence API v2.0",
    description="AI-Powered Scenario Planner + Disruption Detection + Strategy Reports",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# PLUG-AND-PLAY DATA CONNECTOR ARCHITECTURE
# ============================================================
# This abstraction layer allows future ERP/SCM integration.
# To connect a real data source, implement the DataConnector
# interface and register it. The solver and APIs read from
# the connector, NOT from hardcoded data.

class DataConnector:
    """
    Base class for supply chain data sources.
    Implement this interface to plug in SAP, Oracle SCM,
    Kinaxis, Blue Yonder, or any ERP system.
    """
    def get_warehouses(self) -> List[Dict]: raise NotImplementedError
    def get_customers(self) -> List[Dict]: raise NotImplementedError
    def get_routes(self) -> List[Dict]: raise NotImplementedError
    def get_products(self) -> List[Dict]: raise NotImplementedError
    def get_inventory_levels(self) -> Dict[str, int]: raise NotImplementedError
    def get_active_orders(self) -> List[Dict]: return []
    def get_disruption_feeds(self) -> List[Dict]: return []
    def push_alert(self, alert: Dict) -> bool: return True
    def push_report(self, report: Dict) -> bool: return True

    @property
    def connector_type(self) -> str: return "base"
    @property
    def connector_name(self) -> str: return "Base Connector"


class SyntheticDataConnector(DataConnector):
    """
    Built-in synthetic data modeled on Vertiv's global DC infrastructure
    supply chain. Replace with real connector for production.
    """

    @property
    def connector_type(self): return "synthetic"
    @property
    def connector_name(self): return "Synthetic (Vertiv-modeled)"

    def get_warehouses(self):
        return [
            {"id": "WH-PHX", "name": "Phoenix Hub", "location": "Phoenix, AZ", "lat": 33.45, "lng": -112.07, "capacity": 12000, "currentStock": 9200, "type": "Primary DC", "specialization": "UPS & Thermal", "operatingCostPerUnit": 2.1, "region": "NA"},
            {"id": "WH-CLT", "name": "Charlotte Facility", "location": "Charlotte, NC", "lat": 35.23, "lng": -80.84, "capacity": 8500, "currentStock": 6100, "type": "Regional DC", "specialization": "Power Distribution", "operatingCostPerUnit": 1.8, "region": "NA"},
            {"id": "WH-SJC", "name": "San Jose Center", "location": "San Jose, CA", "lat": 37.34, "lng": -121.89, "capacity": 6000, "currentStock": 4800, "type": "Regional DC", "specialization": "Cooling Systems", "operatingCostPerUnit": 2.5, "region": "NA"},
            {"id": "WH-DFW", "name": "Dallas Mega Hub", "location": "Dallas, TX", "lat": 32.78, "lng": -96.80, "capacity": 15000, "currentStock": 11500, "type": "Primary DC", "specialization": "Full Portfolio", "operatingCostPerUnit": 1.6, "region": "NA"},
            {"id": "WH-CHI", "name": "Chicago North", "location": "Chicago, IL", "lat": 41.88, "lng": -87.63, "capacity": 7000, "currentStock": 5300, "type": "Regional DC", "specialization": "IT Infrastructure", "operatingCostPerUnit": 1.9, "region": "NA"},
            {"id": "WH-MUM", "name": "Mumbai Gateway", "location": "Mumbai, India", "lat": 19.08, "lng": 72.88, "capacity": 10000, "currentStock": 7600, "type": "International Hub", "specialization": "APAC Distribution", "operatingCostPerUnit": 1.2, "region": "APAC"},
            {"id": "WH-SNG", "name": "Singapore Hub", "location": "Singapore", "lat": 1.35, "lng": 103.82, "capacity": 9000, "currentStock": 6900, "type": "International Hub", "specialization": "APAC Cooling", "operatingCostPerUnit": 2.0, "region": "APAC"},
            {"id": "WH-FRA", "name": "Frankfurt Center", "location": "Frankfurt, Germany", "lat": 50.11, "lng": 8.68, "capacity": 8000, "currentStock": 5500, "type": "International Hub", "specialization": "EMEA Distribution", "operatingCostPerUnit": 2.3, "region": "EMEA"},
        ]

    def get_customers(self):
        return [
            {"id": "C-AWS-VA", "name": "AWS Virginia", "location": "Ashburn, VA", "lat": 39.04, "lng": -77.47, "demandUnits": 2400, "priority": "Critical", "segment": "Hyperscale", "slaLeadDays": 3},
            {"id": "C-MSFT-WA", "name": "Microsoft Quincy", "location": "Quincy, WA", "lat": 47.23, "lng": -119.85, "demandUnits": 1800, "priority": "Critical", "segment": "Hyperscale", "slaLeadDays": 4},
            {"id": "C-META-OR", "name": "Meta Prineville", "location": "Prineville, OR", "lat": 44.30, "lng": -120.73, "demandUnits": 1500, "priority": "High", "segment": "Hyperscale", "slaLeadDays": 4},
            {"id": "C-GOOG-SC", "name": "Google SC", "location": "The Dalles, OR", "lat": 45.59, "lng": -121.18, "demandUnits": 2000, "priority": "Critical", "segment": "Hyperscale", "slaLeadDays": 3},
            {"id": "C-EQX-SV", "name": "Equinix SV5", "location": "San Jose, CA", "lat": 37.39, "lng": -121.95, "demandUnits": 800, "priority": "High", "segment": "Colocation", "slaLeadDays": 2},
            {"id": "C-DLR-TX", "name": "Digital Realty TX", "location": "Dallas, TX", "lat": 32.82, "lng": -96.75, "demandUnits": 950, "priority": "High", "segment": "Colocation", "slaLeadDays": 2},
            {"id": "C-REL-MUM", "name": "Reliance Jio DC", "location": "Navi Mumbai, India", "lat": 19.03, "lng": 73.03, "demandUnits": 1200, "priority": "High", "segment": "Telecom", "slaLeadDays": 5},
            {"id": "C-SING-TEL", "name": "Singtel DC", "location": "Singapore", "lat": 1.30, "lng": 103.85, "demandUnits": 700, "priority": "Medium", "segment": "Telecom", "slaLeadDays": 5},
            {"id": "C-EQNX-FRA", "name": "Equinix FR5", "location": "Frankfurt, Germany", "lat": 50.08, "lng": 8.72, "demandUnits": 650, "priority": "Medium", "segment": "Colocation", "slaLeadDays": 3},
            {"id": "C-JPM-NJ", "name": "JPMorgan Metro", "location": "Jersey City, NJ", "lat": 40.73, "lng": -74.04, "demandUnits": 500, "priority": "Critical", "segment": "Enterprise", "slaLeadDays": 2},
        ]

    def get_routes(self):
        return [
            {"id": "R001", "from": "WH-CLT", "to": "C-AWS-VA", "distance": 400, "costPerUnit": 12.5, "leadTimeDays": 1, "tariffPct": 0, "mode": "Ground"},
            {"id": "R002", "from": "WH-DFW", "to": "C-AWS-VA", "distance": 1300, "costPerUnit": 28.0, "leadTimeDays": 3, "tariffPct": 0, "mode": "Ground"},
            {"id": "R003", "from": "WH-PHX", "to": "C-MSFT-WA", "distance": 1400, "costPerUnit": 31.0, "leadTimeDays": 3, "tariffPct": 0, "mode": "Ground"},
            {"id": "R004", "from": "WH-SJC", "to": "C-MSFT-WA", "distance": 800, "costPerUnit": 19.5, "leadTimeDays": 2, "tariffPct": 0, "mode": "Ground"},
            {"id": "R005", "from": "WH-SJC", "to": "C-META-OR", "distance": 550, "costPerUnit": 15.0, "leadTimeDays": 2, "tariffPct": 0, "mode": "Ground"},
            {"id": "R006", "from": "WH-SJC", "to": "C-GOOG-SC", "distance": 600, "costPerUnit": 16.0, "leadTimeDays": 2, "tariffPct": 0, "mode": "Ground"},
            {"id": "R007", "from": "WH-DFW", "to": "C-GOOG-SC", "distance": 1800, "costPerUnit": 35.0, "leadTimeDays": 4, "tariffPct": 0, "mode": "Ground"},
            {"id": "R008", "from": "WH-SJC", "to": "C-EQX-SV", "distance": 10, "costPerUnit": 3.0, "leadTimeDays": 0.5, "tariffPct": 0, "mode": "Local"},
            {"id": "R009", "from": "WH-DFW", "to": "C-DLR-TX", "distance": 15, "costPerUnit": 3.5, "leadTimeDays": 0.5, "tariffPct": 0, "mode": "Local"},
            {"id": "R010", "from": "WH-MUM", "to": "C-REL-MUM", "distance": 30, "costPerUnit": 4.0, "leadTimeDays": 1, "tariffPct": 5, "mode": "Local"},
            {"id": "R011", "from": "WH-SNG", "to": "C-SING-TEL", "distance": 20, "costPerUnit": 5.0, "leadTimeDays": 1, "tariffPct": 3, "mode": "Local"},
            {"id": "R012", "from": "WH-FRA", "to": "C-EQNX-FRA", "distance": 15, "costPerUnit": 4.5, "leadTimeDays": 0.5, "tariffPct": 2, "mode": "Local"},
            {"id": "R013", "from": "WH-CLT", "to": "C-JPM-NJ", "distance": 600, "costPerUnit": 18.0, "leadTimeDays": 2, "tariffPct": 0, "mode": "Ground"},
            {"id": "R014", "from": "WH-PHX", "to": "C-DLR-TX", "distance": 1000, "costPerUnit": 24.0, "leadTimeDays": 3, "tariffPct": 0, "mode": "Ground"},
            {"id": "R015", "from": "WH-CHI", "to": "C-AWS-VA", "distance": 700, "costPerUnit": 20.0, "leadTimeDays": 2, "tariffPct": 0, "mode": "Ground"},
            {"id": "R016", "from": "WH-CHI", "to": "C-JPM-NJ", "distance": 790, "costPerUnit": 21.0, "leadTimeDays": 2, "tariffPct": 0, "mode": "Ground"},
            {"id": "R017", "from": "WH-DFW", "to": "C-META-OR", "distance": 1900, "costPerUnit": 38.0, "leadTimeDays": 4, "tariffPct": 0, "mode": "Ground"},
            {"id": "R018", "from": "WH-SNG", "to": "C-REL-MUM", "distance": 3900, "costPerUnit": 65.0, "leadTimeDays": 7, "tariffPct": 8, "mode": "Ocean"},
            {"id": "R019", "from": "WH-FRA", "to": "C-SING-TEL", "distance": 10000, "costPerUnit": 85.0, "leadTimeDays": 14, "tariffPct": 6, "mode": "Ocean"},
            {"id": "R020", "from": "WH-MUM", "to": "C-SING-TEL", "distance": 3200, "costPerUnit": 55.0, "leadTimeDays": 5, "tariffPct": 4, "mode": "Ocean"},
        ]

    def get_products(self):
        return [
            {"id": "P-UPS", "name": "Liebert UPS Systems", "category": "Power Protection", "unitCost": 8500},
            {"id": "P-PDU", "name": "Power Distribution Units", "category": "Power Distribution", "unitCost": 3200},
            {"id": "P-COOL", "name": "Liebert Cooling Units", "category": "Thermal Management", "unitCost": 15000},
            {"id": "P-RACK", "name": "VR Rack Systems", "category": "IT Infrastructure", "unitCost": 2800},
            {"id": "P-MON", "name": "Trellis Monitoring", "category": "Software/Monitoring", "unitCost": 500},
        ]

    def get_inventory_levels(self):
        return {w["id"]: w["currentStock"] for w in self.get_warehouses()}


# --- Register Active Connector ---
# To switch data source, replace SyntheticDataConnector() with your
# ERPDataConnector(), SAPConnector(), OracleConnector(), etc.
ACTIVE_CONNECTOR: DataConnector = SyntheticDataConnector()

# Load data from connector
WAREHOUSES = ACTIVE_CONNECTOR.get_warehouses()
CUSTOMERS = ACTIVE_CONNECTOR.get_customers()
ROUTES = ACTIVE_CONNECTOR.get_routes()
PRODUCTS = ACTIVE_CONNECTOR.get_products()

# Lookup maps
WH_MAP = {w["id"]: w for w in WAREHOUSES}
CUST_MAP = {c["id"]: c for c in CUSTOMERS}
ROUTE_MAP = {r["id"]: r for r in ROUTES}

WH_NAME_MAP = {
    "phoenix": "WH-PHX", "phx": "WH-PHX",
    "charlotte": "WH-CLT", "clt": "WH-CLT",
    "san jose": "WH-SJC", "sjc": "WH-SJC", "sanjose": "WH-SJC",
    "dallas": "WH-DFW", "dfw": "WH-DFW",
    "chicago": "WH-CHI", "chi": "WH-CHI",
    "mumbai": "WH-MUM", "mum": "WH-MUM",
    "singapore": "WH-SNG", "sng": "WH-SNG",
    "frankfurt": "WH-FRA", "fra": "WH-FRA",
}

CUST_NAME_MAP = {
    "aws": "C-AWS-VA", "amazon": "C-AWS-VA",
    "microsoft": "C-MSFT-WA", "msft": "C-MSFT-WA",
    "meta": "C-META-OR", "facebook": "C-META-OR",
    "google": "C-GOOG-SC", "goog": "C-GOOG-SC",
    "equinix sv": "C-EQX-SV", "equinix san jose": "C-EQX-SV",
    "digital realty": "C-DLR-TX", "dlr": "C-DLR-TX",
    "reliance": "C-REL-MUM", "jio": "C-REL-MUM",
    "singtel": "C-SING-TEL",
    "equinix frankfurt": "C-EQNX-FRA", "equinix fra": "C-EQNX-FRA",
    "jpmorgan": "C-JPM-NJ", "jpm": "C-JPM-NJ", "jp morgan": "C-JPM-NJ",
}

SEGMENT_MAP = {
    "hyperscale": ["C-AWS-VA", "C-MSFT-WA", "C-META-OR", "C-GOOG-SC"],
    "colocation": ["C-EQX-SV", "C-DLR-TX", "C-EQNX-FRA"],
    "telecom": ["C-REL-MUM", "C-SING-TEL"],
    "enterprise": ["C-JPM-NJ"],
}


# ============================================================
# LLAMA 3 INTEGRATION
# ============================================================

def call_llama(prompt: str, max_tokens: int = 512, temperature: float = 0.1) -> Optional[str]:
    if not HF_API_TOKEN:
        return None

    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "return_full_text": False,
            "do_sample": temperature > 0,
        },
    }

    for url in [HF_API_URL, HF_FALLBACK_URL]:
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            if resp.status_code == 200:
                result = resp.json()
                if isinstance(result, list) and len(result) > 0:
                    return result[0].get("generated_text", "").strip()
            elif resp.status_code == 503:
                time.sleep(5)
                resp = requests.post(url, headers=headers, json=payload, timeout=60)
                if resp.status_code == 200:
                    result = resp.json()
                    if isinstance(result, list) and len(result) > 0:
                        return result[0].get("generated_text", "").strip()
        except Exception as e:
            print(f"LLM call failed for {url}: {e}")
            continue
    return None


# ============================================================
# INTENT PARSER (v2 — enhanced)
# ============================================================

PARSE_PROMPT_TEMPLATE = """<|begin_of_turn|>system
You are a supply chain query parser. Extract intent as JSON.

VALID ACTIONS: tariff_change, demand_change, warehouse_shutdown, capacity_change, baseline, general_question
WAREHOUSES: WH-PHX (Phoenix), WH-CLT (Charlotte), WH-SJC (San Jose), WH-DFW (Dallas), WH-CHI (Chicago), WH-MUM (Mumbai), WH-SNG (Singapore), WH-FRA (Frankfurt)
CUSTOMERS: C-AWS-VA, C-MSFT-WA, C-META-OR, C-GOOG-SC, C-EQX-SV, C-DLR-TX, C-REL-MUM, C-SING-TEL, C-EQNX-FRA, C-JPM-NJ
SEGMENTS: hyperscale, colocation, telecom, enterprise, all

Respond ONLY with JSON.

Examples:
"Tariff increases 15% from Singapore" → {{"action":"tariff_change","warehouse_id":"WH-SNG","percentage":15,"direction":"increase"}}
"Demand surges 30% for hyperscale" → {{"action":"demand_change","target":"hyperscale","target_type":"segment","percentage":30,"direction":"increase"}}
"Shut down Mumbai warehouse" → {{"action":"warehouse_shutdown","warehouse_id":"WH-MUM"}}
"Reduce capacity at Dallas by 40%" → {{"action":"capacity_change","warehouse_id":"WH-DFW","percentage":40,"direction":"decrease"}}
"Show baseline" → {{"action":"baseline"}}
<|end_of_turn|>
<|begin_of_turn|>user
{query}
<|end_of_turn|>
<|begin_of_turn|>assistant
"""


def parse_intent_llm(query: str) -> dict:
    prompt = PARSE_PROMPT_TEMPLATE.format(query=query)
    raw = call_llama(prompt, max_tokens=200, temperature=0.05)

    if raw:
        try:
            json_match = re.search(r'\{[^{}]+\}', raw)
            if json_match:
                parsed = json.loads(json_match.group())
                if validate_intent(parsed):
                    return parsed
        except (json.JSONDecodeError, KeyError):
            pass

    return parse_intent_rules(query)


def validate_intent(intent: dict) -> bool:
    action = intent.get("action")
    if not action:
        return False
    if action in ("tariff_change", "warehouse_shutdown", "capacity_change"):
        wh_id = intent.get("warehouse_id", "")
        if wh_id and wh_id not in WH_MAP and wh_id != "ALL":
            return False
    if action == "demand_change":
        target = intent.get("target", "")
        target_type = intent.get("target_type", "")
        if target_type == "segment" and target not in SEGMENT_MAP and target != "all":
            return False
        if target_type == "customer" and target not in CUST_MAP:
            return False
    if action in ("tariff_change", "demand_change", "capacity_change"):
        pct = intent.get("percentage")
        if pct is not None and (not isinstance(pct, (int, float)) or pct < 0 or pct > 500):
            return False
    return True


def parse_intent_rules(query: str) -> dict:
    lower = query.lower().strip()

    if any(kw in lower for kw in ["baseline", "current plan", "current state", "show me the plan", "show plan", "default"]):
        return {"action": "baseline"}

    tariff_match = re.search(
        r'tariff\s*(?:increase|raise|go(?:es)?\s*up|hike|jump|change)(?:s|d|ed)?\s*(?:by\s*)?(\d+)\s*%?\s*(?:on|for|from|at)?\s*(?:routes?\s*(?:from|out\s*of|at))?\s*(\w[\w\s]*)',
        lower
    )
    if tariff_match:
        pct = int(tariff_match.group(1))
        loc = tariff_match.group(2).strip()
        wh_id = WH_NAME_MAP.get(loc)
        if loc == "all":
            return {"action": "tariff_change", "warehouse_id": "ALL", "percentage": pct, "direction": "increase"}
        if wh_id:
            return {"action": "tariff_change", "warehouse_id": wh_id, "percentage": pct, "direction": "increase"}

    demand_match = re.search(
        r'demand\s*(?:increase|surge|jump|grow|rise|raise|spike|boost)(?:s|d|ed)?\s*(?:by\s*)?(\d+)\s*%?\s*(?:for|at|from)?\s*(\w[\w\s]*)',
        lower
    )
    if demand_match:
        pct = int(demand_match.group(1))
        target = demand_match.group(2).strip()
        if target in SEGMENT_MAP or target == "all":
            return {"action": "demand_change", "target": target, "target_type": "segment", "percentage": pct, "direction": "increase"}
        cust_id = CUST_NAME_MAP.get(target)
        if cust_id:
            return {"action": "demand_change", "target": cust_id, "target_type": "customer", "percentage": pct, "direction": "increase"}

    shutdown_match = re.search(
        r'(?:shut\s*down|close|disable|lose|remove|deactivate)\s*(?:the\s*)?(?:warehouse\s*(?:in|at)?\s*)?(\w[\w\s]*)',
        lower
    )
    if shutdown_match:
        loc = shutdown_match.group(1).strip()
        wh_id = WH_NAME_MAP.get(loc)
        if wh_id:
            return {"action": "warehouse_shutdown", "warehouse_id": wh_id}

    cap_match = re.search(
        r'(?:reduce|decrease|cut|lower)\s*(?:capacity|stock)\s*(?:at|in|for)?\s*(\w[\w\s]*?)\s*(?:by\s*)?(\d+)\s*%',
        lower
    )
    if cap_match:
        loc = cap_match.group(1).strip()
        pct = int(cap_match.group(2))
        wh_id = WH_NAME_MAP.get(loc)
        if wh_id:
            return {"action": "capacity_change", "warehouse_id": wh_id, "percentage": pct, "direction": "decrease"}

    return {"action": "general_question", "topic": query}


# ============================================================
# OPTIMIZATION ENGINE v2
# ============================================================

def run_optimization(modifiers: dict = None) -> dict:
    if modifiers is None:
        modifiers = {}

    tariff_mod = modifiers.get("tariff_modifier", {})
    demand_mod = modifiers.get("demand_modifier", {})
    capacity_mod = modifiers.get("capacity_modifier", {})
    disabled_routes = modifiers.get("disabled_routes", [])
    disabled_warehouses = modifiers.get("disabled_warehouses", [])

    wh_state = {}
    for w in WAREHOUSES:
        if w["id"] in disabled_warehouses:
            continue
        cap_mod = capacity_mod.get(w["id"], 0)
        effective_cap = max(0, w["capacity"] + cap_mod)
        effective_stock = min(w["currentStock"], effective_cap)
        wh_state[w["id"]] = {
            **w,
            "effectiveCapacity": effective_cap,
            "effectiveStock": effective_stock,
            "allocated": 0,
            "remaining": effective_stock,
        }

    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    sorted_customers = sorted(CUSTOMERS, key=lambda c: priority_order.get(c["priority"], 3))

    total_cost = 0
    total_units = 0
    unmet_demand = 0
    allocations = []
    sla_violations = []

    for customer in sorted_customers:
        d_mod = demand_mod.get(customer["id"], 0)
        remaining_demand = customer["demandUnits"] + d_mod
        if remaining_demand <= 0:
            continue

        available_routes = []
        for r in ROUTES:
            if r["to"] != customer["id"]:
                continue
            if r["id"] in disabled_routes or r["from"] in disabled_warehouses or r["from"] not in wh_state:
                continue
            t_mod = tariff_mod.get(r["id"], tariff_mod.get(r["from"], 0))
            effective_tariff = r["tariffPct"] + t_mod
            effective_cost = r["costPerUnit"] * (1 + effective_tariff / 100)
            available_routes.append({
                **r,
                "effectiveCost": round(effective_cost, 2),
                "effectiveTariff": round(effective_tariff, 2),
            })
        available_routes.sort(key=lambda r: r["effectiveCost"])

        customer_max_lead = 0
        for route in available_routes:
            if remaining_demand <= 0:
                break
            wh = wh_state.get(route["from"])
            if not wh or wh["remaining"] <= 0:
                continue
            can_ship = min(remaining_demand, wh["remaining"])
            ship_cost = can_ship * route["effectiveCost"]

            allocations.append({
                "route": route["id"],
                "from": route["from"],
                "to": route["to"],
                "fromName": wh["name"],
                "toName": customer["name"],
                "units": can_ship,
                "cost": round(ship_cost, 2),
                "costPerUnit": route["effectiveCost"],
                "leadTimeDays": route["leadTimeDays"],
                "tariff": route["effectiveTariff"],
                "mode": route["mode"],
                "distance": route["distance"],
            })

            wh["allocated"] += can_ship
            wh["remaining"] -= can_ship
            total_cost += ship_cost
            total_units += can_ship
            remaining_demand -= can_ship
            customer_max_lead = max(customer_max_lead, route["leadTimeDays"])

        if remaining_demand > 0:
            unmet_demand += remaining_demand

        if customer_max_lead > customer.get("slaLeadDays", 999) and customer_max_lead > 0:
            sla_violations.append({
                "customer": customer["name"],
                "customerId": customer["id"],
                "sla": customer["slaLeadDays"],
                "actualLead": customer_max_lead,
                "priority": customer["priority"],
            })

    avg_lead = 0
    if total_units > 0:
        avg_lead = sum(a["leadTimeDays"] * a["units"] for a in allocations) / total_units

    warehouse_usage = []
    for wh_id, wh in wh_state.items():
        utilization = round(wh["allocated"] / wh["effectiveCapacity"] * 100, 1) if wh["effectiveCapacity"] > 0 else 0
        warehouse_usage.append({
            "id": wh_id, "name": wh["name"],
            "capacity": wh["effectiveCapacity"],
            "stock": wh["effectiveStock"],
            "allocated": wh["allocated"],
            "remaining": wh["remaining"],
            "utilization": utilization,
        })

    return {
        "totalCost": round(total_cost, 2),
        "totalUnits": total_units,
        "unmetDemand": unmet_demand,
        "avgLeadTime": round(avg_lead, 1),
        "routeCount": len(allocations),
        "allocations": allocations,
        "warehouseUsage": warehouse_usage,
        "slaViolations": sla_violations,
    }


def build_modifiers(intent: dict) -> dict:
    modifiers = {}
    action = intent.get("action")

    if action == "tariff_change":
        pct = intent.get("percentage", 0)
        direction = intent.get("direction", "increase")
        actual_pct = pct if direction == "increase" else -pct
        wh_id = intent.get("warehouse_id")
        modifiers["tariff_modifier"] = {}
        if wh_id == "ALL":
            for r in ROUTES:
                modifiers["tariff_modifier"][r["id"]] = actual_pct
        elif wh_id:
            modifiers["tariff_modifier"][wh_id] = actual_pct

    elif action == "demand_change":
        pct = intent.get("percentage", 0)
        direction = intent.get("direction", "increase")
        multiplier = pct / 100 if direction == "increase" else -pct / 100
        target = intent.get("target")
        target_type = intent.get("target_type", "segment")
        modifiers["demand_modifier"] = {}
        if target_type == "segment":
            if target == "all":
                for c in CUSTOMERS:
                    modifiers["demand_modifier"][c["id"]] = round(c["demandUnits"] * multiplier)
            elif target in SEGMENT_MAP:
                for cid in SEGMENT_MAP[target]:
                    c = CUST_MAP[cid]
                    modifiers["demand_modifier"][cid] = round(c["demandUnits"] * multiplier)
        elif target_type == "customer" and target in CUST_MAP:
            c = CUST_MAP[target]
            modifiers["demand_modifier"][target] = round(c["demandUnits"] * multiplier)

    elif action == "warehouse_shutdown":
        wh_id = intent.get("warehouse_id")
        if wh_id:
            modifiers["disabled_warehouses"] = [wh_id]

    elif action == "capacity_change":
        pct = intent.get("percentage", 0)
        direction = intent.get("direction", "decrease")
        wh_id = intent.get("warehouse_id")
        if wh_id and wh_id in WH_MAP:
            wh = WH_MAP[wh_id]
            change = round(wh["capacity"] * pct / 100)
            if direction == "decrease":
                change = -change
            modifiers["capacity_modifier"] = {wh_id: change}

    return modifiers


# ============================================================
# DISRUPTION DETECTION ENGINE (NEW in v2)
# ============================================================

DISRUPTION_TEMPLATES = [
    {"type": "Typhoon Warning", "severity": 0.85, "region": "APAC", "affectedWH": ["WH-SNG", "WH-MUM"], "category": "Weather", "description": "Tropical cyclone approaching SE Asia; port operations at risk"},
    {"type": "Port Congestion", "severity": 0.72, "region": "NA", "affectedWH": ["WH-SJC"], "category": "Logistics", "description": "LA/Long Beach port backlog exceeding 14-day wait times"},
    {"type": "Tariff Escalation", "severity": 0.68, "region": "APAC", "affectedWH": ["WH-SNG", "WH-MUM"], "category": "Geopolitical", "description": "New 25% tariff on semiconductor equipment from APAC origins"},
    {"type": "Semiconductor Shortage", "severity": 0.91, "region": "Global", "affectedWH": ["WH-DFW", "WH-PHX"], "category": "Supply", "description": "Critical UPS component shortage; lead times extended to 16 weeks"},
    {"type": "Rail Strike", "severity": 0.65, "region": "NA", "affectedWH": ["WH-CHI", "WH-DFW"], "category": "Logistics", "description": "Potential freight rail disruption across US midwest corridor"},
    {"type": "Earthquake Alert", "severity": 0.78, "region": "APAC", "affectedWH": ["WH-MUM"], "category": "Weather", "description": "Seismic activity near Gujarat; Mumbai warehouse inspections required"},
    {"type": "Cyber Incident", "severity": 0.82, "region": "EMEA", "affectedWH": ["WH-FRA"], "category": "Security", "description": "Ransomware targeting European logistics management systems"},
    {"type": "Demand Spike", "severity": 0.60, "region": "NA", "affectedWH": ["WH-DFW", "WH-CLT"], "category": "Demand", "description": "Hyperscaler accelerating deployment timeline by 6 weeks"},
]

# In-memory alert store (would be DB in production)
ALERT_STORE: List[Dict] = []


def compute_risk_score(event: dict, baseline: dict) -> float:
    """Risk = severity × 0.4 + costExposure × 0.35 + slaRisk × 0.25"""
    severity_weight = 0.4
    cost_weight = 0.35
    sla_weight = 0.25

    affected_routes = [r for r in ROUTES if r["from"] in event["affectedWH"]]
    affected_demand = sum(
        CUST_MAP.get(r["to"], {}).get("demandUnits", 0) for r in affected_routes
    )
    total_demand = sum(c["demandUnits"] for c in CUSTOMERS)
    cost_exposure = affected_demand / total_demand if total_demand > 0 else 0

    critical_count = sum(
        1 for r in affected_routes
        if CUST_MAP.get(r["to"], {}).get("priority") == "Critical"
    )
    sla_risk = min(1.0, critical_count / 4)

    score = event["severity"] * severity_weight + cost_exposure * cost_weight + sla_risk * sla_weight
    return round(score, 3)


def simulate_disruption_impact(event: dict, baseline: dict) -> dict:
    """Run impact simulation through the solver for a disruption event."""
    mods = {}
    cat = event.get("category", "")

    if cat in ("Weather", "Security"):
        mods["disabled_warehouses"] = event["affectedWH"]
    elif cat == "Geopolitical":
        mods["tariff_modifier"] = {wh: 25 for wh in event["affectedWH"]}
    elif cat == "Supply":
        mods["capacity_modifier"] = {}
        for wh_id in event["affectedWH"]:
            w = WH_MAP.get(wh_id)
            if w:
                mods["capacity_modifier"][wh_id] = -round(w["capacity"] * 0.4)
    elif cat == "Demand":
        mods["demand_modifier"] = {}
        for c in CUSTOMERS:
            if c["segment"] == "Hyperscale":
                mods["demand_modifier"][c["id"]] = round(c["demandUnits"] * 0.3)
    elif cat == "Logistics":
        mods["capacity_modifier"] = {}
        for wh_id in event["affectedWH"]:
            w = WH_MAP.get(wh_id)
            if w:
                mods["capacity_modifier"][wh_id] = -round(w["capacity"] * 0.3)

    scenario = run_optimization(mods)
    cost_delta = ((scenario["totalCost"] - baseline["totalCost"]) / baseline["totalCost"] * 100) if baseline["totalCost"] > 0 else 0
    lead_delta = ((scenario["avgLeadTime"] - baseline["avgLeadTime"]) / baseline["avgLeadTime"] * 100) if baseline["avgLeadTime"] > 0 else 0

    return {
        "scenario": scenario,
        "costDelta": round(cost_delta, 1),
        "leadDelta": round(lead_delta, 1),
        "modifiers": mods,
    }


def generate_alerts(baseline: dict) -> List[Dict]:
    """Generate alerts for all high-risk disruption events."""
    alerts = []
    for tmpl in DISRUPTION_TEMPLATES:
        risk_score = compute_risk_score(tmpl, baseline)
        alert = {
            "id": f"ALT-{uuid.uuid4().hex[:8].upper()}",
            "type": tmpl["type"],
            "severity": tmpl["severity"],
            "riskScore": risk_score,
            "region": tmpl["region"],
            "affectedWH": tmpl["affectedWH"],
            "category": tmpl["category"],
            "description": tmpl["description"],
            "status": "active" if risk_score > 0.7 else "monitoring",
            "timestamp": (datetime.utcnow() - timedelta(hours=int(hash(tmpl["type"]) % 72))).isoformat() + "Z",
            "requiresAction": risk_score > 0.7,
        }
        alerts.append(alert)

    alerts.sort(key=lambda a: a["riskScore"], reverse=True)
    return alerts


# ============================================================
# EXPLANATION ENGINE v2
# ============================================================

def generate_explanation(intent: dict, baseline: dict, scenario: dict) -> str:
    cost_delta = ((scenario["totalCost"] - baseline["totalCost"]) / baseline["totalCost"]) * 100 if baseline["totalCost"] > 0 else 0
    lead_delta = ((scenario["avgLeadTime"] - baseline["avgLeadTime"]) / baseline["avgLeadTime"]) * 100 if baseline["avgLeadTime"] > 0 else 0

    action = intent.get("action", "unknown")
    if action == "tariff_change":
        wh_name = WH_MAP.get(intent.get("warehouse_id", ""), {}).get("name", "multiple locations")
        desc = f"Tariff increased by {intent.get('percentage', 0)}% on routes from {wh_name}"
    elif action == "demand_change":
        desc = f"Demand {'increased' if intent.get('direction') == 'increase' else 'decreased'} by {intent.get('percentage', 0)}% for {intent.get('target', 'unknown')} customers"
    elif action == "warehouse_shutdown":
        wh_name = WH_MAP.get(intent.get("warehouse_id", ""), {}).get("name", "unknown")
        desc = f"Warehouse shutdown: {wh_name}"
    elif action == "capacity_change":
        wh_name = WH_MAP.get(intent.get("warehouse_id", ""), {}).get("name", "unknown")
        desc = f"Capacity {'reduced' if intent.get('direction') == 'decrease' else 'increased'} by {intent.get('percentage', 0)}% at {wh_name}"
    else:
        desc = "Baseline analysis"

    top_wh = max(scenario["warehouseUsage"], key=lambda w: w["utilization"]) if scenario["warehouseUsage"] else {"name": "N/A", "utilization": 0}
    sla_text = "None" if not scenario["slaViolations"] else "; ".join(
        f"{v['customer']} (SLA: {v['sla']}d, actual: {v['actualLead']}d)" for v in scenario["slaViolations"]
    )

    # Try LLM explanation
    prompt = f"""<|begin_of_turn|>system
You are a senior supply chain analyst. Generate a concise executive summary (4-5 sentences).
RULES: ONLY use exact numbers provided. Be direct and data-driven.
<|end_of_turn|>
<|begin_of_turn|>user
SCENARIO: {desc}
Baseline cost: ${baseline['totalCost']:,.0f} | Scenario cost: ${scenario['totalCost']:,.0f} | Change: {cost_delta:+.1f}%
Lead time: {baseline['avgLeadTime']:.1f}d → {scenario['avgLeadTime']:.1f}d ({lead_delta:+.1f}%)
Units shipped: {scenario['totalUnits']:,} | Unmet: {scenario['unmetDemand']:,}
SLA violations: {sla_text} | Top warehouse: {top_wh['name']} at {top_wh['utilization']:.0f}%
<|end_of_turn|>
<|begin_of_turn|>assistant
"""
    llm_result = call_llama(prompt, max_tokens=300, temperature=0.15)

    if llm_result:
        return llm_result

    # Deterministic fallback
    parts = []
    cost_dir = "increased" if cost_delta > 0 else "decreased"
    parts.append(f"Under this scenario, total logistics cost {cost_dir} by {abs(cost_delta):.1f}% (${baseline['totalCost']:,.0f} → ${scenario['totalCost']:,.0f}).")
    if abs(lead_delta) > 0.5:
        lead_dir = "increased" if lead_delta > 0 else "decreased"
        parts.append(f"Average lead time {lead_dir} by {abs(lead_delta):.1f}% to {scenario['avgLeadTime']:.1f} days.")
    if scenario["unmetDemand"] > 0:
        parts.append(f"Critical: {scenario['unmetDemand']:,} units of demand cannot be fulfilled.")
    else:
        parts.append("All customer demand is fully satisfied.")
    if scenario["slaViolations"]:
        parts.append(f"SLA at risk: {sla_text}.")
    if cost_delta > 10:
        parts.append("Recommendation: Evaluate alternate sourcing or negotiate tariff exemptions.")
    elif scenario["unmetDemand"] > 0:
        parts.append("Recommendation: Activate backup supply routes.")
    else:
        parts.append("Recommendation: Monitor cost trend and lock favorable routing rates.")
    return " ".join(parts)


def generate_report_content(intent_or_query: str, baseline: dict, scenario: dict) -> dict:
    """Generate full strategy report content."""
    cost_delta = ((scenario["totalCost"] - baseline["totalCost"]) / baseline["totalCost"]) * 100 if baseline["totalCost"] > 0 else 0
    lead_delta = ((scenario["avgLeadTime"] - baseline["avgLeadTime"]) / baseline["avgLeadTime"]) * 100 if baseline["avgLeadTime"] > 0 else 0

    cost_dir = "increased" if cost_delta > 0 else "decreased"
    fulfillment_rate = round(scenario["totalUnits"] / sum(c["demandUnits"] for c in CUSTOMERS) * 100, 1) if CUSTOMERS else 0
    high_util_count = len([w for w in scenario["warehouseUsage"] if w["utilization"] > 85])

    summary = (
        f"Executive Summary: Under the scenario \"{intent_or_query}\", total logistics cost {cost_dir} by {abs(cost_delta):.1f}% "
        f"from ${baseline['totalCost']:,.0f} to ${scenario['totalCost']:,.0f}. "
        f"{'Critical: ' + str(scenario['unmetDemand']) + ' units of unmet demand.' if scenario['unmetDemand'] > 0 else 'All demand fully satisfied.'} "
        f"Average lead time: {scenario['avgLeadTime']:.1f} days ({lead_delta:+.1f}% change)."
    )

    risk_analysis = (
        f"Risk Analysis: Network operating at {fulfillment_rate}% demand fulfillment across {scenario['routeCount']} active routes. "
        f"{str(len(scenario['slaViolations'])) + ' SLA breach(es) flagged.' if scenario['slaViolations'] else 'No SLA violations.'} "
        f"{high_util_count} facility(ies) operating above 85% utilization threshold."
    )

    if cost_delta > 5:
        rec1 = "Negotiate tariff exemptions or activate alternate sourcing to offset cost increase"
    else:
        rec1 = "Lock in current favorable routing costs through long-term carrier contracts"

    if scenario["unmetDemand"] > 0:
        rec2 = "Activate backup supply corridors and expedite procurement for critical shortfalls"
    else:
        rec2 = "Pre-position safety stock at regional DCs to buffer against future disruptions"

    rec3 = f"Implement real-time monitoring on {scenario['routeCount']} active routes for plan deviation detection"

    return {
        "title": f"Strategy Report: {intent_or_query}",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "summary": summary,
        "riskAnalysis": risk_analysis,
        "recommendations": [rec1, rec2, rec3],
        "metrics": {
            "costDelta": round(cost_delta, 1),
            "leadDelta": round(lead_delta, 1),
            "unmetDemand": scenario["unmetDemand"],
            "routeCount": scenario["routeCount"],
            "fulfillmentRate": fulfillment_rate,
            "slaViolations": len(scenario["slaViolations"]),
        },
        "warehouseUsage": scenario["warehouseUsage"],
        "allocations": scenario["allocations"][:15],
        "slaViolations": scenario["slaViolations"],
    }


# ============================================================
# PYDANTIC MODELS
# ============================================================

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    explanation: str
    intent: dict
    baseline: dict
    scenario: Optional[dict] = None
    is_scenario: bool = False

class SimulateRequest(BaseModel):
    event_type: str
    affected_warehouses: List[str] = Field(default_factory=list)
    category: str = "Weather"
    severity: float = 0.8

class ReportRequest(BaseModel):
    scenarioName: str
    modifiers: Optional[dict] = None
    costImpact: Optional[float] = None
    serviceLevelImpact: Optional[float] = None

class ConnectorInfo(BaseModel):
    type: str
    name: str
    status: str = "active"
    capabilities: List[str] = Field(default_factory=list)


# ============================================================
# COMPUTE BASELINE
# ============================================================

BASELINE = run_optimization()


# ============================================================
# API ENDPOINTS
# ============================================================

@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "Supply Chain Intelligence API",
        "version": "2.0.0",
        "features": ["optimization", "disruption-detection", "strategy-reports", "plug-and-play-connectors"],
        "connector": ACTIVE_CONNECTOR.connector_name,
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "llm_configured": bool(HF_API_TOKEN),
        "model": LLAMA_MODEL,
        "connector": ACTIVE_CONNECTOR.connector_type,
        "version": "2.0.0",
    }


# --- Core Optimization ---

@app.get("/baseline")
def get_baseline():
    return BASELINE


@app.get("/network")
def get_network():
    return {
        "warehouses": WAREHOUSES,
        "customers": CUSTOMERS,
        "routes": ROUTES,
        "products": PRODUCTS,
    }


@app.post("/query", response_model=QueryResponse)
def handle_query(req: QueryRequest):
    query = req.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    intent = parse_intent_llm(query)
    action = intent.get("action", "general_question")

    if action == "baseline":
        return QueryResponse(
            explanation=(
                f"Current baseline: ${BASELINE['totalCost']:,.0f} total cost for "
                f"{BASELINE['totalUnits']:,} units across {BASELINE['routeCount']} routes. "
                f"Avg lead time {BASELINE['avgLeadTime']:.1f}d. {BASELINE['unmetDemand']} units unmet."
            ),
            intent=intent, baseline=BASELINE, scenario=BASELINE, is_scenario=True,
        )

    if action == "general_question":
        return QueryResponse(
            explanation=(
                f"The network serves {len(CUSTOMERS)} customers via {len(WAREHOUSES)} warehouses. "
                f"Baseline: ${BASELINE['totalCost']:,.0f} cost, {BASELINE['totalUnits']:,} units, {BASELINE['avgLeadTime']:.1f}d avg lead. "
                f"Try what-if scenarios: tariff changes, demand surges, warehouse shutdowns, capacity adjustments."
            ),
            intent=intent, baseline=BASELINE, is_scenario=False,
        )

    modifiers = build_modifiers(intent)
    scenario = run_optimization(modifiers)
    explanation = generate_explanation(intent, BASELINE, scenario)

    return QueryResponse(
        explanation=explanation, intent=intent,
        baseline=BASELINE, scenario=scenario, is_scenario=True,
    )


# --- Disruption Detection (NEW v2) ---

@app.get("/api/alerts")
def get_alerts(
    status: Optional[str] = Query(None, description="Filter by status: active, monitoring, resolved"),
    region: Optional[str] = Query(None, description="Filter by region: NA, APAC, EMEA, Global"),
    min_risk: Optional[float] = Query(None, description="Minimum risk score threshold"),
):
    """
    GET /api/alerts — Returns active disruption alerts with risk scores.
    Each alert includes: type, severity, riskScore, region, affectedWH,
    category, description, status, timestamp.
    """
    alerts = generate_alerts(BASELINE)

    if status:
        alerts = [a for a in alerts if a["status"] == status]
    if region:
        alerts = [a for a in alerts if a["region"] == region]
    if min_risk is not None:
        alerts = [a for a in alerts if a["riskScore"] >= min_risk]

    return {
        "alerts": alerts,
        "totalCount": len(alerts),
        "activeCount": len([a for a in alerts if a["status"] == "active"]),
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


@app.post("/api/alerts/simulate")
def simulate_alert(req: SimulateRequest):
    """
    POST /api/alerts/simulate — Run impact simulation for a disruption event.
    Returns scenario results + cost/lead deltas.
    """
    event = {
        "type": req.event_type,
        "severity": req.severity,
        "region": "Custom",
        "affectedWH": req.affected_warehouses or [],
        "category": req.category,
        "description": f"Custom simulation: {req.event_type}",
    }

    if not event["affectedWH"]:
        raise HTTPException(status_code=400, detail="affected_warehouses cannot be empty")

    for wh in event["affectedWH"]:
        if wh not in WH_MAP:
            raise HTTPException(status_code=400, detail=f"Invalid warehouse ID: {wh}")

    risk_score = compute_risk_score(event, BASELINE)
    impact = simulate_disruption_impact(event, BASELINE)

    return {
        "event": event,
        "riskScore": risk_score,
        "impact": {
            "costDelta": impact["costDelta"],
            "leadDelta": impact["leadDelta"],
            "unmetDemand": impact["scenario"]["unmetDemand"],
            "slaViolations": impact["scenario"]["slaViolations"],
            "routeCount": impact["scenario"]["routeCount"],
        },
        "scenario": impact["scenario"],
        "baseline": BASELINE,
    }


# --- Strategy Reports (NEW v2) ---

@app.post("/api/reports")
def generate_report(req: ReportRequest):
    """
    POST /api/reports — Generate AI strategy report from scenario results.
    Accepts scenarioName and optional modifiers. Returns full report.
    """
    if not req.scenarioName:
        raise HTTPException(status_code=400, detail="scenarioName is required")

    # If modifiers provided, run custom scenario
    if req.modifiers:
        scenario = run_optimization(req.modifiers)
    else:
        # Parse scenarioName as a query
        intent = parse_intent_rules(req.scenarioName)
        if intent["action"] == "general_question":
            scenario = BASELINE
        else:
            modifiers = build_modifiers(intent)
            scenario = run_optimization(modifiers)

    report = generate_report_content(req.scenarioName, BASELINE, scenario)

    return {
        "reportId": f"RPT-{uuid.uuid4().hex[:8].upper()}",
        "report": report,
        "scenario": scenario,
        "baseline": BASELINE,
    }


@app.get("/api/reports/templates")
def get_report_templates():
    """GET /api/reports/templates — Available report templates."""
    return {
        "templates": [
            {"id": "executive", "name": "Executive Summary", "sections": ["summary", "metrics", "recommendations"]},
            {"id": "detailed", "name": "Detailed Analysis", "sections": ["summary", "riskAnalysis", "warehouseUsage", "allocations", "recommendations"]},
            {"id": "risk", "name": "Risk Assessment", "sections": ["riskAnalysis", "slaViolations", "warehouseUsage", "recommendations"]},
        ]
    }


# --- Data Connector Info ---

@app.get("/api/connector")
def get_connector_info():
    """GET /api/connector — Current data connector status."""
    return ConnectorInfo(
        type=ACTIVE_CONNECTOR.connector_type,
        name=ACTIVE_CONNECTOR.connector_name,
        status="active",
        capabilities=[
            "warehouses", "customers", "routes", "products",
            "inventory_levels", "disruption_feeds"
        ],
    )


@app.get("/api/connector/schema")
def get_connector_schema():
    """
    GET /api/connector/schema — Data schema for ERP/SCM integration.
    Use this to understand what data format the system expects.
    """
    return {
        "warehouse_schema": {
            "id": "string (unique)", "name": "string", "location": "string",
            "lat": "float", "lng": "float", "capacity": "int",
            "currentStock": "int", "type": "string",
            "specialization": "string", "operatingCostPerUnit": "float",
            "region": "string (NA|APAC|EMEA)",
        },
        "customer_schema": {
            "id": "string (unique)", "name": "string", "location": "string",
            "lat": "float", "lng": "float", "demandUnits": "int",
            "priority": "string (Critical|High|Medium|Low)",
            "segment": "string", "slaLeadDays": "int",
        },
        "route_schema": {
            "id": "string (unique)", "from": "warehouse_id", "to": "customer_id",
            "distance": "int (miles)", "costPerUnit": "float",
            "leadTimeDays": "float", "tariffPct": "float",
            "mode": "string (Ground|Ocean|Air|Local)",
        },
        "integration_notes": [
            "Implement DataConnector interface in backend/connectors/",
            "Register connector: ACTIVE_CONNECTOR = YourConnector()",
            "All APIs automatically use the active connector's data",
            "Supported: SAP S/4HANA, Oracle SCM, Kinaxis, Blue Yonder, custom REST",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
