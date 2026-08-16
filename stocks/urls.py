from django.urls import path

from . import views

app_name = 'stocks'

urlpatterns = [
    path('', views.stock_list, name='stock_list'),
    path('stocks/<str:stock_code>/', views.stock_detail, name='stock_detail'),
    path(
        'stocks/<str:stock_code>/disclosures/<str:rcept_no>/analyze/',
        views.analyze_disclosure,
        name='analyze_disclosure',
    ),
]
