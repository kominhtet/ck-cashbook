
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import HttpResponse, HttpResponseForbidden
from django.db.models import Sum, F
from io import BytesIO
import csv
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


from .models import Business, Membership, Transaction, TransactionCategory, BusinessCategory, BusinessType
from .forms import BusinessForm, CashInForm, CashOutForm, DateFilterForm, AddMemberForm, CustomUserCreationForm
from .permissions import require_membership, require_role
from .utils import resolve_period

def signup(request):
    """User registration with email field"""
    # Debug: Check if user is authenticated
    if request.user.is_authenticated:
        messages.info(request, f'You are already logged in as {request.user.username}. If you want to create a new account, please logout first.')
        return redirect('home')
        
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome {user.get_full_name() or user.username}! Your account has been created successfully.')
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

def custom_logout(request):
    """Custom logout view that clears session data and provides better UX"""
    if request.user.is_authenticated:
        # Clear session data including business selection
        if 'biz_id' in request.session:
            del request.session['biz_id']
        
        # Logout the user
        logout(request)
        messages.success(request, 'You have been successfully logged out.')
    
    return redirect('login')


@login_required
def home(request):
    """
    Unified view for business list and creation functionality
    Handles both GET (display list) and POST (create business) requests
    """
    # Get user's business memberships
    memberships = Membership.objects.filter(user=request.user).select_related('business')
    
    # Handle business creation
    if request.method == 'POST':
        form = BusinessForm(request.POST)
        if form.is_valid():
            biz = form.save()
            Membership.objects.create(user=request.user, business=biz, role=Membership.Role.OWNER)
            request.session['biz_id'] = biz.id
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'success': True,
                    'message': 'Business created successfully!',
                    'business_id': biz.id,
                    'business_name': biz.name
                })
            else:
                messages.success(request, 'Business created and you are OWNER.')
                return redirect('dashboard')
        else:
            # Handle form validation errors for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
            else:
                # For non-AJAX requests, show form with errors
                categories = BusinessCategory.objects.all()
                business_types = BusinessType.objects.all()
                return render(request, 'business/list.html', {
                    'memberships': memberships,
                    'form': form,
                    'show_modal': True,
                    'categories': categories,
                    'business_types': business_types
                })
    
    # GET request - show business list
    form = BusinessForm()
    categories = BusinessCategory.objects.all()
    business_types = BusinessType.objects.all()
    return render(request, 'business/list.html', {
        'memberships': memberships,
        'form': form,
        'categories': categories,
        'business_types': business_types
    })

@login_required
def switch_business(request, biz_id:int):
    if not Membership.objects.filter(user=request.user, business_id=biz_id).exists():
        return HttpResponseForbidden('You are not a member of this business')
    request.session['biz_id'] = biz_id
    
    # Check user role and redirect accordingly
    membership = Membership.objects.get(user=request.user, business_id=biz_id)
    if membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return redirect('dashboard')
    else:
        return redirect('transactions_list')

