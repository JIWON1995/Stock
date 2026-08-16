import json

import requests
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, render

from . import dart, gemini_client
from .models import DailyPrice, DisclosureAnalysis, Stock


def stock_list(request):
    query = request.GET.get('q', '').strip()
    stocks = Stock.objects.filter(Q(delete_date__isnull=True) | Q(delete_date=''))
    if query:
        stocks = stocks.filter(Q(stock_code__icontains=query) | Q(stock_name__icontains=query))

    recent_prices = DailyPrice.objects.filter(stock=OuterRef('pk')).order_by('-stock_date')
    stocks = stocks.annotate(
        latest_price=Subquery(recent_prices.values('now_price')[:1]),
        latest_volume=Subquery(recent_prices.values('trade_qty')[:1]),
        prev_price=Subquery(recent_prices.values('now_price')[1:2]),
    )

    paginator = Paginator(stocks, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    for stock in page_obj:
        if stock.latest_price is not None and stock.prev_price:
            stock.change = stock.latest_price - stock.prev_price
            stock.change_rate = round(stock.change / stock.prev_price * 100, 2)
        else:
            stock.change = None
            stock.change_rate = None

    return render(request, 'stocks/stock_list.html', {
        'page_obj': page_obj,
        'query': query,
    })


MAX_AUTO_ANALYZE_PER_VISIT = 3  # 페이지 방문마다 새로 분석할 공시 수 상한 (응답 지연/API 비용 제한)


def _annotate_with_ai_analysis(stock, disclosures):
    """미분석 공시 중 최신 몇 건을 Gemini로 분석해 DB에 캐싱하고, 각 disclosure dict에 결과를 채운다."""
    if not disclosures:
        return

    existing = {
        a.rcept_no: a
        for a in DisclosureAnalysis.objects.filter(rcept_no__in=[d['rcept_no'] for d in disclosures])
    }
    remaining_slots = MAX_AUTO_ANALYZE_PER_VISIT

    for d in disclosures:
        analysis = existing.get(d['rcept_no'])
        if analysis:
            d['ai_summary'] = analysis.summary
            d['ai_error'] = None
            continue
        if remaining_slots <= 0:
            d['ai_summary'] = None
            d['ai_error'] = None
            continue

        remaining_slots -= 1
        try:
            body_text = dart.get_document_text(d['rcept_no'])
            summary = gemini_client.analyze_disclosure(
                corp_name=stock.stock_name, report_nm=d['report_nm'], rcept_dt=d['rcept_dt'], body_text=body_text,
            )
            DisclosureAnalysis.objects.update_or_create(
                rcept_no=d['rcept_no'],
                defaults={
                    'stock_id': stock.stock_code,
                    'report_nm': d['report_nm'],
                    'rcept_dt': d['rcept_dt'],
                    'summary': summary,
                },
            )
            d['ai_summary'] = summary
            d['ai_error'] = None
        except (dart.DartError, gemini_client.GeminiError, requests.RequestException) as e:
            d['ai_summary'] = None
            d['ai_error'] = str(e)


PERIOD_DAYS = {
    '1m': 30,
    '3m': 90,
    '6m': 180,
    '1y': 365,
    'all': None,
}
MA_WINDOWS = (5, 20, 60)


def stock_detail(request, stock_code):
    stock = get_object_or_404(Stock, stock_code=stock_code)
    period = request.GET.get('period', '3m')
    if period not in PERIOD_DAYS:
        period = '3m'
    days = PERIOD_DAYS[period]

    qs = stock.daily_prices.all()  # 최신순(모델 기본 정렬)
    prices = list(qs[:days]) if days else list(qs)

    latest = prices[0] if prices else None
    previous = prices[1] if len(prices) > 1 else None

    change = change_rate = None
    if latest and previous and previous.now_price:
        change = latest.now_price - previous.now_price
        change_rate = round(change / previous.now_price * 100, 2)

    ordered = list(reversed(prices))  # 차트는 날짜 오름차순으로
    closes = [float(p.now_price) if p.now_price is not None else None for p in ordered]

    moving_averages = {}
    for window in MA_WINDOWS:
        values = []
        for i in range(len(closes)):
            window_slice = closes[max(0, i - window + 1):i + 1]
            if i + 1 < window or None in window_slice:
                values.append(None)
            else:
                values.append(round(sum(window_slice) / window, 2))
        moving_averages[f'ma{window}'] = values

    def as_float(value):
        return float(value) if value is not None else None

    chart_data = [
        {
            'date': f'{p.stock_date[0:4]}-{p.stock_date[4:6]}-{p.stock_date[6:8]}',
            'o': as_float(p.start_price),
            'h': as_float(p.high_price),
            'l': as_float(p.low_price),
            'c': as_float(p.now_price),
            'v': p.trade_qty,
        }
        for p in ordered
    ]

    try:
        disclosures = dart.get_disclosures(stock_code)
        dart_error = None
    except dart.DartError as e:
        disclosures = []
        dart_error = str(e)
    except requests.RequestException:
        disclosures = []
        dart_error = 'DART 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.'

    if not dart_error:
        _annotate_with_ai_analysis(stock, disclosures)

    return render(request, 'stocks/stock_detail.html', {
        'stock': stock,
        'prices': prices,
        'latest': latest,
        'change': change,
        'change_rate': change_rate,
        'period': period,
        'chart_data': json.dumps(chart_data, cls=DjangoJSONEncoder),
        'ma_data': json.dumps(moving_averages, cls=DjangoJSONEncoder),
        'disclosures': disclosures,
        'dart_error': dart_error,
    })
