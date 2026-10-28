from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from django.urls import include, path
from django.views.decorators.http import require_safe

admin.site.site_header = "ศูนย์ยืม-คืนอุปกรณ์ไอที — ผู้ดูแลระบบ"
admin.site.site_title = "ผู้ดูแลระบบ"
admin.site.index_title = "จัดการข้อมูลระบบ"

# Django เสิร์ฟทั้งหมดใน origin เดียว:
#   /api/...     REST API (rental)
#   /api/admin/  Django admin (เฉพาะเมื่อ ENABLE_DJANGO_ADMIN)
#   /static/...  css/js/รูป/ฟอนต์ (WhiteNoise)
#   /media/...   รูปที่ผู้ใช้อัปโหลด
#   /...         หน้าเว็บ (frontend)
urlpatterns = [
    path("api/", include("rental.urls")),
    path("", include("frontend.urls")),
]

if settings.ENABLE_DJANGO_ADMIN:
    urlpatterns.insert(0, path("api/admin/", admin.site.urls))


@require_safe
def serve_media_from_storage(request, name):
    """
    รูปที่อัปโหลดเก็บใน MinIO (เปิดเฉพาะในเครือข่าย docker) — Django ดึงมาส่งให้เบราว์เซอร์ทีละไฟล์
    รับแค่ GET/HEAD และไม่ส่ง cookie/สิทธิ์ใด ๆ ต่อไปที่ MinIO
    """
    if not default_storage.exists(name):
        raise Http404
    response = FileResponse(default_storage.open(name))
    response["Cache-Control"] = "public, max-age=2592000"
    return response


if settings.MINIO_ENDPOINT:
    urlpatterns += [path(f"{settings.MEDIA_URL.strip('/')}/<path:name>", serve_media_from_storage)]
elif settings.DEBUG:
    # พัฒนาบนเครื่องโดยไม่ใช้ MinIO: ไฟล์อยู่ใน MEDIA_ROOT
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
