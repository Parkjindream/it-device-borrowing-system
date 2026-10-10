"""
สร้างบัญชีผู้ใช้ทั่วไป (ไม่ใช่ superuser) จากค่าใน .env ให้อัตโนมัติ — docker compose เรียกตอน migrate ทุกครั้ง

    SEED_USER_USERNAME=harry
    SEED_USER_EMAIL=harry@example.com     # หน้าเว็บ login ด้วยอีเมลนี้
    SEED_USER_PASSWORD=1234
    SEED_USER_ROLE=student                # student (ค่าเริ่มต้น) หรือ staff

- ไม่ได้ตั้ง USERNAME/PASSWORD -> ข้ามไปเฉย ๆ
- มีบัญชีชื่อนี้อยู่แล้ว -> ไม่แตะอะไรเลย (ไม่รีเซ็ตรหัสผ่านที่เจ้าของเปลี่ยนไปแล้วทับ)
"""
import os

from django.core.management.base import BaseCommand, CommandError

from rental.models import User


class Command(BaseCommand):
    help = "สร้างบัญชีผู้ใช้ทั่วไปจาก SEED_USER_* ถ้ายังไม่มี (รันซ้ำได้ไม่มีผลเสีย)"

    def handle(self, *args, **options):
        username = os.environ.get("SEED_USER_USERNAME", "").strip()
        email = os.environ.get("SEED_USER_EMAIL", "").strip()
        password = os.environ.get("SEED_USER_PASSWORD", "")
        role = os.environ.get("SEED_USER_ROLE", "").strip() or User.Role.STUDENT

        if not username or not password:
            return

        if role not in User.Role.values:
            raise CommandError(f"SEED_USER_ROLE ต้องเป็น {' หรือ '.join(User.Role.values)} (ได้ '{role}')")

        if User.objects.filter(username=username).exists():
            self.stdout.write(f"มีบัญชี '{username}' อยู่แล้ว — ไม่ต้องสร้างใหม่")
            return

        User.objects.create_user(username=username, email=email, password=password, role=role)
        self.stdout.write(self.style.SUCCESS(f"สร้างบัญชี '{username}' ({User.Role(role).label}) เรียบร้อย"))
