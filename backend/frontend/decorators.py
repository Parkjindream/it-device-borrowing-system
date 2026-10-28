from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

from rental.models import User

DASHBOARD_URL_NAMES = {
    User.Role.STAFF: "frontend:staff-dashboard",
    User.Role.STUDENT: "frontend:student-dashboard",
}


def dashboard_url_name(user) -> str:
    return DASHBOARD_URL_NAMES.get(user.role, "frontend:student-dashboard")


def role_required(role):
    """
    เช็คก่อนส่งหน้า dashboard (แทน requireAuth ฝั่ง JS เดิม)
    - ยังไม่ล็อกอิน (ไม่มี session) -> ไปหน้า login พร้อม ?next= กลับมาหน้านี้
    - ล็อกอินแล้วแต่ role ไม่ตรง -> ไปหน้า dashboard ของ role ตัวเอง
    """

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if request.user.role != role:
                return redirect(dashboard_url_name(request.user))
            return view(request, *args, **kwargs)

        return wrapper

    return decorator
