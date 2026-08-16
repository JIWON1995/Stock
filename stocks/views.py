import json

import requests
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import OuterRef, Q, Subquery
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from . import dart, gemini_client
from .models import DailyPrice, DisclosureAnalysis, Stock
from .sectors import get_sector_name, get_sector_stock_codes


def stock_list(request):
    query = request.GET.get('q', '').strip()
    sector = request.GET.get('sector', '').strip()
    stocks = Stock.objects.filter(Q(delete_date__isnull=True) | Q(delete_date=''))
    if query:
        stocks = stocks.filter(Q(stock_code__icontains=query) | Q(stock_name__icontains=query))
    if sector:
        stocks = stocks.filter(stock_code__in=get_sector_stock_codes(sector))

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
        'sector': sector,
        'sector_name': get_sector_name(sector) if sector else None,
    })


def _attach_cached_analysis(disclosures):
    """이미 분석된 공시가 있으면 결과를 dict에 채운다. 새 분석은 사용자가 버튼을 눌렀을 때만 실행된다."""
    if not disclosures:
        return

    existing = {
        a.rcept_no: a
        for a in DisclosureAnalysis.objects.filter(rcept_no__in=[d['rcept_no'] for d in disclosures])
    }
    for d in disclosures:
        analysis = existing.get(d['rcept_no'])
        d['ai_summary'] = analysis.summary if analysis else None


@require_POST
def analyze_disclosure(request, stock_code, rcept_no):
    stock = get_object_or_404(Stock, stock_code=stock_code)
    report_nm = request.POST.get('report_nm', '')
    rcept_dt = request.POST.get('rcept_dt', '')

    analysis = DisclosureAnalysis.objects.filter(rcept_no=rcept_no).first()
    if analysis:
        return JsonResponse({'summary': analysis.summary})

    try:
        body_text = dart.get_document_text(rcept_no)
        summary = gemini_client.analyze_disclosure(
            corp_name=stock.stock_name, report_nm=report_nm, rcept_dt=rcept_dt, body_text=body_text,
        )
        DisclosureAnalysis.objects.update_or_create(
            rcept_no=rcept_no,
            defaults={
                'stock_id': stock.stock_code,
                'report_nm': report_nm,
                'rcept_dt': rcept_dt,
                'summary': summary,
            },
        )
        return JsonResponse({'summary': summary})
    except (dart.DartError, gemini_client.GeminiError, requests.RequestException) as e:
        return JsonResponse({'error': str(e)}, status=502)


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
        _attach_cached_analysis(disclosures)

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
