# Google Gemini API 연동 - DART 공시 원문을 요약/분석하는 데 사용.
# https://ai.google.dev/gemini-api/docs
import requests
from django.conf import settings

GEMINI_MODEL = 'gemini-flash-latest'
GEMINI_URL = f'https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent'

PROMPT_TEMPLATE = """당신은 한국 주식 시장 애널리스트입니다. 아래는 기업 '{corp_name}'이(가) {rcept_dt}에 제출한 \
전자공시 '{report_nm}'의 원문 일부입니다. 다음 형식의 한국어로 간결하게 정리해 주세요.

핵심 요약: (2~3문장)
투자자 관점 시사점: (2~3문장)
주의할 리스크: (있다면 1~2문장, 없으면 "특이사항 없음")

--- 공시 원문 ---
{body_text}
--- 원문 끝 ---
"""


class GeminiError(Exception):
    """API 키 누락, 응답 파싱 실패 등 사용자에게 보여줄 메시지를 담는다."""


def _get_api_key():
    key = settings.GEMINI_API_KEY
    if not key:
        raise GeminiError('GEMINI_API_KEY가 설정되지 않았습니다. .env 파일에 발급받은 키를 입력하세요.')
    return key


def analyze_disclosure(corp_name, report_nm, rcept_dt, body_text):
    prompt = PROMPT_TEMPLATE.format(
        corp_name=corp_name, report_nm=report_nm, rcept_dt=rcept_dt, body_text=body_text,
    )
    resp = requests.post(
        GEMINI_URL,
        params={'key': _get_api_key()},
        json={'contents': [{'parts': [{'text': prompt}]}]},
        timeout=90,
    )
    resp.raise_for_status()
    data = resp.json()
    try:
        parts = data['candidates'][0]['content']['parts']
        text = ''.join(p['text'] for p in parts if p.get('text') and not p.get('thought')).strip()
    except (KeyError, IndexError, TypeError):
        raise GeminiError('Gemini 응답을 해석할 수 없습니다.')
    if not text:
        raise GeminiError('Gemini가 빈 응답을 반환했습니다.')
    return text
