# DART(전자공시시스템) Open API 연동.
# https://opendart.fss.or.kr - 종목코드(6자리)는 DART 고유번호(8자리, corp_code)와 달라서
# corpCode.xml을 내려받아 매핑 테이블을 만든 뒤, 이를 통해 공시 목록을 조회한다.
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta

import requests
from django.conf import settings
from django.core.cache import cache

DART_BASE_URL = 'https://opendart.fss.or.kr/api'
CORP_CODE_CACHE_PATH = settings.BASE_DIR / 'var' / 'dart_corp_codes.json'
CORP_CODE_CACHE_TTL = timedelta(days=7)
DISCLOSURE_CACHE_TTL = 600  # seconds
DISCLOSURE_LOOKBACK_DAYS = 365  # bgn_de를 안 주면 DART가 아주 좁은 범위만 반환한다
DOCUMENT_TEXT_MAX_CHARS = 40000  # 사업/분기보고서는 수백만 자에 달해 AI 분석용으로 앞부분만 사용
_TAG_RE = re.compile(r'<[^>]+>')
_ENTITY_RE = re.compile(r'&[a-zA-Z#0-9]+;')
_WHITESPACE_RE = re.compile(r'\s+')


class DartError(Exception):
    """DART API 키 누락, 매핑 실패, API 오류 등 사용자에게 보여줄 메시지를 담는다."""


def _get_api_key():
    key = settings.DART_API_KEY
    if not key:
        raise DartError('DART_API_KEY가 설정되지 않았습니다. .env 파일에 발급받은 키를 입력하세요.')
    return key


def _download_corp_codes():
    key = _get_api_key()
    resp = requests.get(f'{DART_BASE_URL}/corpCode.xml', params={'crtfc_key': key}, timeout=15)
    resp.raise_for_status()
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            xml_bytes = zf.read('CORPCODE.xml')
    except zipfile.BadZipFile:
        raise DartError('DART corpCode 응답이 올바르지 않습니다. API 키를 확인하세요.')

    root = ET.fromstring(xml_bytes)
    mapping = {}
    for item in root.iter('list'):
        stock_code = (item.findtext('stock_code') or '').strip()
        corp_code = (item.findtext('corp_code') or '').strip()
        if stock_code:
            mapping[stock_code] = corp_code

    CORP_CODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORP_CODE_CACHE_PATH.write_text(json.dumps(mapping), encoding='utf-8')
    return mapping


def _load_corp_codes():
    if CORP_CODE_CACHE_PATH.exists():
        age = datetime.now() - datetime.fromtimestamp(CORP_CODE_CACHE_PATH.stat().st_mtime)
        if age < CORP_CODE_CACHE_TTL:
            return json.loads(CORP_CODE_CACHE_PATH.read_text(encoding='utf-8'))
    return _download_corp_codes()


def get_corp_code(stock_code):
    corp_code = _load_corp_codes().get(stock_code)
    if not corp_code:
        raise DartError(f'DART에 등록되지 않은 종목입니다 ({stock_code}).')
    return corp_code


def get_disclosures(stock_code, count=15):
    """최근 공시 목록을 [{rcept_no, report_nm, flr_nm, rcept_dt, rm, url}, ...]로 반환한다."""
    cache_key = f'dart:disclosures:{stock_code}:{count}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    corp_code = get_corp_code(stock_code)
    today = datetime.now().date()
    resp = requests.get(f'{DART_BASE_URL}/list.json', params={
        'crtfc_key': _get_api_key(),
        'corp_code': corp_code,
        'bgn_de': (today - timedelta(days=DISCLOSURE_LOOKBACK_DAYS)).strftime('%Y%m%d'),
        'end_de': today.strftime('%Y%m%d'),
        'page_count': count,
    }, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    status = data.get('status')
    if status == '013':  # 조회된 데이터 없음
        disclosures = []
    elif status != '000':
        raise DartError(data.get('message', 'DART API 오류가 발생했습니다.'))
    else:
        disclosures = [
            {
                'rcept_no': item.get('rcept_no'),
                'report_nm': (item.get('report_nm') or '').strip(),
                'flr_nm': item.get('flr_nm'),
                'rcept_dt': item.get('rcept_dt'),
                'rm': item.get('rm'),
                'url': f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={item.get('rcept_no')}",
            }
            for item in data.get('list', [])
        ]

    cache.set(cache_key, disclosures, timeout=DISCLOSURE_CACHE_TTL)
    return disclosures


def get_document_text(rcept_no, max_chars=DOCUMENT_TEXT_MAX_CHARS):
    """공시 원문(XML)을 내려받아 태그를 제거한 평문으로 반환한다. AI 분석 입력으로 사용."""
    cache_key = f'dart:document_text:{rcept_no}:{max_chars}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    resp = requests.get(f'{DART_BASE_URL}/document.xml', params={
        'crtfc_key': _get_api_key(),
        'rcept_no': rcept_no,
    }, timeout=30)
    resp.raise_for_status()
    try:
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            raw = b''.join(zf.read(name) for name in zf.namelist())
    except zipfile.BadZipFile:
        raise DartError('공시 원문을 불러올 수 없습니다.')

    text = raw.decode('utf-8', errors='ignore')
    text = _TAG_RE.sub(' ', text)
    text = _ENTITY_RE.sub(' ', text)
    text = _WHITESPACE_RE.sub(' ', text).strip()
    text = text[:max_chars]

    cache.set(cache_key, text, timeout=DISCLOSURE_CACHE_TTL)
    return text