@require_membership
def dashboard(request):
    biz_id = request.session['biz_id']
    
    # Get the current business
    from .models import Business
    current_business = Business.objects.get(id=biz_id)
    
    # Check if user has permission to access dashboard (OWNER or ADMIN only)
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    if current_membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.info(request, 'You do not have permission to access the dashboard. Redirecting to transactions.')
        return redirect('transactions_list')
    
    form = DateFilterForm(request.GET or None)
    period = form.data.get('period','this_month')
    start, end = resolve_period(period)
    date_from = form.data.get('date_from') or (start.isoformat() if start else None)
    date_to = form.data.get('date_to') or (end.isoformat() if end else None)


    tx = Transaction.objects.filter(business_id=biz_id)
    if date_from: tx = tx.filter(date__gte=date_from)
    if date_to: tx = tx.filter(date__lte=date_to)


    # totals - convert amount from string to decimal for aggregation
    from decimal import Decimal
    total_in = 0
    total_out = 0
    
    for transaction in tx.filter(kind=Transaction.Kind.CASH_IN):
        try:
            total_in += Decimal(str(transaction.amount))
        except (ValueError, TypeError):
            pass
    
    for transaction in tx.filter(kind=Transaction.Kind.CASH_OUT):
        try:
            total_out += Decimal(str(transaction.amount))
        except (ValueError, TypeError):
            pass


    # group by month for chart - manual aggregation since amount is now CharField
    from django.db.models.functions import TruncMonth
    from collections import defaultdict
    
    # Get transactions grouped by month and kind
    monthly_data = defaultdict(lambda: {'CASH_IN': 0, 'CASH_OUT': 0})
    
    for transaction in tx:
        month_key = transaction.date.strftime('%Y-%m')
        try:
            amount = float(transaction.amount)
            monthly_data[month_key][transaction.kind] += amount
        except (ValueError, TypeError):
            pass
    
    # build chart data
    labels = sorted(monthly_data.keys())
    data_in = [monthly_data[label]['CASH_IN'] for label in labels]
    data_out = [monthly_data[label]['CASH_OUT'] for label in labels]

    # Get recent transactions for the dashboard
    recent_transactions = (Transaction.objects
                          .filter(business_id=biz_id)
                          .select_related('category', 'created_by')
                          .order_by('-date', '-id')[:10])  # Show last 10 transactions

    # Check permissions for adding members
    can_add_members = current_membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]

    # Get all team members for this business
    team_members = Membership.objects.filter(business_id=biz_id).select_related('user').order_by('-role', 'user__first_name', 'user__last_name')

    return render(request, 'dashboard.html', {
        'current_business': current_business,
        'filter_form': form,
        'total_in': total_in,
        'total_out': total_out,
        'labels': labels,
        'data_in': data_in,
        'data_out': data_out,
        'date_from': date_from,
        'date_to': date_to,
        'recent_transactions': recent_transactions,
        'current_membership': current_membership,
        'can_add_members': can_add_members,
        'team_members': team_members,
    })

@require_membership
def transactions_list(request):
    biz_id = request.session['biz_id']
    
    # Get the current business
    current_business = Business.objects.get(id=biz_id)
    
    form = DateFilterForm(request.GET or None)
    period = form.data.get('period','this_month')
    start, end = resolve_period(period)
    date_from = form.data.get('date_from') or (start.isoformat() if start else None)
    date_to = form.data.get('date_to') or (end.isoformat() if end else None)
    kind = form.data.get('kind','ALL')

    qs = Transaction.objects.filter(business_id=biz_id)
    if date_from: qs = qs.filter(date__gte=date_from)
    if date_to: qs = qs.filter(date__lte=date_to)
    if kind in ('CASH_IN','CASH_OUT'): qs = qs.filter(kind=kind)

    qs = qs.select_related('category','created_by').order_by('-date','-id')
    
    # Get categories for the modals
    categories = TransactionCategory.objects.filter(business_id=biz_id)
    
    # Get current user's membership for role checking
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    
    return render(request, 'transactions/list.html', {
        'current_business': current_business,
        'form': form, 
        'transactions': qs,
        'categories': categories,
        'current_membership': current_membership
    })

@require_membership
def cash_in_create(request):
    # Check if user has permission to create Cash In (OWNER or ADMIN only)
    biz_id = request.session['biz_id']
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    if current_membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.error(request, 'You cannot access to this')
        return redirect('transactions_list')
    # Only OWNER can create Cash In (assign number)
    if request.method == 'POST':
        form = CashInForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            # ensure business matches session
            obj.kind = Transaction.Kind.CASH_IN
            obj.created_by = request.user
            if obj.business_id != request.session['biz_id']:
                return HttpResponseForbidden('Wrong business selected.')
            obj.save()
            messages.success(request, 'Cash In recorded.')
            return redirect('transactions_list')
    else:
        form = CashInForm(initial={'business': request.session['biz_id']})
    return render(request, 'transactions/cash_in_form.html', {'form': form})

@require_membership
def cash_out_create(request):
    # Staff and Owner can record Cash Out; owner will see who inserted
    role = Membership.objects.filter(user=request.user, business_id=request.session['biz_id']).values_list('role', flat=True).first()
    if role not in [Membership.Role.STAFF, Membership.Role.OWNER]:
        return HttpResponseForbidden('Only staff/owner can record cash out.')
    if request.method == 'POST':
        form = CashOutForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.kind = Transaction.Kind.CASH_OUT
            obj.created_by = request.user
            if obj.business_id != request.session['biz_id']:
                return HttpResponseForbidden('Wrong business selected.')
            obj.save()
            messages.success(request, 'Cash Out recorded.')
            return redirect('transactions_list')
    else:
        form = CashOutForm(initial={'business': request.session['biz_id']})
    return render(request, 'transactions/cash_out_form.html', {'form': form})

