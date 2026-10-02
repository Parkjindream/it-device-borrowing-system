"""
ทดสอบว่าตั้งค่าอีเมล (SMTP) ถูกต้องและส่งออกไปได้จริงหรือไม่

    python manage.py send_test_email you@example.com
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "ส่งอีเมลทดสอบไปยังที่อยู่ที่ระบุ เพื่อเช็คการตั้งค่า SMTP"

    def add_arguments(self, parser):
        parser.add_argument("to", help="อีเมลปลายทางที่จะให้ส่งทดสอบ")

    def handle(self, *args, **options):
        backend = settings.EMAIL_BACKEND
        self.stdout.write(f"EMAIL_BACKEND = {backend}")
        if "console" in backend:
            self.stdout.write(self.style.WARNING(
                "ตอนนี้ตั้งเป็น console backend: อีเมลจะแค่ถูกพิมพ์ใน terminal ไม่ได้ส่งออกจริง\n"
                "ถ้าต้องการส่งจริง ให้แก้ .env ตามหัวข้อ 'ตั้งค่าอีเมลจริง' ใน README แล้วรันใหม่"
            ))
        try:
            send_mail(
                subject="ทดสอบอีเมลจากระบบยืม-คืนอุปกรณ์ไอที",
                message="ถ้าคุณเห็นอีเมลฉบับนี้ แสดงว่าตั้งค่าอีเมลของระบบถูกต้องแล้ว",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[options["to"]],
                fail_silently=False,
            )
        except Exception as exc:
            raise CommandError(f"ส่งอีเมลไม่สำเร็จ: {exc}")
        self.stdout.write(self.style.SUCCESS(f"ส่งคำสั่งส่งอีเมลไปที่ {options['to']} เรียบร้อย"))
