"""
ลบบัญชีทดสอบที่สร้างโดย seed_demo_data ทิ้ง (staff01, student01-03) ก่อนใช้งานจริง

    python manage.py remove_demo_accounts          # ดูก่อนว่าจะลบอะไรบ้าง (dry-run)
    python manage.py remove_demo_accounts --confirm # ลบจริง

ทำ 3 ขั้นตอนตามลำดับเพื่อความถูกต้อง:
1. คืนสถานะอุปกรณ์ที่ติดอยู่กับการจองของบัญชีทดสอบให้เป็น "ว่าง" (กันเครื่องค้างสถานะผิด)
2. ลบประวัติการจองทั้งหมดของบัญชีทดสอบ (ต้องลบก่อนเพราะ Booking.student ป้องกันการลบ user ที่มีประวัติอยู่)
3. ลบบัญชีผู้ใช้ทดสอบทั้งหมด (ประวัติอีเมลของบัญชีเหล่านี้จะถูกลบตามไปอัตโนมัติ)

ไม่แตะอุปกรณ์/หมวดหมู่ที่ seed_demo_data สร้างไว้ (ของพวกนั้นเป็นคลังอุปกรณ์จริงที่ใช้ต่อได้)
ถ้าต้องการลบอุปกรณ์ตัวอย่างด้วย ให้ลบเองผ่านหน้าเว็บ (ปุ่ม "ลบ" ในแท็บจัดการคลังอุปกรณ์)
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from rental.models import Booking, EquipmentUnit, User

DEMO_USERNAMES = ["staff01", "student01", "student02", "student03"]


class Command(BaseCommand):
    help = "ลบบัญชีทดสอบ (staff01, student01-03) ที่สร้างโดย seed_demo_data ทิ้งก่อนใช้งานจริง"

    def add_arguments(self, parser):
        parser.add_argument("--confirm", action="store_true", help="ลบจริง (ไม่ใส่ = แค่แสดงตัวอย่างว่าจะลบอะไร)")

    @transaction.atomic
    def handle(self, *args, **options):
        users = User.objects.filter(username__in=DEMO_USERNAMES)
        if not users.exists():
            self.stdout.write(self.style.WARNING("ไม่พบบัญชีทดสอบในระบบ (อาจลบไปแล้ว หรือยังไม่เคยรัน seed_demo_data)"))
            return

        booking_count = Booking.objects.filter(student__in=users).count()
        usernames = list(users.values_list("username", flat=True))

        self.stdout.write(f"จะลบบัญชี: {', '.join(usernames)}")
        self.stdout.write(f"จะลบประวัติการจองที่เกี่ยวข้อง: {booking_count} รายการ")

        if not options["confirm"]:
            self.stdout.write(self.style.WARNING(
                "\nนี่เป็นแค่การแสดงตัวอย่าง (dry-run) ยังไม่ได้ลบจริง\n"
                "รันคำสั่งเดิมพร้อม --confirm เพื่อลบจริง:\n"
                "  python manage.py remove_demo_accounts --confirm"
            ))
            return

        # 1) คืนสถานะอุปกรณ์ที่ติดอยู่กับการจองค้างของบัญชีทดสอบ กันเครื่องค้างสถานะผิด
        stuck_statuses = [Booking.Status.AWAITING_PICKUP, Booking.Status.BORROWED, Booking.Status.OVERDUE]
        freed_units = EquipmentUnit.objects.filter(
            bookings__student__in=users, bookings__status__in=stuck_statuses,
        ).distinct()
        freed_count = freed_units.update(status=EquipmentUnit.Status.AVAILABLE)

        # 2) ลบประวัติการจองทั้งหมดของบัญชีทดสอบ (ต้องลบก่อนจึงจะลบ user ได้)
        deleted_bookings, _ = Booking.objects.filter(student__in=users).delete()

        # 3) ลบบัญชีผู้ใช้ทดสอบ (ประวัติอีเมลของบัญชีเหล่านี้ลบตามอัตโนมัติ)
        deleted_users, _ = users.delete()

        self.stdout.write(self.style.SUCCESS(
            f"\nลบสำเร็จ: บัญชีทดสอบ {deleted_users} บัญชี, ประวัติการจอง {deleted_bookings} รายการ"
            f"{f', คืนสถานะอุปกรณ์ {freed_count} เครื่องกลับเป็นว่าง' if freed_count else ''}"
        ))
        self.stdout.write(
            "\nขั้นต่อไป: สร้างบัญชีแอดมินจริงด้วย python manage.py createsuperuser "
            "(ใช้อีเมลจริงของคุณ) แล้วเพิ่มนักศึกษาจริงผ่านแท็บ \"จัดการนักศึกษา\" ในหน้าเจ้าหน้าที่"
        )