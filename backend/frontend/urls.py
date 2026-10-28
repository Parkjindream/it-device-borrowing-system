from django.urls import path
from django.views.generic import RedirectView, TemplateView

from . import views

app_name = "frontend"


def old_html(url_name):
    """ลิงก์ .html แบบเดิม (เช่นในอีเมลที่ส่งไปแล้ว) -> URL ใหม่ โดยคง ?uid=&token= ไว้"""
    return RedirectView.as_view(pattern_name=f"frontend:{url_name}", permanent=True, query_string=True)


urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_page, name="login"),
    path("logout/", views.logout_page, name="logout"),
    path("forgot-password/", TemplateView.as_view(template_name="frontend/forgot_password.html"),
         name="forgot-password"),
    path("reset-password/", TemplateView.as_view(template_name="frontend/reset_password.html"),
         name="reset-password"),
    path("set-password/", TemplateView.as_view(template_name="frontend/set_password.html"), name="set-password"),
    path("staff/", views.staff_dashboard, name="staff-dashboard"),
    path("student/", views.student_dashboard, name="student-dashboard"),

    path("index.html", old_html("home")),
    path("login.html", old_html("login")),
    path("forgot-password.html", old_html("forgot-password")),
    path("reset-password.html", old_html("reset-password")),
    path("set-password.html", old_html("set-password")),
    path("staff/dashboard.html", old_html("staff-dashboard")),
    path("student/dashboard.html", old_html("student-dashboard")),
]