@require_membership
def create_transaction_category(request):
    """Create a new transaction category via AJAX"""
    if request.method == 'POST':
        from .forms import CategoryForm
        from django.http import JsonResponse
        
        # Add business_id to the POST data
        post_data = request.POST.copy()
        post_data['business'] = request.session['biz_id']
        
        form = CategoryForm(post_data)
        if form.is_valid():
            category = form.save()
            
            # Return JSON response for AJAX
            return JsonResponse({
                'success': True,
                'category_id': category.id,
                'category_name': category.name,
                'message': 'Category created successfully!'
            })
        else:
            # Debug: Print form errors to console
            print(f"Form errors: {form.errors}")
            print(f"Form data: {post_data}")
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    
    from django.http import JsonResponse
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@require_membership
def export_excel(request):
    biz_id = request.session['biz_id']
    form = DateFilterForm(request.GET or None)
    start, end = resolve_period(form.data.get('period','this_month'))
    date_from = form.data.get('date_from') or (start.isoformat() if start else None)
    date_to = form.data.get('date_to') or (end.isoformat() if end else None)


    qs = Transaction.objects.filter(business_id=biz_id)
    if date_from: qs = qs.filter(date__gte=date_from)
    if date_to: qs = qs.filter(date__lte=date_to)


    df = pd.DataFrame(list(qs.values('date','kind','amount','details','category__name','created_by__username')))
    df.rename(columns={'category__name':'category','created_by__username':'created_by'}, inplace=True)


    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
        summary = df.groupby(['kind']).agg(total_amount=('amount','sum')).reset_index()
        summary.to_excel(writer, index=False, sheet_name='Summary')
    out.seek(0)


    resp = HttpResponse(out.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="transactions.xlsx"'
    return resp

@require_membership
def export_pdf(request):
    biz_id = request.session['biz_id']
    qs = Transaction.objects.filter(business_id=biz_id).select_related('category','created_by').order_by('date')[:200]    


    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4


    y = height - 40
    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y, "Transactions Report (first 200)")
    y -= 20
    p.setFont("Helvetica", 10)
    p.drawString(40, y, f"Business ID: {biz_id}")
    y -= 20


    headers = ["Date","Kind","Category","Amount","Details","User"]
    col_x = [40, 100, 180, 280, 380, 500]
    p.setFont("Helvetica-Bold", 9)
    for i,h in enumerate(headers):
        p.drawString(col_x[i], y, h)
    y -= 12
    p.setFont("Helvetica", 9)
    for t in qs:
        if y < 40:
            p.showPage(); y = height - 40; p.setFont("Helvetica", 9)
        row = [t.date.strftime('%Y-%m-%d'), t.kind, t.category.name, str(t.amount), t.details[:20] if t.details else '', t.created_by.username]
        for i,val in enumerate(row):
            p.drawString(col_x[i], y, str(val)[:22])
        y -= 12


    p.showPage(); p.save()
    pdf = buffer.getvalue(); buffer.close()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = 'attachment; filename="transactions.pdf"'
    return resp


