from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404

admin.site.site_header = "ศูนย์ยืม-คืนอุปกรณ์ไอที — ผู้ดูแลระบบ"
admin.site.site_title = "ผู้ดูแลระบบ"
admin.site.index_title = "จัดการข้อมูลระบบ"

# nginx/dev_server.py ตัด /api ออกก่อนส่งมา ฝั่ง Django จึงเริ่มเส้นทางที่ราก
# (ภายนอกเข้าเป็น /api/auth/login/, /api/admin/ — prefix /api ตั้งไว้ที่ FORCE_SCRIPT_NAME ใน settings)
urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("rental.urls")),
]


def serve_media_from_storage(request, name):
    if not default_storage.exists(name):
        raise Http404
    return FileResponse(default_storage.open(name))


# ตอนพัฒนา (DEBUG) ให้ Django เสิร์ฟรูปที่อัปโหลดเอง / ตอนใช้ Docker nginx ดึงจาก MinIO มาเสิร์ฟ /media/ ให้
if settings.DEBUG:
    if settings.MINIO_ENDPOINT:
        urlpatterns += [path(f"{settings.MEDIA_URL.strip('/')}/<path:name>", serve_media_from_storage)]
    else:
        urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
