"""
ที่เก็บไฟล์อัปโหลด (รูปอุปกรณ์/รูปโปรไฟล์) บน S3-compatible storage (MinIO / Supabase Storage)
เปิดใช้เมื่อตั้ง MINIO_ENDPOINT (ดู settings.py)

- ไม่ตั้ง MEDIA_PUBLIC_BASE_URL: ลิงก์รูปเป็น /media/<ไฟล์> และ Django ดึงจาก storage มาส่งให้ (config/urls.py)
- ตั้ง MEDIA_PUBLIC_BASE_URL (เช่น URL สาธารณะของ bucket บน Supabase): ลิงก์รูปชี้ตรงไปที่ storage
  ไม่ผ่าน function ของ Vercel -> เร็วกว่า ประหยัดโควต้า และไม่ติดเพดาน body 4.5 MB ของ function
"""
from django.conf import settings
from django.utils.encoding import filepath_to_uri
from storages.backends.s3 import S3Storage


class MediaStorage(S3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        base = (getattr(settings, "MEDIA_PUBLIC_BASE_URL", "") or "").rstrip("/")
        if base:
            return f"{base}/{filepath_to_uri(name)}"
        return f"{settings.MEDIA_URL}{filepath_to_uri(name)}"