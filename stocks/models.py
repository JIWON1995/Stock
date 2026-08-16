# 기존 키움증권 OpenAPI 연동 테이블(SCODE, OPT10081)을 읽기 전용으로 매핑한 모델.
# managed=False 이므로 makemigrations/migrate 대상에서 제외되고, 기존 데이터는 그대로 유지된다.
from django.db import models


class Stock(models.Model):
    stock_code = models.CharField(db_column='STOCK_CODE', primary_key=True, max_length=6)
    stock_name = models.CharField(db_column='STOCK_NAME', max_length=100, blank=True, null=True)
    ybjong_code = models.CharField(db_column='YBJONG_CODE', max_length=6)
    first_date = models.CharField(db_column='FIRST_DATE', max_length=8, blank=True, null=True)
    delete_date = models.CharField(db_column='DELETE_DATE', max_length=8, blank=True, null=True)
    market_gb = models.CharField(db_column='Market_Gb', max_length=1, blank=True, null=True)
    buy_price = models.IntegerField(db_column='BUY_PRICE', blank=True, null=True)
    target_price1 = models.IntegerField(db_column='Target_Price1', blank=True, null=True)
    target_price2 = models.IntegerField(db_column='Target_Price2', blank=True, null=True)
    target_price3 = models.IntegerField(db_column='Target_Price3', blank=True, null=True)
    cut_price1 = models.IntegerField(db_column='Cut_Price1', blank=True, null=True)
    cut_price2 = models.IntegerField(db_column='Cut_Price2', blank=True, null=True)
    cut_price3 = models.IntegerField(db_column='Cut_Price3', blank=True, null=True)
    dividend_rate = models.CharField(db_column='Dividend_Rate', max_length=5, blank=True, null=True)
    stock_contents = models.TextField(db_column='Stock_Contents', blank=True, null=True)
    simple_contents = models.CharField(db_column='SIMPLE_CONTENTS', max_length=1000, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'SCODE'
        ordering = ['stock_code']

    def __str__(self):
        return f'{self.stock_name}({self.stock_code})'

    @property
    def is_delisted(self):
        return bool(self.delete_date)


class DailyPrice(models.Model):
    pk = models.CompositePrimaryKey('stock', 'stock_date')
    stock = models.ForeignKey(
        Stock, db_column='STOCK_CODE', to_field='stock_code',
        on_delete=models.DO_NOTHING, db_constraint=False, related_name='daily_prices',
    )
    stock_date = models.CharField(db_column='STOCK_DATE', max_length=8)
    now_price = models.DecimalField(db_column='NOW_PRICE', max_digits=18, decimal_places=0, blank=True, null=True)
    trade_qty = models.IntegerField(db_column='TRADE_QTY', blank=True, null=True)
    trade_daegum = models.DecimalField(db_column='TRADE_DAEGUM', max_digits=14, decimal_places=0, blank=True, null=True)
    start_price = models.DecimalField(db_column='START_PRICE', max_digits=18, decimal_places=0, blank=True, null=True)
    high_price = models.DecimalField(db_column='HIGH_PRICE', max_digits=18, decimal_places=0, blank=True, null=True)
    low_price = models.DecimalField(db_column='LOW_PRICE', max_digits=18, decimal_places=0, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'OPT10081'
        ordering = ['-stock_date']

    def __str__(self):
        return f'{self.stock_id} {self.stock_date}'


class SectorNode(models.Model):
    """업종 분류 트리. NODE_CODE는 2자리씩 계층을 나타내며, STOCK_CODE가 채워진 행이 해당 업종에 속한 종목이다."""
    node_code = models.CharField(db_column='NODE_CODE', primary_key=True, max_length=20)
    node_name = models.CharField(db_column='NODE_NAME', max_length=50, blank=True, null=True)
    stock_code = models.CharField(db_column='STOCK_CODE', max_length=6, blank=True, null=True)
    node_desc = models.CharField(db_column='NODE_DESC', max_length=100, blank=True, null=True)

    class Meta:
        managed = False
        db_table = 'TNODE'

    def __str__(self):
        return f'{self.node_code} {self.node_name}'


class DisclosureAnalysis(models.Model):
    """DART 공시(rcept_no)별 Gemini 분석 결과 캐시. 새로 만든 테이블(관리 대상)."""
    rcept_no = models.CharField(primary_key=True, max_length=20)
    stock = models.ForeignKey(
        Stock, to_field='stock_code',
        on_delete=models.CASCADE, db_constraint=False, related_name='disclosure_analyses',
    )
    report_nm = models.CharField(max_length=255)
    rcept_dt = models.CharField(max_length=8)
    summary = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-rcept_dt']

    def __str__(self):
        return f'{self.stock_id} {self.report_nm}'
