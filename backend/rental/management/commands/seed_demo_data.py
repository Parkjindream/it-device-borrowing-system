"""
คำสั่งสร้างข้อมูลตัวอย่างสำหรับทดสอบระบบทั้งหมด รันด้วย:

    python manage.py seed_demo_data

สร้าง: หมวดหมู่อุปกรณ์, อุปกรณ์ + จำนวนเครื่องจริง, บัญชีเจ้าหน้าที่ 1 คน,
บัญชีนักศึกษาตัวอย่าง 3 คน, และตั้งค่า PenaltySettings เริ่มต้น

*** สำหรับทดสอบ/พัฒนาเท่านั้น — ห้ามรันกับฐานข้อมูล production จริง
    เปลี่ยนรหัสผ่านตัวอย่างทั้งหมดก่อนใช้งานจริงเสมอ ***
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from rental.models import (
    Booking, EquipmentCategory, Equipment, EquipmentUnit, NotificationLog, PenaltySettings, User,
)


DEMO_PASSWORD = "Passw0rd!2026"  # เปลี่ยนก่อนใช้งานจริงเสมอ


class Command(BaseCommand):
    help = "สร้างข้อมูลตัวอย่างสำหรับทดสอบระบบยืม-คืนอุปกรณ์ไอทีแบบครบวงจร (dev เท่านั้น)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true",
            help="ลบการจอง/อุปกรณ์/หมวดหมู่เดิมทั้งหมดก่อน แล้วสร้างชุดอุปกรณ์ใหม่ (ไม่ลบบัญชีผู้ใช้) — dev เท่านั้น",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            NotificationLog.objects.all().delete()
            Booking.objects.all().delete()
            EquipmentUnit.objects.all().delete()
            Equipment.objects.all().delete()
            EquipmentCategory.objects.all().delete()
            self.stdout.write(self.style.WARNING("ลบการจอง/อุปกรณ์/หมวดหมู่เดิมทั้งหมดแล้ว"))

        self.stdout.write("กำลังสร้างข้อมูลตัวอย่าง...")

        PenaltySettings.get_solo()  # สร้างค่าตั้งต้นถ้ายังไม่มี

        categories = self._create_categories()
        self._create_equipment(categories)
        staff = self._create_staff()
        students = self._create_students()

        self.stdout.write(self.style.SUCCESS("\nสร้างข้อมูลตัวอย่างสำเร็จ!"))
        self.stdout.write("\nบัญชีสำหรับทดสอบ (รหัสผ่านเดียวกันหมด):")
        self.stdout.write(f"  รหัสผ่าน: {DEMO_PASSWORD}")
        self.stdout.write(f"  เจ้าหน้าที่: {staff.email}")
        for s in students:
            self.stdout.write(f"  นักศึกษา: {s.email}")
        self.stdout.write(
            self.style.WARNING("\n*** เปลี่ยนรหัสผ่านทั้งหมดนี้ก่อนใช้งานจริงในสถานศึกษา ***")
        )

    def _create_categories(self):
        names = ["โน้ตบุ๊ก", "แท็บเล็ต (iPad)", "บอร์ดไมโครคอนโทรลเลอร์"]
        categories = {}
        for name in names:
            cat, _ = EquipmentCategory.objects.get_or_create(name=name)
            categories[name] = cat
        return categories

    def _create_equipment(self, categories):
        # (ชื่อ, หมวด, ยืมได้สูงสุดกี่วัน, จำนวนเครื่อง, คำอธิบาย)
        equipment_plan = [
            ("โน้ตบุ๊ก Lenovo ThinkPad E14", "โน้ตบุ๊ก", 7, 6,
             "โน้ตบุ๊กสำหรับเรียนและทำงานทั่วไป เหมาะกับการเขียนโปรแกรมและทำรายงาน"),
            ("โน้ตบุ๊ก Dell Latitude 5420", "โน้ตบุ๊ก", 7, 6,
             "โน้ตบุ๊กสำหรับเรียนและทำงานทั่วไป น้ำหนักเบา พกพาสะดวก"),
            ("โน้ตบุ๊ก HP ProBook 450 G8", "โน้ตบุ๊ก", 7, 4,
             "โน้ตบุ๊กหน้าจอ 15.6 นิ้ว เหมาะกับงานเอกสารและงานนำเสนอ"),
            ("iPad (Gen 9)", "แท็บเล็ต (iPad)", 7, 4,
             "แท็บเล็ตสำหรับจดบันทึก อ่านเอกสาร และงานสื่อการเรียนรู้"),
            ("iPad (Gen 10)", "แท็บเล็ต (iPad)", 7, 4,
             "แท็บเล็ตรุ่นใหม่ หน้าจอใหญ่ขึ้น เหมาะกับงานออกแบบและนำเสนอ"),
            ("ESP32 DevKit V1", "บอร์ดไมโครคอนโทรลเลอร์", 7, 10,
             "บอร์ด Wi-Fi + Bluetooth สำหรับโปรเจกต์ IoT"),
            ("ESP8266 NodeMCU", "บอร์ดไมโครคอนโทรลเลอร์", 7, 10,
             "บอร์ด Wi-Fi ราคาประหยัด เหมาะกับงาน IoT เบื้องต้น"),
            ("Raspberry Pi 4 Model B (4GB)", "บอร์ดไมโครคอนโทรลเลอร์", 7, 5,
             "คอมพิวเตอร์บอร์ดเดี่ยว รัน Linux ได้ เหมาะกับโปรเจกต์ขนาดกลาง"),
            ("Arduino Uno R3", "บอร์ดไมโครคอนโทรลเลอร์", 7, 10,
             "บอร์ดเริ่มต้นสำหรับเรียนอิเล็กทรอนิกส์และการควบคุมเบื้องต้น"),
        ]
        for name, cat_name, max_days, unit_count, description in equipment_plan:
            equipment, _ = Equipment.objects.get_or_create(
                name=name,
                defaults={
                    "category": categories[cat_name],
                    "max_borrow_days": max_days,
                    "description": description,
                },
            )
            existing_units = equipment.units.count()
            for i in range(existing_units, unit_count):
                EquipmentUnit.objects.create(
                    equipment=equipment,
                    serial_number=f"{equipment.id:03d}-{i + 1:03d}",
                )

    def _create_staff(self):
        staff, created = User.objects.get_or_create(
            username="staff01",
            defaults={
                "email": "staff01@example.ac.th",
                "first_name": "เจ้าหน้าที่",
                "last_name": "ห้องโสตฯ",
                "role": User.Role.STAFF,
                "is_staff": True,  # ให้เข้าหน้า Django admin ได้ด้วย
            },
        )
        if created:
            staff.set_password(DEMO_PASSWORD)
            staff.save()
        return staff

    def _create_students(self):
        plan = [
            ("student01", "student01@example.ac.th", "สมชาย", "ใจดี", "6501001"),
            ("student02", "student02@example.ac.th", "สมหญิง", "รักเรียน", "6501002"),
            ("student03", "student03@example.ac.th", "วิชัย", "ตั้งใจ", "6501003"),
        ]
        students = []
        for username, email, first, last, student_id in plan:
            student, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "role": User.Role.STUDENT,
                    "student_id": student_id,
                },
            )
            if created:
                student.set_password(DEMO_PASSWORD)
                student.save()
            students.append(student)
        return students