@require_membership
def add_member(request):
    """Add a new member to the current business"""
    biz_id = request.session['biz_id']
    current_business = Business.objects.get(id=biz_id)
    
    # Get current user's membership to check their role
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    
    # Check if user has permission to add members (OWNER or ADMIN only)
    if current_membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return HttpResponseForbidden('You do not have permission to add members.')
    
    if request.method == 'POST':
        form = AddMemberForm(current_membership.role, request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']
            
            try:
                user = User.objects.get(email=email)
                
                # Check if user is already a member of this business
                if Membership.objects.filter(user=user, business_id=biz_id).exists():
                    messages.error(request, 'This user is already a member of this business.')
                else:
                    # Create new membership
                    Membership.objects.create(
                        user=user,
                        business=current_business,
                        role=role
                    )
                    messages.success(request, f'Successfully added {user.get_full_name() or user.username} as {role}.')
                    return redirect('dashboard')
                    
            except User.DoesNotExist:
                messages.error(request, 'User with this email does not exist.')
    else:
        form = AddMemberForm(current_membership.role)
    
    return render(request, 'add_member.html', {
        'form': form,
        'current_business': current_business,
    })



def signup(request):
    """User registration with email field"""
    # Debug: Check if user is authenticated
    if request.user.is_authenticated:
        messages.info(request, f'You are already logged in as {request.user.username}. If you want to create a new account, please logout first.')
        return redirect('home')
        
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome {user.get_full_name() or user.username}! Your account has been created successfully.')
            return redirect('home')
    else:
        form = CustomUserCreationForm()
    return render(request, 'registration/signup.html', {'form': form})

def custom_logout(request):
    """Custom logout view that clears session data and provides better UX"""
    if request.user.is_authenticated:
        # Clear session data including business selection
        if 'biz_id' in request.session:
            del request.session['biz_id']
        
        # Logout the user
        logout(request)
        messages.success(request, 'You have been successfully logged out.')
    
    return redirect('login')


@login_required
def home(request):
    """
    Unified view for business list and creation functionality
    Handles both GET (display list) and POST (create business) requests
    """
    # Get user's business memberships
    memberships = Membership.objects.filter(user=request.user).select_related('business')
    
    # Handle business creation
    if request.method == 'POST':
        form = BusinessForm(request.POST)
        if form.is_valid():
            biz = form.save()
            Membership.objects.create(user=request.user, business=biz, role=Membership.Role.OWNER)
            request.session['biz_id'] = biz.id
            
            # Check if it's an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'success': True,
                    'message': 'Business created successfully!',
                    'business_id': biz.id,
                    'business_name': biz.name
                })
            else:
                messages.success(request, 'Business created and you are OWNER.')
                return redirect('dashboard')
        else:
            # Handle form validation errors for AJAX
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                from django.http import JsonResponse
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                }, status=400)
            else:
                # For non-AJAX requests, show form with errors
                categories = BusinessCategory.objects.all()
                business_types = BusinessType.objects.all()
                return render(request, 'business/list.html', {
                    'memberships': memberships,
                    'form': form,
                    'show_modal': True,
                    'categories': categories,
                    'business_types': business_types
                })
    
    # GET request - show business list
    form = BusinessForm()
    categories = BusinessCategory.objects.all()
    business_types = BusinessType.objects.all()
    return render(request, 'business/list.html', {
        'memberships': memberships,
        'form': form,
        'categories': categories,
        'business_types': business_types
    })

@login_required
def switch_business(request, biz_id:int):
    if not Membership.objects.filter(user=request.user, business_id=biz_id).exists():
        return HttpResponseForbidden('You are not a member of this business')
    request.session['biz_id'] = biz_id
    
    # Check user role and redirect accordingly
    membership = Membership.objects.get(user=request.user, business_id=biz_id)
    if membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        return redirect('dashboard')
    else:
        return redirect('transactions_list')

