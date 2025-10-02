from django.contrib import admin
from .models import Business, Membership, TransactionCategory,  Transaction
from .models import BusinessCategory, BusinessType

admin.site.register(Business)
admin.site.register(Membership)
admin.site.register(TransactionCategory)
admin.site.register(Transaction)
admin.site.register(BusinessCategory)
admin.site.register(BusinessType)