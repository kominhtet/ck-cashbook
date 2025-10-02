from django.http import HttpResponseForbidden
from .models import Membership, Business


def require_membership(view):
    def _wrapped(request, *args, **kwargs):
        biz_id = request.session.get('biz_id')
        if not request.user.is_authenticated:
            from django.contrib.auth.views import redirect_to_login
            return redirect_to_login(request.get_full_path())
        if not biz_id:
            return HttpResponseForbidden('Select a business first.')
        if not Membership.objects.filter(user=request.user, business_id=biz_id).exists():
            return HttpResponseForbidden('No membership for this business.')
        return view(request, *args, **kwargs)
    return _wrapped


def require_role(role):
    def decorator(view):
        def _wrapped(request, *args, **kwargs):
            biz_id = request.session.get('biz_id')
            m = Membership.objects.filter(user=request.user, business_id=biz_id).first()
            if not m or m.role != role:
                return HttpResponseForbidden('Insufficient role.')
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator