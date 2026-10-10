"""
เตรียม bucket เก็บไฟล์อัปโหลดบน MinIO — docker compose เรียกตอน migrate ทุกครั้ง

- ยังไม่มี bucket -> สร้างให้
- ตั้งให้ "อ่านไฟล์ทีละไฟล์" ได้โดยไม่ต้อง login (nginx ดึงรูปมาเสิร์ฟที่ /media/ ได้)
  แต่ไม่เปิดให้ดูรายชื่อไฟล์ทั้งหมดหรืออัปโหลด/ลบ — ทำได้เฉพาะ backend ที่มีรหัส MinIO
- ไม่ได้ตั้ง MINIO_ENDPOINT (เก็บไฟล์ลงดิสก์) -> ข้ามไปเฉย ๆ
"""
import json

from botocore.exceptions import ClientError
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "สร้าง bucket เก็บไฟล์อัปโหลดบน MinIO ถ้ายังไม่มี (รันซ้ำได้ไม่มีผลเสีย)"

    def handle(self, *args, **options):
        if not settings.MINIO_ENDPOINT:
            self.stdout.write("ไม่ได้ตั้ง MINIO_ENDPOINT — เก็บไฟล์อัปโหลดลงดิสก์ ข้ามการสร้าง bucket")
            return

        bucket = default_storage.bucket_name
        client = default_storage.connection.meta.client
        try:
            client.head_bucket(Bucket=bucket)
            self.stdout.write(f"มี bucket '{bucket}' อยู่แล้ว")
        except ClientError:
            client.create_bucket(Bucket=bucket)
            self.stdout.write(self.style.SUCCESS(f"สร้าง bucket '{bucket}' เรียบร้อย"))

        policy = {
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            }],
        }
        client.put_bucket_policy(Bucket=bucket, Policy=json.dumps(policy))
