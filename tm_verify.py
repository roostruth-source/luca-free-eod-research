#!/usr/bin/env python3
"""LUCA Time Machine v0.1 — read-only, no orders, no model fitting.

Two deliberately separated kinds of evidence:
  archive: freezes a selection *when it was actually known*, not at session close.
  evaluate: checks later daily bars only, does not infer executable profit.

No calls to the original Work 5-day task, its folders, APIs, or deploys.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import pathlib
import re
import sys
import zipfile
import io
from zoneinfo import ZoneInfo

UTC = dt.timezone.utc
NY = ZoneInfo('America/New_York')
MARK = 'globalThis.LUCA_PAYLOAD='
TICKER = re.compile(r'^[A-Z][A-Z0-9.\-]{0,12}$')
ATTEMPT = re.compile(r'^[A-Za-z0-9_.\-]{8,120}$')

class Blocked(ValueError):
    pass


def check(cond, reason):
    if not cond:
        raise Blocked(reason)


def parse_ts(value):
    check(isinstance(value, str) and value, '필수 시각 누락')
    try:
        t = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        check(t.tzinfo is not None, '시간대 없는 시각 차단')
        return t.astimezone(UTC)
    except (ValueError, TypeError) as e:
        raise Blocked('시각 형식 오류') from e


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(obj):
    return (json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)+'\n').encode('utf-8')


def read_json_bytes(p):
    b = pathlib.Path(p).read_bytes()
    return json.loads(b), b


def payload_from_html(raw):
    html = raw.decode('utf8')
    pos = html.find(MARK)
    check(pos != -1 and html.count(MARK) == 1, 'HTML 내부 원본 선정 자료가 한 개여야 함')
    start = pos + len(MARK)
    try:
        result, length = json.JSONDecoder().raw_decode(html[start:])
    except ValueError as e:
        raise Blocked('HTML 원본 선정 자료 파싱 실패') from e
    check(isinstance(result, dict), '선정 자료는 객체여야 함')
    check(html[start+length:start+length+1] == ';', '선정 객체 종료 확인 실패')
    return result


def ny_session_close(session):
    date = dt.date.fromisoformat(session)
    # Local 16:00 ET handles DST; holiday calendar not inferred or fabricated.
    return dt.datetime.combine(date, dt.time(16), NY).astimezone(UTC)


def atomic_new(path, obj):
    path = pathlib.Path(path)
    data = canonical(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as f:
            f.write(data)
        return 'CREATED'
    except FileExistsError:
        check(path.read_bytes() == data, '기존 기록과 내용이 달라 덮어쓰기 차단: '+str(path))
        return 'UNCHANGED'


def atomic_bytes_new(path, data):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    try:
        with path.open('xb') as f: f.write(data)
        return 'CREATED'
    except FileExistsError:
        check(path.read_bytes() == data, '기존 압축 원본과 내용이 달라 덮어쓰기 차단: '+str(path))
        return 'UNCHANGED'


def archive(status_path, html_path, output_dir, *, now=None, retain_source=False):
    """Freeze future tracking records; not a reconstructed historical prediction."""
    status, status_raw = read_json_bytes(status_path)
    html_raw = pathlib.Path(html_path).read_bytes()
    payload = payload_from_html(html_raw)
    known = parse_ts(payload.get('selection_known_at'))
    now = now or dt.datetime.now(UTC)
    check(known <= now, '미래에 선정된 자료 사용 금지')
    check(status.get('status') == 'SUCCESS_RESEARCH_OBSERVATION' and status.get('success_this_run') is True,
          '최신 수집이 실제 성공한 경우만 보존')
    check(status.get('validation_status') == 'NOT_VALIDATED' and status.get('real_trades_allowed') is False,
          '실전 매매 안전 차단값 누락')
    check(payload.get('entryAllowed') is False and payload.get('validationStatus') == 'NOT_VALIDATED',
          '원본 자료의 매수 차단 증거 누락')
    check(payload.get('kind') == 'real-current-radar' and payload.get('counts_as_frozen_five_session') is False,
          '별도 연구판 / 기존 5거래일 격리 확인 실패')
    last = status.get('last_success') or {}
    session = last.get('session')
    check(isinstance(session,str) and re.fullmatch(r'\d{4}-\d\d-\d\d',session), '정상 거래일 누락')
    check(session == payload.get('session'), '사이트 상태·선정 원본의 거래일 불일치')
    check(known >= ny_session_close(session), '미완료 거래일에 미래 일봉 사용 의심')
    generated = parse_ts(last.get('collected_at_utc'))
    check(known <= generated <= now, '선정/게시 시각 역전')
    check((now-generated).total_seconds() <= 8*3600, '수집 8시간 이상 경과 — 자동 보존 차단')
    attempt_id = last.get('attempt_id')
    check(isinstance(attempt_id,str) and ATTEMPT.fullmatch(attempt_id), '시도 ID 형식 오류')
    formal = payload.get('candidates')
    check(isinstance(formal,list) and len(formal) == last.get('formal'), '정식 선정 수 불일치')
    check(len(formal) <= 25, '상세 분석 최대치 초과')
    check(payload.get('research_track') == 'partial-coverage-v1', '예상 연구 트랙 불일치')
    output = []
    tickers = set()
    for row in formal:
        check(isinstance(row,dict), '후보 레코드 구조 오류')
        sym = row.get('ticker')
        check(isinstance(sym,str) and bool(TICKER.fullmatch(sym)), '종목 코드 오류')
        check(sym not in tickers, '동일 종목 중복')
        tickers.add(sym)
        check(row.get('observation_group') == 'formal', '정식 관찰 레코드 아님')
        check(row.get('entryAllowed') is False and row.get('validationStatus') == 'NOT_VALIDATED',
              '후보 개별 매수 차단 증거 없음')
        row_at = parse_ts(row.get('selected_at'))
        check(ny_session_close(session) <= row_at <= known, '후보 선정 시각 오류')
        check(row.get('session') == session, '후보 거래일 불일치')
        daily = row.get('daily')
        check(isinstance(daily,list) and len(daily) > 0, '일봉 원본 없음')
        for bar in daily:
            t = parse_ts(bar.get('t'))
            check(t.astimezone(NY).date().isoformat() <= session, '선정 원본에 미래 일봉 포함')
        px = row.get('price')
        check(isinstance(px,(int,float)) and not isinstance(px,bool) and math.isfinite(px) and px>0,
              '선정 시점 기준종가 오류')
        output.append({'ticker':sym,'name':str(row.get('name',''))[:120],
                       'observed_session':session, 'selected_at_utc':row_at.isoformat(),
                       'reference_close':float(px),
                       'change_pct':row.get('daily_change_pct'),
                       'rvol_daily':row.get('rvol_daily'),
                       'risk':str(row.get('risk_summary','미확인'))[:240],
                       'entry_allowed':False, 'validation_status':'NOT_VALIDATED'})
    snap={'schema':'LUCA_TM_SNAPSHOT_V1','source_type':'COMPLETED_DAILY_BARS',
          'date':session,'selection_lock_utc':known.isoformat(),
          'publication_utc':generated.isoformat(),'attempt_id':attempt_id,
          'source_html_sha256':sha(html_raw),'source_status_sha256':sha(status_raw),
          'source_payload_sha256':sha(canonical(payload)),
          'scope_partial': bool(last.get('scope_partial')),
          'dated':last.get('dated'),'detail_count':last.get('details'),
          'formal_count':len(output),'candidates':sorted(output,key=lambda x:x['ticker']),
          'historical_asof_replay_validated':False,
          'reason':'선정 잠금시점 이전의 전종목·공시 시점별 복원 미검증. 사후 관찰 기록만 보존.',
          'real_trades_allowed':False,'validation_status':'NOT_VALIDATED'}
    if retain_source:
        # Deterministic compressed source for an independent later provenance audit.
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for name,data in [('latest.html',html_raw),('status.json',status_raw)]:
                info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED
                info.external_attr=0o600 << 16
                z.writestr(info,data,compress_type=zipfile.ZIP_DEFLATED,compresslevel=6)
        rawpath=pathlib.Path(output_dir)/'source'/(session+'.zip')
        source_state=atomic_bytes_new(rawpath,buffer.getvalue())
    dest=pathlib.Path(output_dir)/'snapshots'/(session+'.json')
    state=atomic_new(dest,snap)
    return dest, state, snap


def read_bars_csv(path):
    raw=pathlib.Path(path).read_bytes()
    rows={}
    with pathlib.Path(path).open('r',encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f):
            sym=r['ticker'].upper().strip()
            check(TICKER.fullmatch(sym), '후속 일봉 종목 코드 오류')
            date=dt.date.fromisoformat(r['date'])
            t=parse_ts(r['collected_at_utc'])
            check(t >= ny_session_close(date.isoformat()), '후속 일봉 확정 전 수집 표시 차단')
            check(r.get('source_url','').startswith('https://'), '후속 일봉 출처 URL 없음')
            vals={}
            for k in ('open','high','low','close'):
                vals[k]=float(r[k]);check(math.isfinite(vals[k]) and vals[k]>0, '후속 가격 비정상')
            check(vals['low']<=min(vals['open'],vals['close']) <= max(vals['open'],vals['close'])<=vals['high'],
                  '후속 OHLC 가격 관계 오류')
            key=(sym,date)
            check(key not in rows, '후속 일봉 중복')
            rows[key]={**vals,'date':date,'retrieved_at':t,'source_url':r['source_url']}
    return rows, sha(raw)


def first_touch(bars, entry, up=0.05, down=0.05):
    """No fabricated intraday event order; ambiguous if both touched in one daily bar."""
    top=entry*(1+up);bottom=entry*(1-down)
    for b in bars:
        ups=b['high']>=top;downs=b['low']<=bottom
        if ups and downs: return 'AMBIGUOUS_SAME_DAY'
        if ups:return 'UP_FIRST_DAILY_BAR'
        if downs:return 'DOWN_FIRST_DAILY_BAR'
    return 'NEITHER_IN_AVAILABLE_BARS'


def evaluate(snapshot_path, bars_csv, output_dir):
    snap, snapraw=read_json_bytes(snapshot_path)
    check(snap.get('schema')=='LUCA_TM_SNAPSHOT_V1', '스냅샷 버전 오류')
    check(snap.get('real_trades_allowed') is False, '매매 허용 스냅샷 거부')
    locked=parse_ts(snap.get('selection_lock_utc'))
    src_bars,bars_sha=read_bars_csv(bars_csv)
    outcomes=[]
    for candidate in snap['candidates']:
        sym=candidate['ticker']
        future=sorted((b for (t,d),b in src_bars.items() if t==sym and dt.datetime.combine(d,dt.time(9,30),NY).astimezone(UTC)>locked),key=lambda b:b['date'])
        # A full 09:30–16:00 ET session must start AFTER the selection lock.
        # If locked before today's US open, today's open may be the first reference.
        if future:
            entry=future[0]['open']
            periods={}
            for n in (1,3,5):
                block=future[:n]
                periods[str(n)]={'status':'REFERENCE_ONLY' if len(block)==n else 'INSUFFICIENT_DATA',
                                 'day_n_date':block[-1]['date'].isoformat() if block else None,
                                 'close_vs_next_open_pct':round((block[-1]['close']/entry-1)*100,3) if len(block)==n else None,
                                 'max_high_vs_next_open_pct':round((max(b['high'] for b in block)/entry-1)*100,3) if len(block)==n else None,
                                 'min_low_vs_next_open_pct':round((min(b['low'] for b in block)/entry-1)*100,3) if len(block)==n else None,
                                 'first_5pct_direction':first_touch(block,entry) if len(block)==n else 'INSUFFICIENT_DATA'}
            outcomes.append({'ticker':sym,'start_reference_day':future[0]['date'].isoformat(),
                             'next_session_open_reference':entry,'available_sessions':len(future),
                             'reference_only':True,'periods':periods})
        else:
            outcomes.append({'ticker':sym,'available_sessions':0,'status':'INSUFFICIENT_DATA',
                             'reference_only':True,'periods':{str(n):{'status':'INSUFFICIENT_DATA'} for n in (1,3,5)}})
    result={'schema':'LUCA_TM_EVALUATION_V1','snapshot_sha256':sha(snapraw),
            'bars_csv_sha256':bars_sha,'selection_lock_utc':locked.isoformat(),
            'session':snap['date'],'results':outcomes,
            'trading_performance_verified':False,'hit_rate':None,
            'real_trades_allowed':False,'validation_status':'NOT_VALIDATED',
            'limitations':'거래일 연속성·시장 휴장·분할 조정·정지·유동성·스프레드·수수료·호가·실제 체결 미검증. 첫 가능 거래일 시가 대비 가격 변동 참고만 가능. 장중 선후관계는 일봉만으로 판정 불가.'}
    name=pathlib.Path(snapshot_path).stem
    dest=pathlib.Path(output_dir)/'evaluations'/(name+'-'+bars_sha[:16]+'.json')
    state=atomic_new(dest,result)
    return dest,state,result


def main(argv=None):
    p=argparse.ArgumentParser(description='LUCA 별도 무료 타임머신 연구판 / 실제 매매 차단')
    sub=p.add_subparsers(dest='action',required=True)
    s=sub.add_parser('snapshot');s.add_argument('--status',required=True);s.add_argument('--html',required=True);s.add_argument('--out',required=True);s.add_argument('--retain-source',action='store_true')
    s=sub.add_parser('evaluate');s.add_argument('--snapshot',required=True);s.add_argument('--bars',required=True);s.add_argument('--out',required=True)
    a=p.parse_args(argv)
    try:
        if a.action=='snapshot':
            path,state,data=archive(a.status,a.html,a.out,retain_source=a.retain_source)
            print(json.dumps({'result':state,'file':str(path),'formal':data['formal_count'],'signal_type':'OBSERVATION_ONLY','performance':'NOT_VALIDATED'},ensure_ascii=False))
        else:
            path,state,data=evaluate(a.snapshot,a.bars,a.out)
            print(json.dumps({'result':state,'file':str(path),'outcomes':len(data['results']),'performance':'NOT_VALIDATED'},ensure_ascii=False))
    except (OSError,ValueError,KeyError,UnicodeError) as e:
        print('TM_BLOCKED: '+str(e)[:250],file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':sys.exit(main())
