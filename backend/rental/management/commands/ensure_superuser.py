"""
สร้างบัญชีแอดมิน (เจ้าหน้าที่) จากค่าใน .env ให้อัตโนมัติ — docker compose เรียกตอนเริ่มระบบทุกครั้ง

    DJANGO_SUPERUSER_USERNAME=admin
    DJANGO_SUPERUSER_EMAIL=admin@yourcollege.ac.th
    DJANGO_SUPERUSER_PASSWORD=...

- ไม่ได้ตั้ง USERNAME/PASSWORD -> ข้ามไปเฉย ๆ (สร้างเองทีหลังด้วย createsuperuser ได้)
- มีบัญชีชื่อนี้อยู่แล้ว -> ไม่แตะอะไรเลย (ไม่รีเซ็ตรหัสผ่านที่แอดมินเปลี่ยนไปแล้วทับ)
"""
import os

from django.core.management.base import BaseCommand

from rental.models import User


class Command(BaseCommand):
    help = "สร้างบัญชีแอดมินจาก DJANGO_SUPERUSER_* ถ้ายังไม่มี (รันซ้ำได้ไม่มีผลเสีย)"

    def handle(self, *args, **options):
        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "").strip()
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not username or not password:
            self.stdout.write("ไม่ได้ตั้ง DJANGO_SUPERUSER_USERNAME/PASSWORD — ข้ามการสร้างบัญชีแอดมินอัตโนมัติ")
            return

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"มีบัญชีแอดมิน '{username}' อยู่แล้ว — ไม่ต้องสร้างใหม่")
            return

        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"สร้างบัญชีแอดมิน '{username}' (เจ้าหน้าที่) เรียบร้อย"))
