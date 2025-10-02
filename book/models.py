from django.db import models
from django.contrib.auth.models import User


class BusinessCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    photo = models.ImageField(upload_to='business_categories/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Business Category"
        verbose_name_plural = "Business Categories"

    def __str__(self):
        return self.name


class BusinessType(models.Model):
    name = models.CharField(max_length=100, unique=True)
    photo = models.ImageField(upload_to='business_types/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Business Type"
        verbose_name_plural = "Business Types"

    def __str__(self):
        return self.name


class Business(models.Model):
    name = models.CharField(max_length=120, unique=True)
    category = models.ForeignKey(BusinessCategory, on_delete=models.SET_NULL, null=True, blank=True)
    business_type = models.ForeignKey(BusinessType, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Business"
        verbose_name_plural = "Businesses"

    def __str__(self):
        return self.name


class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = 'OWNER', 'Owner'
        ADMIN = 'ADMIN', 'Admin'
        STAFF = 'STAFF', 'Staff'
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    role = models.CharField(max_length=8, choices=Role.choices)


    class Meta:
        unique_together = ('user', 'business')


    def __str__(self):
        return f"{self.user} in {self.business} ({self.role})"


class TransactionCategory(models.Model):
    class Kind(models.TextChoices):
        INCOME = 'INCOME', 'Income'
        EXPENSE = 'EXPENSE', 'Expense'
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=Kind.choices)

    class Meta:
        unique_together = ('business','name','kind')

    def __str__(self):
        return f"{self.name} ({self.kind})"

class Transaction(models.Model):
    class Kind(models.TextChoices):
        CASH_IN = 'CASH_IN', 'Cash In'
        CASH_OUT = 'CASH_OUT', 'Cash Out'

    business = models.ForeignKey(Business, on_delete=models.CASCADE) 
    details = models.CharField(max_length=240, blank=True)
    category = models.ForeignKey(TransactionCategory, on_delete=models.PROTECT)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    amount = models.CharField(max_length=40) 
    photo = models.ImageField(upload_to='transactions/', blank=True, null=True)
    date = models.DateField()
    created_by = models.ForeignKey(User, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)


    class Meta:
        indexes = [
        models.Index(fields=['business','date']),
        models.Index(fields=['business','kind']),
        ]


    def __str__(self):
        return f"{self.number} {self.kind} {self.amount}"