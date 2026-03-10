# Supply Chain Intelligence v2.0 — Deployment Guide

## Architecture

```
┌─────────────────────────────────────────────────┐
│                   FRONTEND                       │
│         React + Vite (Netlify)                  │
│  ┌──────────┬──────────┬────────┬──────────┐   │
│  │ Digital  │  Chat +  │ Alert  │ Report   │   │
│  │ Twin Map │  Solver  │ Panel  │ Generator│   │
│  │ (D3.js)  │          │        │ (Plotly) │   │
│  └──────────┴──────────┴────────┴──────────┘   │
│         ↕ REST API ↕ Claude API ↕              │
└─────────────────────────────────────────────────┘
                       │
┌─────────────────────────────────────────────────┐
│                   BACKEND                        │
│         FastAPI + Llama 3 (Render)              │
│  ┌──────────────────────────────────────────┐   │
│  │        DataConnector Interface            │   │
│  │  (Plug-and-play: SAP, Oracle, Kinaxis)   │   │
│  └──────────────────────────────────────────┘   │
│  ┌─────────┬──────────┬─────────┬──────────┐   │
│  │ /query  │/api/alerts│/api/    │/api/     │   │
│  │ Solver  │ Disruption│reports  │connector │   │
│  │ + NLP   │ Detection │ Gen    │ Schema   │   │
│  └─────────┴──────────┴─────────┴──────────┘   │
└─────────────────────────────────────────────────┘
```

## New v2 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/query` | POST | Scenario analysis (v1 + enhanced) |
| `/api/alerts` | GET | Disruption alerts with risk scores |
| `/api/alerts/simulate` | POST | Impact simulation for events |
| `/api/reports` | POST | AI strategy report generation |
| `/api/reports/templates` | GET | Available report templates |
| `/api/connector` | GET | Active data connector info |
| `/api/connector/schema` | GET | Schema for ERP integration |

## Backend Deployment (Render)

1. Push `backend_v2_main.py` as `main.py` to your Render repo
2. Update `requirements.txt` with the v2 version
3. Set env vars:
   - `HF_API_TOKEN` — HuggingFace token for Llama 3
   - `PORT` — defaults to 8000

## Frontend Deployment (Netlify)

1. Replace `src/App.jsx` with `supply-chain-v2.jsx` content
2. `npm run build && netlify deploy --prod`
3. Set `VITE_API_URL` to your Render backend URL

## ERP Integration (Future)

To connect a real data source:

```python
# backend/connectors/sap_connector.py
from main import DataConnector

class SAPConnector(DataConnector):
    def __init__(self, host, client, user, password):
        self.connection = pyrfc.Connection(...)
    
    def get_warehouses(self):
        # Query SAP MM/WM module
        return self.connection.call('BAPI_WAREHOUSE_LIST')
    
    def get_routes(self):
        # Query SAP TM module
        return self.connection.call('BAPI_ROUTE_LIST')

# Register in main.py:
# ACTIVE_CONNECTOR = SAPConnector(host="...", ...)
```

## What's New in v2

- **Digital Twin Map**: D3 + TopoJSON world outlines, distance/time labels, utilization arcs
- **Disruption Detection**: Risk scoring engine, impact simulation, alert feed
- **AI Reports**: Claude/Llama-powered executive strategy reports with Plotly charts
- **Plug-and-Play**: DataConnector interface for SAP, Oracle, Kinaxis, Blue Yonder
- **Enhanced Solver**: SLA violation tracking, region awareness
