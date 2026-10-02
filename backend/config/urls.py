from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

admin.site.site_header = "ศูนย์ยืม-คืนอุปกรณ์ไอที — ผู้ดูแลระบบ"
admin.site.site_title = "ผู้ดูแลระบบ"
admin.site.index_title = "จัดการข้อมูลระบบ"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("rental.urls")),
]

# ตอนพัฒนา (DEBUG) ให้ Django เสิร์ฟรูปที่อัปโหลดเอง / ตอนใช้ Docker nginx เสิร์ฟ /media/ ให้
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
