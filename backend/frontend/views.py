from django.contrib.auth import logout
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from rental.models import Equipment, User
from rental.views import equipment_with_counts

from .decorators import dashboard_url_name, role_required


@require_GET
def home(request):
    """หน้าแรก: รายการอุปกรณ์ + จำนวนว่างจากฐานข้อมูลตรง ๆ (ชุดเดียวกับ /api/public/equipment/)"""
    equipment = equipment_with_counts(
        Equipment.objects.filter(is_active=True).select_related("category")
    ).order_by("category__name", "name")
    dashboard_url = reverse(dashboard_url_name(request.user)) if request.user.is_authenticated else None
    return render(request, "frontend/index.html", {"equipment_list": equipment, "dashboard_url": dashboard_url})


@require_GET
def login_page(request):
    # ล็อกอินอยู่แล้ว (มี session) ไม่ต้องเห็นหน้า login อีก
    if request.user.is_authenticated:
        return redirect(dashboard_url_name(request.user))
    return render(request, "frontend/login.html")


@require_GET
def logout_page(request):
    """
    ล้าง session แล้วไปหน้า login — JS เรียกเมื่อ token ใช้ไม่ได้ (401) กันวนลูป login <-> dashboard
    ออกจากระบบปกติใช้ POST /api/auth/logout/ ซึ่งลบทั้ง token และ session
    """
    logout(request)
    return redirect("frontend:login")


@require_GET
@role_required(User.Role.STAFF)
def staff_dashboard(request):
    return render(request, "frontend/staff/dashboard.html")


@require_GET
@role_required(User.Role.STUDENT)
def student_dashboard(request):
    return render(request, "frontend/student/dashboard.html")
