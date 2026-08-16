# TNODE(업종 분류 트리) 조회 헬퍼. 최상위 업종은 4자리 NODE_CODE로 구분된다.
from django.core.cache import cache
from django.db.models.functions import Length

from .models import SectorNode

TOP_LEVEL_CACHE_KEY = 'sectors:top_level'
TOP_LEVEL_CACHE_TTL = 60 * 60 * 24  # 업종 목록은 거의 바뀌지 않는다


def get_top_level_sectors():
    sectors = cache.get(TOP_LEVEL_CACHE_KEY)
    if sectors is None:
        sectors = list(
            SectorNode.objects.annotate(code_len=Length('node_code'))
            .filter(code_len=4)
            .order_by('node_code')
            .values('node_code', 'node_name')
        )
        cache.set(TOP_LEVEL_CACHE_KEY, sectors, TOP_LEVEL_CACHE_TTL)
    return sectors


def get_sector_name(sector_code):
    return next((s['node_name'] for s in get_top_level_sectors() if s['node_code'] == sector_code), None)


def get_sector_stock_codes(sector_code):
    return list(
        SectorNode.objects.filter(node_code__startswith=sector_code)
        .exclude(stock_code__in=('', None))
        .values_list('stock_code', flat=True)
        .distinct()
    )
