from django.urls import path
from . import views


urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('logout/', views.custom_logout, name='logout'),
    path('business/switch/<int:biz_id>/', views.switch_business, name='switch_business'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('transactions/', views.transactions_list, name='transactions_list'),
    path('transactions/cash-in/new/', views.cash_in_create, name='cash_in_create'),
    path('transactions/cash-out/new/', views.cash_out_create, name='cash_out_create'),
    path('transactions/category/create/', views.create_transaction_category, name='create_transaction_category'),
    path('export/excel/', views.export_excel, name='export_excel'),
    path('export/pdf/', views.export_pdf, name='export_pdf'),
    path('add-member/', views.add_member, name='add_member'),
    
    # Keep the home route at the end to avoid conflicts
    path('', views.home, name='home'),
]