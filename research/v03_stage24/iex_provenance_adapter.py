"""Optional IEX GET provenance adapter for a FUTURE T0-frozen research session.

Preserves existing fetch_after_freeze and review logic unchanged. Uses only the
actual HTTP response status and terminal page token; never invents an API success
or infers a missing IEX bar means the stock had no trades market-wide.
Not wired into the one-off live workflow. No API call on import.
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.request

from prospective_iex_research import fetch_after_freeze,review
from iex_timestamp_provenance import build_minute_provenance

UTC=dt.timezone.utc


class _ObservedResponse:
    def __init__(self,raw,records):
        self.raw=raw
        self.records=records
        self.entered=None
        self.read_count=0

    def __enter__(self):
        self.entered=self.raw.__enter__()
        return self

    def __exit__(self,*args):
        return self.raw.__exit__(*args)

    def read(self,n=-1):
        if self.read_count:
            raise ValueError("DUPLICATE_RESPONSE_READ")
        self.read_count+=1
        if self.entered is None:
            raise ValueError("RESPONSE_NOT_ENTERED")
        status=getattr(self.entered,"status",None)
        if status is None:
            getter=getattr(self.entered,"getcode",None)
            status=getter() if callable(getter) else None
        if type(status) is not int or status!=200:
            raise ValueError("UNVERIFIED_HTTP_STATUS")
        payload=self.entered.read(n)
        # Parsing is only for actual pagination evidence. The original
        # fetch_after_freeze still performs its own strict schema validation.
        obj=json.loads(payload)
        if type(obj) is not dict:
            raise ValueError("BAD_PAGINATION_EVIDENCE")
        nxt=obj.get("next_page_token")
        if nxt is not None and (type(nxt) is not str or not nxt):
            raise ValueError("BAD_PAGINATION_EVIDENCE")
        self.records.append({"status":status,"terminal":nxt is None})
        return payload


def fetch_review_with_provenance(frozen,review_time,key,secret,
                                 recorded_at,opener=None):
    """Fetch once after T0, review unchanged, then return timestamp evidence.

    A failed GET, missing HTTP status, incomplete pagination or invalid review
    raises; no partial 'API OK' report is returned.
    """
    records=[]
    underlying=opener or urllib.request.urlopen

    def observed_opener(req,timeout):
        if req.get_method()!="GET" or "/v2/stocks/bars?" not in req.full_url:
            raise ValueError("NON_READONLY_REQUEST")
        if "feed=iex" not in req.full_url or "/orders" in req.full_url:
            raise ValueError("WRONG_FEED_OR_ORDER")
        return _ObservedResponse(underlying(req,timeout=timeout),records)

    bars=fetch_after_freeze(frozen,review_time,key,secret,opener=observed_opener)
    checked=review(frozen,bars,review_time)
    if not records:
        # Empty frozen universe needs no HTTP evidence; this helper is not
        # permitted to invent successful HTTP fetches.
        api=None
    else:
        if any(r["terminal"] for r in records[:-1]) or not records[-1]["terminal"]:
            raise ValueError("INCOMPLETE_PAGINATION_EVIDENCE")
        api={"get_only":True,"http_statuses":[r["status"] for r in records],
             "final_page_token_absent":True}
    evidence=build_minute_provenance(frozen,checked,bars,recorded_at,api)
    return checked,evidence
