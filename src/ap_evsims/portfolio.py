from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class PortfolioConfig:
    max_total_units: float = 1.0
    max_event_units: float = 0.5
    max_shared_risk_units: float = 0.5


def allocate_card(screened: list[dict], unit_usd: float, cfg: PortfolioConfig = PortfolioConfig()) -> list[dict]:
    ordered=sorted(screened,key=lambda r:r.get("ev_conservative",-999),reverse=True)
    total=0.0; event_exposure={}; risk_exposure={}; out=[]
    for original in ordered:
        r=dict(original); r["reasons"]=list(original.get("reasons",[]))
        if r.get("status")!="CORE_CANDIDATE": out.append(r); continue
        stake=float(r.get("stake_usd",0)); units=stake/unit_usd if unit_usd else 0
        event=r.get("event_group","")
        risks=r.get("risk_groups",[])
        if total+units > cfg.max_total_units+1e-9:
            r["status"]="PASS";r["stake_usd"]=0;r["reasons"].append("CARD_TOTAL_EXPOSURE_CAP")
        elif event_exposure.get(event,0)+units > cfg.max_event_units+1e-9:
            r["status"]="PASS";r["stake_usd"]=0;r["reasons"].append("EVENT_EXPOSURE_CAP")
        elif any(risk_exposure.get(g,0) > 0 for g in risks):
            r["status"]="PASS";r["stake_usd"]=0;r["reasons"].append("SHARED_RISK_ALREADY_SELECTED")
        elif any(risk_exposure.get(g,0)+units > cfg.max_shared_risk_units+1e-9 for g in risks):
            r["status"]="PASS";r["stake_usd"]=0;r["reasons"].append("SHARED_RISK_EXPOSURE_CAP")
        else:
            total+=units; event_exposure[event]=event_exposure.get(event,0)+units
            for g in risks:risk_exposure[g]=risk_exposure.get(g,0)+units
        out.append(r)
    return out