@require_membership
def dashboard(request):
    biz_id = request.session['biz_id']
    
    # Get the current business
    from .models import Business
    current_business = Business.objects.get(id=biz_id)
    
    # Check if user has permission to access dashboard (OWNER or ADMIN only)
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    if current_membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.info(request, 'You do not have permission to access the dashboard. Redirecting to transactions.')
        return redirect('transactions_list')
    
    form = DateFilterForm(request.GET or None)
    period = form.data.get('period','this_month')
    start, end = resolve_period(period)
    date_from = form.data.get('date_from') or (start.isoformat() if start else None)
    date_to = form.data.get('date_to') or (end.isoformat() if end else None)


    tx = Transaction.objects.filter(business_id=biz_id)
    if date_from: tx = tx.filter(date__gte=date_from)
    if date_to: tx = tx.filter(date__lte=date_to)


    # totals - convert amount from string to decimal for aggregation
    from decimal import Decimal
    total_in = 0
    total_out = 0
    
    for transaction in tx.filter(kind=Transaction.Kind.CASH_IN):
        try:
            total_in += Decimal(str(transaction.amount))
        except (ValueError, TypeError):
            pass
    
    for transaction in tx.filter(kind=Transaction.Kind.CASH_OUT):
        try:
            total_out += Decimal(str(transaction.amount))
        except (ValueError, TypeError):
            pass


    # group by month for chart - manual aggregation since amount is now CharField
    from django.db.models.functions import TruncMonth
    from collections import defaultdict
    
    # Get transactions grouped by month and kind
    monthly_data = defaultdict(lambda: {'CASH_IN': 0, 'CASH_OUT': 0})
    
    for transaction in tx:
        month_key = transaction.date.strftime('%Y-%m')
        try:
            amount = float(transaction.amount)
            monthly_data[month_key][transaction.kind] += amount
        except (ValueError, TypeError):
            pass
    
    # build chart data
    labels = sorted(monthly_data.keys())
    data_in = [monthly_data[label]['CASH_IN'] for label in labels]
    data_out = [monthly_data[label]['CASH_OUT'] for label in labels]

    # Get recent transactions for the dashboard
    recent_transactions = (Transaction.objects
                          .filter(business_id=biz_id)
                          .select_related('category', 'created_by')
                          .order_by('-date', '-id')[:10])  # Show last 10 transactions

    # Check permissions for adding members
    can_add_members = current_membership.role in [Membership.Role.OWNER, Membership.Role.ADMIN]

    # Get all team members for this business
    team_members = Membership.objects.filter(business_id=biz_id).select_related('user').order_by('-role', 'user__first_name', 'user__last_name')

    # Calculate balance
    balance = total_in - total_out

    return render(request, 'dashboard.html', {
        'current_business': current_business,
        'filter_form': form,
        'total_in': total_in,
        'total_out': total_out,
        'balance': balance,
        'labels': labels,
        'data_in': data_in,
        'data_out': data_out,
        'date_from': date_from,
        'date_to': date_to,
        'recent_transactions': recent_transactions,
        'current_membership': current_membership,
        'can_add_members': can_add_members,
        'team_members': team_members,
    })

@require_membership
def transactions_list(request):
    biz_id = request.session['biz_id']
    
    # Get the current business
    current_business = Business.objects.get(id=biz_id)
    
    form = DateFilterForm(request.GET or None)
    period = form.data.get('period','this_month')
    start, end = resolve_period(period)
    date_from = form.data.get('date_from') or (start.isoformat() if start else None)
    date_to = form.data.get('date_to') or (end.isoformat() if end else None)
    kind = form.data.get('kind','ALL')

    qs = Transaction.objects.filter(business_id=biz_id)
    if date_from: qs = qs.filter(date__gte=date_from)
    if date_to: qs = qs.filter(date__lte=date_to)
    if kind in ('CASH_IN','CASH_OUT'): qs = qs.filter(kind=kind)

    qs = qs.select_related('category','created_by').order_by('-date','-id')
    
    # Get categories for the modals
    categories = TransactionCategory.objects.filter(business_id=biz_id)
    
    # Get current user's membership for role checking
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    
    return render(request, 'transactions/list.html', {
        'current_business': current_business,
        'form': form, 
        'transactions': qs,
        'categories': categories,
        'current_membership': current_membership
    })

@require_membership
def cash_in_create(request):
    # Check if user has permission to create Cash In (OWNER or ADMIN only)
    biz_id = request.session['biz_id']
    current_membership = Membership.objects.get(user=request.user, business_id=biz_id)
    if current_membership.role not in [Membership.Role.OWNER, Membership.Role.ADMIN]:
        messages.error(request, 'You cannot access to this')
        return redirect('transactions_list')
    # Only OWNER can create Cash In (assign number)
    if request.method == 'POST':
        form = CashInForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            # ensure business matches session
            obj.kind = Transaction.Kind.CASH_IN
            obj.created_by = request.user
            if obj.business_id != request.session['biz_id']:
                return HttpResponseForbidden('Wrong business selected.')
            obj.save()
            messages.success(request, 'Cash In recorded.')
            return redirect('transactions_list')
    else:
        form = CashInForm(initial={'business': request.session['biz_id']})
    return render(request, 'transactions/cash_in_form.html', {'form': form})

