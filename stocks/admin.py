from django.contrib import admin

from .models import Stock

# DailyPrice(OPT10081)는 복합 기본키(STOCK_CODE, STOCK_DATE)를 사용하는데,
# Django admin은 복합 기본키 모델 등록을 지원하지 않아 여기서는 Stock만 등록한다.
# 일별 시세 조회는 종목 상세 페이지(stocks:stock_detail)에서 확인할 수 있다.


@admin.register(Stock)
class StockAdmin(admin.ModelAdmin):
    list_display = ('stock_code', 'stock_name', 'market_gb', 'is_delisted')
    search_fields = ('stock_code', 'stock_name')
    list_filter = ('market_gb',)

    def has_delete_permission(self, request, obj=None):
        return False
