"""
ที่เก็บไฟล์อัปโหลด (รูปอุปกรณ์/รูปโปรไฟล์) บน MinIO — เปิดใช้เมื่อตั้ง MINIO_ENDPOINT (ดู settings.py)

ลิงก์รูปที่ส่งให้เบราว์เซอร์ยังเป็น /media/<ไฟล์> เหมือนตอนเก็บลงดิสก์ — frontend ไม่ต้องแก้อะไร
nginx (หรือ Django ตอน DEBUG) จะไปดึงไฟล์จาก MinIO มาให้เอง ไม่ต้องเปิด MinIO ออกอินเทอร์เน็ต
"""
from django.conf import settings
from django.utils.encoding import filepath_to_uri
from storages.backends.s3 import S3Storage


class MediaStorage(S3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        return f"{settings.MEDIA_URL}{filepath_to_uri(name)}"