@require_membership
def cash_out_create(request):
    # Staff and Owner can record Cash Out; owner will see who inserted
    role = Membership.objects.filter(user=request.user, business_id=request.session['biz_id']).values_list('role', flat=True).first()
    if role not in [Membership.Role.STAFF, Membership.Role.OWNER]:
        return HttpResponseForbidden('Only staff/owner can record cash out.')
    if request.method == 'POST':
        form = CashOutForm(request.POST, request.FILES)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.kind = Transaction.Kind.CASH_OUT
            obj.created_by = request.user
            if obj.business_id != request.session['biz_id']:
                return HttpResponseForbidden('Wrong business selected.')
            obj.save()
            messages.success(request, 'Cash Out recorded.')
            return redirect('transactions_list')
    else:
        form = CashOutForm(initial={'business': request.session['biz_id']})
    return render(request, 'transactions/cash_out_form.html', {'form': form})

@require_membership
def create_transaction_category(request):
    """Create a new transaction category via AJAX"""
    if request.method == 'POST':
        from .forms import CategoryForm
        from django.http import JsonResponse
        
        # Add business_id to the POST data
        post_data = request.POST.copy()
        post_data['business'] = request.session['biz_id']
        
        form = CategoryForm(post_data)
        if form.is_valid():
            category = form.save()
            
            # Return JSON response for AJAX
            return JsonResponse({
                'success': True,
                'category_id': category.id,
                'category_name': category.name,
                'message': 'Category created successfully!'
            })
        else:
            # Debug: Print form errors to console
            print(f"Form errors: {form.errors}")
            print(f"Form data: {post_data}")
            return JsonResponse({
                'success': False,
                'errors': form.errors
            }, status=400)
    
    from django.http import JsonResponse
    return JsonResponse({'success': False, 'message': 'Invalid request method'}, status=405)

@require_membership
def export_excel(request):
    biz_id = request.session['biz_id']
    form = DateFilterForm(request.GET or None)
    start, end = resolve_period(form.data.get('period','this_month'))
    date_from = form.data.get('date_from') or (start.isoformat() if start else None)
    date_to = form.data.get('date_to') or (end.isoformat() if end else None)


    qs = Transaction.objects.filter(business_id=biz_id)
    if date_from: qs = qs.filter(date__gte=date_from)
    if date_to: qs = qs.filter(date__lte=date_to)


    df = pd.DataFrame(list(qs.values('date','kind','amount','details','category__name','created_by__username')))
    df.rename(columns={'category__name':'category','created_by__username':'created_by'}, inplace=True)


    out = BytesIO()
    with pd.ExcelWriter(out, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
        summary = df.groupby(['kind']).agg(total_amount=('amount','sum')).reset_index()
        summary.to_excel(writer, index=False, sheet_name='Summary')
    out.seek(0)


    resp = HttpResponse(out.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    resp['Content-Disposition'] = 'attachment; filename="transactions.xlsx"'
    return resp

@require_membership
def export_pdf(request):
    biz_id = request.session['biz_id']
    qs = Transaction.objects.filter(business_id=biz_id).select_related('category','created_by').order_by('date')[:200]    


    buffer = BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4


    y = height - 40
    p.setFont("Helvetica-Bold", 14)
    p.drawString(40, y, "Transactions Report (first 200)")
    y -= 20
    p.setFont("Helvetica", 10)
    p.drawString(40, y, f"Business ID: {biz_id}")
    y -= 20


    headers = ["Date","Kind","Category","Amount","Details","User"]
    col_x = [40, 100, 180, 280, 380, 500]
    p.setFont("Helvetica-Bold", 9)
    for i,h in enumerate(headers):
        p.drawString(col_x[i], y, h)
    y -= 12
    p.setFont("Helvetica", 9)
    for t in qs:
        if y < 40:
            p.showPage(); y = height - 40; p.setFont("Helvetica", 9)
        row = [t.date.strftime('%Y-%m-%d'), t.kind, t.category.name, str(t.amount), t.details[:20] if t.details else '', t.created_by.username]
        for i,val in enumerate(row):
            p.drawString(col_x[i], y, str(val)[:22])
        y -= 12


    p.showPage(); p.save()
    pdf = buffer.getvalue(); buffer.close()
    resp = HttpResponse(pdf, content_type='application/pdf')
    resp['Content-Disposition'] = 'attachment; filename="transactions.pdf"'
    return resp


