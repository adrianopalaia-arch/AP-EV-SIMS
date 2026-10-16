"""Bounded public-stat downloads with immutable byte hashes and actual capture time.

Public reachability does not assert redistribution rights or historical as-of
authenticity. Raw archives remain local. No cookies, API keys, or bypass retries.
"""
import csv
import hashlib
import io
import json
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from .live import http_get
from ..integrity import digest,utc
from ..research_store import ResearchStore

HOSTS={'api.nhle.com','api-web.nhle.com','statsapi.mlb.com','stats.nba.com','cdn.nba.com',
       'github.com','api.github.com','raw.githubusercontent.com','site.api.espn.com'}


class PublicStatsArchive:
    def __init__(self,root,transport=http_get):
        self.root=Path(root);self.transport=transport;self.folder=self.root/'manifests/public'
        self.folder.mkdir(parents=True,exist_ok=True)

    def capture(self,sport,url,*,format='json',refresh=False):
        p=urlparse(url)
        if sport not in ('NFL','NBA','NHL','MLB') or p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password:
            raise ValueError('UNAPPROVED_PUBLIC_SOURCE')
        if any(k.lower() in ('apikey','api_key','token','authorization') for k in parse_qs(p.query)):raise ValueError('SECRET_IN_METADATA')
        if format not in ('json','csv','parquet'):raise ValueError('UNSUPPORTED_SOURCE_FORMAT')
        key=digest([sport,url,format]);cached=[]
        for path in self.folder.glob('*.json'):
            m=json.loads(path.read_text(encoding='utf-8'))
            if (m['sport'],m['url'],m['format'],m['status'])==(sport,url,format,200):cached.append(m)
        if cached and not refresh:
            m=max(cached,key=lambda r:utc(r['captured_at']));self.read(m);return m
        r=self.transport(url,{'User-Agent':'AP-EV-SIMS/3.0 private research','Accept':'application/json,text/csv,*/*'})
        h=hashlib.sha256(r.body).hexdigest();path=self.root/'raw'/sport.lower()/'public'/(h+'.'+format)
        path.parent.mkdir(parents=True,exist_ok=True);ResearchStore._immutable(path,r.body)
        body=dict(sport=sport,url=url,format=format,status=r.status,captured_at=r.fetched_at,available_at=r.fetched_at,
            hash=h,bytes=len(r.body),path=str(path.relative_to(self.root)),
            historical_provenance='RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF',redistribution_permission='NOT_ASSUMED')
        body['manifest_id']=digest(body)
        ResearchStore._immutable(self.folder/(body['manifest_id']+'.json'),json.dumps(body,sort_keys=True,indent=2).encode())
        return body

    def read(self,m):
        if digest({k:v for k,v in m.items() if k!='manifest_id'})!=m['manifest_id'] or utc(m['captured_at'])!=utc(m['available_at']):
            raise ValueError('PUBLIC_MANIFEST_MISMATCH')
        p=(self.root/m['path']).resolve()
        if self.root.resolve() not in p.parents:raise ValueError('SOURCE_PATH_ESCAPE')
        raw=p.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=m['hash']:raise ValueError('PUBLIC_PAYLOAD_HASH_MISMATCH')
        if m['status']!=200:raise ValueError('BLOCKED_SOURCE_ACCESS')
        if m['format']=='json':return json.loads(raw)
        if m['format']=='csv':return list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        import pyarrow.parquet as pq
        return pq.read_table(io.BytesIO(raw)).to_pylist()
