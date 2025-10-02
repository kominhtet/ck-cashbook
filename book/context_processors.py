from .models import Business, Membership


def current_business(request):
    biz_id = request.session.get('biz_id')
    biz = Business.objects.filter(id=biz_id).first() if biz_id else None
    memberships = []
    current_membership = None
    if request.user.is_authenticated:
        memberships = Membership.objects.filter(user=request.user).select_related('business')
        if biz_id:
            current_membership = Membership.objects.filter(user=request.user, business_id=biz_id).first()
    return {'current_business': biz, 'memberships': memberships, 'current_membership': current_membership}