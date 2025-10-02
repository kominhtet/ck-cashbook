from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from .models import Business, TransactionCategory, Transaction, BusinessCategory, BusinessType, Membership


class BusinessForm(forms.ModelForm):
    class Meta:
        model = Business
        fields = ['name', 'category', 'business_type']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'business_type': forms.Select(attrs={'class': 'form-select'}),
        }

class CategoryForm(forms.ModelForm):
    class Meta:
        model = TransactionCategory
        fields = ['business','name','kind']


class CashInForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['business','category','details','date','amount','photo']
        widgets = {
            'date': forms.DateInput(attrs={'type':'date'}),
            'details': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean(self):
        data = super().clean()
        data['kind'] = Transaction.Kind.CASH_IN
        return data


class CashOutForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['business','category','details','date','amount','photo']
        widgets = {
            'date': forms.DateInput(attrs={'type':'date'}),
            'details': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'photo': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }

    def clean(self):
        data = super().clean()
        data['kind'] = Transaction.Kind.CASH_OUT
        return data


class DateFilterForm(forms.Form):
    PERIOD_CHOICES = [
    ('custom','Custom'),('this_month','This Month'),('this_year','This Year'),('last_month','Last Month')
    ]
    period = forms.ChoiceField(choices=PERIOD_CHOICES, required=False, initial='this_month')
    date_from = forms.DateField(required=False, widget=forms.DateInput(attrs={'type':'date'}))
    date_to = forms.DateField(required=False, widget=forms.DateInput(attrs={'type':'date'}))
    kind = forms.ChoiceField(choices=[('ALL','All'),('CASH_IN','Cash In'),('CASH_OUT','Cash Out')], required=False, initial='ALL')


class AddMemberForm(forms.Form):
    email = forms.EmailField(
        label='User Email',
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter user email'})
    )
    role = forms.ChoiceField(
        label='Role',
        choices=[],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    
    def __init__(self, current_user_role, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set role choices based on current user's role
        if current_user_role == Membership.Role.OWNER:
            role_choices = [
                (Membership.Role.ADMIN, 'Admin'),
                (Membership.Role.STAFF, 'Staff')
            ]
        elif current_user_role == Membership.Role.ADMIN:
            role_choices = [
                (Membership.Role.STAFF, 'Staff')
            ]
        else:
            role_choices = []
            
        self.fields['role'].choices = role_choices
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if not email:
            raise forms.ValidationError('Email is required.')
        
        # Check if user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise forms.ValidationError('User with this email does not exist. Please ask them to register first.')
        
        return email


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email'})
    )
    first_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First name (optional)'})
    )
    last_name = forms.CharField(
        max_length=30,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last name (optional)'})
    )
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Choose a username'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add Bootstrap classes to password fields
        self.fields['password1'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Enter password'})
        self.fields['password2'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Confirm password'})
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('A user with this email already exists.')
        return email
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user