from __future__ import annotations
import argparse,csv,json
from datetime import datetime, timezone
from pathlib import Path
from .schemas import Candidate
from .calibration import ValidationReport
from .screening import screen_candidate
from .portfolio import allocate_card
from .integrity import ValidationRegistry
from .exposure import ExposureLedger, ExposureLimits
from .decision import ResearchCandidate, decide
from .ledger import Ledger

BOOL=lambda x:str(x).strip().lower() in {"1","true","yes","y"}

def _candidate(row):
    risks=tuple(x for x in row.get("risk_groups","").split(";") if x)
    return Candidate(
        event_id=row["event_id"],sport=row["sport"],market=row["market"],selection=row["selection"],book=row["book"],
        american_odds=int(row["american_odds"]),opposite_odds=int(row["opposite_odds"]) if row.get("opposite_odds") else None,
        quote_time_utc=row["quote_time_utc"],event_time_utc=row["event_time_utc"],data_time_utc=row["data_time_utc"],
        model_version=row["model_version"],model_mode=row["model_mode"],p_model=float(row["p_model"]),p_low=float(row["p_low"]),
        lineup_verified=BOOL(row["lineup_verified"]),role_verified=BOOL(row["role_verified"]),live_state_verified=BOOL(row["live_state_verified"]),
        settlement_verified=BOOL(row["settlement_verified"]),event_group=row["event_group"],risk_groups=risks,
        feature_cutoff_utc=row.get("feature_cutoff_utc") or None)

def main():
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    s=sub.add_parser("screen"); s.add_argument("csv",type=Path); s.add_argument("--now"); s.add_argument("--unit",type=float,default=22); s.add_argument("--output",type=Path,default=Path("screened.json"))
    e=sub.add_parser("evaluate"); e.add_argument("json",type=Path); e.add_argument("--registry",type=Path,required=True)
    d=sub.add_parser("decide"); d.add_argument("json",type=Path); d.add_argument("--registry",type=Path,required=True); d.add_argument("--exposure",type=Path,required=True); d.add_argument("--ledger",type=Path,required=True); d.add_argument("--bankroll",type=float,required=True); d.add_argument("--now",required=True)
    args=ap.parse_args()
    if args.cmd=="evaluate":
        payload=json.loads(args.json.read_text(encoding="utf-8"))
        evidence=ValidationRegistry(args.registry).evaluate(**payload)
        from dataclasses import asdict
        print(json.dumps(asdict(evidence),indent=2,allow_nan=False)); return
    if args.cmd=="decide":
        payload=json.loads(args.json.read_text(encoding="utf-8"))
        registry=ValidationRegistry(args.registry)
        candidate=ResearchCandidate(**payload["candidate"])
        result=decide(candidate,registry.get(payload["report_id"]),registry=registry,
            exposure=ExposureLedger(args.exposure),limits=ExposureLimits(args.bankroll),
            ledger=Ledger(args.ledger),now=args.now)
        print(json.dumps(result,indent=2,allow_nan=False)); return
    if args.cmd=="screen":
        now=datetime.fromisoformat(args.now.replace("Z","+00:00")) if args.now else datetime.now(timezone.utc)
        with args.csv.open(newline="",encoding="utf-8") as f: rows=list(csv.DictReader(f))
        reports={}
        for r in rows:
            key=(r["sport"],r["market"],r["model_version"],r["model_mode"])
            reports[key]=ValidationReport(r["sport"],r["market"],r["model_version"],r["model_mode"],int(r["validation_n"]),float(r["validation_brier"]),float(r["market_brier"]),float(r["validation_logloss"]),float(r["market_logloss"]),r["training_cutoff_utc"],r["validation_end_utc"],BOOL(r["validation_authenticated"]))
        screened=[]
        for r in rows:
            c=_candidate(r); key=(c.sport,c.market,c.model_version,c.model_mode)
            screened.append(screen_candidate(c,reports[key],now,args.unit))
        final=allocate_card(screened,args.unit)
        payload={"generated_utc":now.astimezone(timezone.utc).isoformat(),"unit_usd":args.unit,"results":final}
        args.output.write_text(json.dumps(payload,indent=2),encoding="utf-8")
        print(json.dumps(payload,indent=2))

if __name__=="__main__": main()
