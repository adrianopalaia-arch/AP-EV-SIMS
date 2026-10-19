"""Archive public bookmaker rule documents, without guessing their applicability."""
import hashlib,json
from pathlib import Path
from datetime import datetime,timezone
from .integrity import digest,utc
from .providers.live import http_get
from .research_store import ResearchStore
from .publication import atomic_json

SOURCES={
 'fanduel':('https://d38ayms4az88sz.cloudfront.net/SB/IL/2026-07-30T12-42-48.html','IL'),
 'draftkings':('https://sportsbook.draftkings.com/help/sport-rules/hockey',None)}

def capture(root,*,transport=http_get):
    root=Path(root);s=ResearchStore(root/'data');folder=s.root/'manifests/book-rules';folder.mkdir(exist_ok=True)
    at=datetime.now(timezone.utc).isoformat();records=[]
    for book,(url,jurisdiction) in SOURCES.items():
        previous=[json.loads(p.read_text()) for p in folder.glob('*.json')]
        matches=[r for r in previous if r['book']==book and r['url']==url]
        old=max(matches,key=lambda x:utc(x['captured_at'])) if matches else None
        if old and 0<=(utc(at)-utc(old['captured_at'])).total_seconds()<86400:
            raw=(s.root/old['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=old['payload_hash'] or digest({k:v for k,v in old.items() if k!='manifest_id'})!=old['manifest_id']:
                raise ValueError('BOOK_RULE_SOURCE_HASH_MISMATCH')
            records.append(old);continue
        response=transport(url,{'User-Agent':'AP-EV-SIMS private research','Accept':'text/html'})
        h=hashlib.sha256(response.body).hexdigest();raw=s.root/'raw/results'/('book-rules-'+h+'.html');s._immutable(raw,response.body)
        body=dict(book=book,url=url,jurisdiction_scope=jurisdiction,status=response.status,
            captured_at=response.fetched_at,available_at=response.fetched_at,payload_hash=h,path=str(raw.relative_to(s.root)),
            applicability='NOT_VERIFIED_FOR_ENTRY',reason='JURISDICTION_AND_MARKET_TERMS_REVIEW_REQUIRED',
            historical_backdating_allowed=False,settlement_authority=False)
        body['manifest_id']=digest(body);s._immutable(folder/(body['manifest_id']+'.json'),json.dumps(body,sort_keys=True).encode());records.append(body)
    report=dict(generated_at=at,sources=records,scope='Source documents only; no pre-entry applicability or completed terms parser is claimed.',settlement_authority=False)
    atomic_json(root/'outputs/book_rule_source_status.json',report);return report
