"""
ชุดทดสอบอัตโนมัติของระบบยืม-คืน — รันด้วย:   python manage.py test

ครอบคลุมกระบวนการหลักทั้งหมด: จอง → รับ → คืน, ของหมด, จองซ้ำ, บทลงโทษ, พักสิทธิ์หมดอายุ,
no-show, แจ้งเตือนอีเมล, สิทธิ์การเข้าถึง (นักศึกษา/เจ้าหน้าที่), โปรไฟล์, และกฎ "สแกน QR ≠ ยืนยัน"
(Django test runner จะสร้างฐานข้อมูลทดสอบแยกให้เอง และใช้ email backend จำลอง ไม่ส่งอีเมลจริง)
"""
from datetime import datetime, time as dtime, timedelta

from django.core import mail
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .jobs import cancel_expired_bookings, lift_expired_suspensions, run_daily_due_date_checks
from .models import (
    Booking, Equipment, EquipmentCategory, EquipmentUnit, NotificationLog, PenaltySettings, User,
)
from .services import BookingError, confirm_pickup, confirm_return, create_booking


class BaseTestCase(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        self.settings_obj = PenaltySettings.get_solo()
        self.category = EquipmentCategory.objects.create(name="โน้ตบุ๊ก")
        self.equipment = Equipment.objects.create(category=self.category, name="Notebook A", max_borrow_days=7)
        self.unit1 = EquipmentUnit.objects.create(equipment=self.equipment, serial_number="NB-001")
        self.unit2 = EquipmentUnit.objects.create(equipment=self.equipment, serial_number="NB-002")

        self.student = self.make_student("s1", "s1@example.ac.th", "6501001")
        self.student2 = self.make_student("s2", "s2@example.ac.th", "6501002")
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.ac.th", password="Pass!word123", role=User.Role.STAFF,
        )

    def make_student(self, username, email, student_id):
        return User.objects.create_user(
            username=username, email=email, password="Pass!word123",
            first_name="สมชาย", last_name="ใจดี", student_id=student_id, role=User.Role.STUDENT,
        )

    def client_for(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    def book(self, student=None, days=3, start=None):
        start = start or self.today
        return create_booking(student or self.student, self.equipment.id, start, start + timedelta(days=days))


class BookingFlowTests(BaseTestCase):
    def test_full_flow_book_pickup_return(self):
        booking = self.book()
        booking.unit.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.AWAITING_PICKUP)
        self.assertEqual(booking.unit.status, EquipmentUnit.Status.RESERVED)
        self.assertEqual(self.equipment.available_units, 1)

        confirm_pickup(booking, self.staff, "สภาพดี")
        booking.refresh_from_db()
        booking.unit.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.BORROWED)
        self.assertEqual(booking.unit.status, EquipmentUnit.Status.BORROWED)

        confirm_return(booking, self.staff, "ปกติ")
        booking.refresh_from_db()
        booking.unit.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.RETURNED)
        self.assertEqual(booking.unit.status, EquipmentUnit.Status.AVAILABLE)
        self.assertFalse(booking.penalty_applied)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_suspended)

    def test_out_of_stock_rejected(self):
        self.book(self.student)
        self.book(self.student2)
        student3 = self.make_student("s3", "s3@example.ac.th", "6501003")
        with self.assertRaises(BookingError):
            self.book(student3)

    def test_same_student_cannot_double_book_same_model(self):
        self.book(self.student)
        with self.assertRaises(BookingError):
            self.book(self.student)

    def test_invalid_dates_rejected(self):
        with self.assertRaises(BookingError):  # คืนก่อนวันเริ่ม
            create_booking(self.student, self.equipment.id, self.today, self.today)
        with self.assertRaises(BookingError):  # เริ่มยืมย้อนหลัง
            create_booking(self.student, self.equipment.id, self.today - timedelta(days=1), self.today + timedelta(days=2))
        with self.assertRaises(BookingError):  # ยืมนานเกินกำหนดของรุ่นนี้
            create_booking(self.student, self.equipment.id, self.today, self.today + timedelta(days=30))
        with self.assertRaises(BookingError):  # จองล่วงหน้านานเกินไป
            create_booking(self.student, self.equipment.id, self.today + timedelta(days=30), self.today + timedelta(days=32))

    def test_cancel_returns_unit_to_stock(self):
        client = self.client_for(self.student)
        resp = client.post("/api/bookings/", {
            "equipment_id": self.equipment.id,
            "start_date": str(self.today), "end_date": str(self.today + timedelta(days=2)),
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        booking_id = resp.data["id"]
        self.assertEqual(self.equipment.available_units, 1)

        resp = client.post(f"/api/bookings/{booking_id}/cancel/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.equipment.available_units, 2)
        self.assertEqual(Booking.objects.get(pk=booking_id).status, Booking.Status.CANCELLED)

    def test_advance_booking_deadline_is_relative_to_start_date(self):
        start = self.today + timedelta(days=3)
        booking = self.book(days=2, start=start)
        # ไม่ควรหมดอายุก่อนถึงวันเริ่มยืมจริง
        start_of_day = timezone.make_aware(datetime.combine(start, dtime.min), timezone.get_current_timezone())
        self.assertGreater(booking.booking_expires_at, start_of_day)


class PenaltyTests(BaseTestCase):
    def _borrowed_booking(self, end_offset_days):
        booking = self.book(days=2)
        confirm_pickup(booking, self.staff)
        Booking.objects.filter(pk=booking.pk).update(requested_end_date=self.today + timedelta(days=end_offset_days))
        booking.refresh_from_db()
        return booking

    def test_late_return_suspends_student_and_sends_emails(self):
        self.settings_obj.overdue_days_threshold = 1
        self.settings_obj.suspension_days = 3
        self.settings_obj.save()
        booking = self._borrowed_booking(end_offset_days=-2)  # เกินกำหนด 2 วัน
        mail.outbox.clear()

        confirm_return(booking, self.staff)
        booking.refresh_from_db()
        self.student.refresh_from_db()
        self.assertTrue(booking.penalty_applied)
        self.assertEqual(booking.overdue_days_at_return, 2)
        self.assertTrue(self.student.is_suspended)
        self.assertEqual(self.student.suspended_until, self.today + timedelta(days=3))
        self.assertTrue(self.student.is_currently_suspended)
        # อีเมลรับคืน + อีเมลแจ้งพักสิทธิ์
        subjects = " | ".join(m.subject for m in mail.outbox)
        self.assertIn("รับคืน", subjects)
        self.assertIn("พักสิทธิ์", subjects)

        with self.assertRaises(BookingError):  # จองใหม่ไม่ได้ระหว่างถูกพัก
            self.book(self.student)

    def test_return_on_time_no_penalty(self):
        booking = self._borrowed_booking(end_offset_days=0)
        confirm_return(booking, self.staff)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_suspended)

    def test_threshold_setting_is_respected(self):
        self.settings_obj.overdue_days_threshold = 3
        self.settings_obj.save()
        booking = self._borrowed_booking(end_offset_days=-2)  # เกิน 2 วัน < เกณฑ์ 3 วัน
        confirm_return(booking, self.staff)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_suspended)

    def test_suspension_lifts_on_return_date_and_by_job(self):
        self.student.is_suspended = True
        self.student.suspended_until = self.today  # วันนี้กลับมาจองได้แล้ว
        self.student.save()
        self.assertTrue(self.student.can_make_new_booking())
        self.assertFalse(self.student.is_currently_suspended)

        self.assertEqual(lift_expired_suspensions(), 1)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_suspended)

    def test_still_suspended_before_end_date(self):
        self.student.is_suspended = True
        self.student.suspended_until = self.today + timedelta(days=1)
        self.student.save()
        self.assertFalse(self.student.can_make_new_booking())

    def test_staff_can_unsuspend(self):
        self.student.is_suspended = True
        self.student.suspended_until = self.today + timedelta(days=5)
        self.student.save()
        resp = self.client_for(self.staff).post(f"/api/staff/students/{self.student.id}/unsuspend/")
        self.assertEqual(resp.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.can_make_new_booking())


class JobTests(BaseTestCase):
    def test_no_show_is_cancelled_and_stock_restored(self):
        booking = self.book()
        Booking.objects.filter(pk=booking.pk).update(booking_expires_at=timezone.now() - timedelta(hours=1))
        mail.outbox.clear()

        cancel_expired_bookings()
        booking.refresh_from_db()
        booking.unit.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.CANCELLED)
        self.assertEqual(booking.cancel_reason, Booking.CancelReason.NO_SHOW)
        self.assertEqual(booking.unit.status, EquipmentUnit.Status.AVAILABLE)
        self.assertTrue(NotificationLog.objects.filter(trigger=NotificationLog.Trigger.AUTO_CANCELLED).exists())

    def test_picked_up_booking_not_cancelled_by_job(self):
        booking = self.book()
        confirm_pickup(booking, self.staff)
        Booking.objects.filter(pk=booking.pk).update(booking_expires_at=timezone.now() - timedelta(hours=1))
        cancel_expired_bookings()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.BORROWED)

    def test_daily_job_reminders_overdue_and_no_duplicates(self):
        booking = self.book(days=2)
        confirm_pickup(booking, self.staff)
        Booking.objects.filter(pk=booking.pk).update(requested_end_date=self.today - timedelta(days=1))
        mail.outbox.clear()

        run_daily_due_date_checks()
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.OVERDUE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("เกินกำหนด", mail.outbox[0].subject)
        self.assertIn("พักสิทธิ์", mail.outbox[0].body)  # อีเมลต้องบอกกติกาบทลงโทษ

        run_daily_due_date_checks()  # รันซ้ำวันเดียวกัน ต้องไม่ส่งซ้ำ
        self.assertEqual(len(mail.outbox), 1)

    def test_due_soon_and_due_today_reminders(self):
        b1 = self.book(self.student, days=2)
        confirm_pickup(b1, self.staff)
        Booking.objects.filter(pk=b1.pk).update(requested_end_date=self.today + timedelta(days=1))
        b2 = self.book(self.student2, days=2)
        confirm_pickup(b2, self.staff)
        Booking.objects.filter(pk=b2.pk).update(requested_end_date=self.today)
        mail.outbox.clear()

        run_daily_due_date_checks()
        triggers = set(NotificationLog.objects.values_list("trigger", flat=True))
        self.assertIn(NotificationLog.Trigger.REMINDER_DUE_SOON, triggers)
        self.assertIn(NotificationLog.Trigger.REMINDER_DUE_TODAY, triggers)

    def test_email_failure_is_logged_not_raised(self):
        self.student.email = ""
        self.student.save()
        self.book()  # ต้องจองสำเร็จแม้ไม่มีอีเมลให้ส่ง
        log = NotificationLog.objects.filter(trigger=NotificationLog.Trigger.BOOKING_CONFIRMED).first()
        self.assertIsNotNone(log)
        self.assertFalse(log.is_success)


class ApiAndPermissionTests(BaseTestCase):
    def test_login_returns_token_and_user(self):
        resp = APIClient().post("/api/auth/login/", {"email": "s1@example.ac.th", "password": "Pass!word123"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("token", resp.data)
        self.assertEqual(resp.data["user"]["role"], "student")

    def test_login_wrong_password(self):
        resp = APIClient().post("/api/auth/login/", {"email": "s1@example.ac.th", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_student_cannot_use_staff_endpoints(self):
        client = self.client_for(self.student)
        for url in ["/api/staff/bookings/", "/api/staff/dashboard-summary/", "/api/staff/students/",
                    "/api/staff/penalty-settings/", "/api/staff/notifications/"]:
            self.assertEqual(client.get(url).status_code, 403, url)

    def test_staff_cannot_book(self):
        resp = self.client_for(self.staff).post("/api/bookings/", {
            "equipment_id": self.equipment.id,
            "start_date": str(self.today), "end_date": str(self.today + timedelta(days=1)),
        }, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_blocked_but_public_equipment_open(self):
        anon = APIClient()
        self.assertEqual(anon.get("/api/equipment/").status_code, 401)
        resp = anon.get("/api/public/equipment/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data[0]["available_units"], 2)

    def test_qr_lookup_does_not_change_status(self):
        booking = self.book()
        client = self.client_for(self.staff)
        resp = client.get(f"/api/staff/bookings/lookup/?code={booking.booking_code.lower()}")
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.AWAITING_PICKUP)  # สแกนแล้วยังไม่เปลี่ยนสถานะ

        resp = client.post(f"/api/staff/bookings/{booking.id}/confirm-pickup/", {"condition_note": "ok"}, format="json")
        self.assertEqual(resp.status_code, 200)
        booking.refresh_from_db()
        self.assertEqual(booking.status, Booking.Status.BORROWED)
        self.assertEqual(booking.confirmed_by_pickup, self.staff)

    def test_cannot_confirm_return_before_pickup(self):
        booking = self.book()
        resp = self.client_for(self.staff).post(f"/api/staff/bookings/{booking.id}/confirm-return/", {}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_student_cannot_cancel_others_booking(self):
        booking = self.book(self.student)
        resp = self.client_for(self.student2).post(f"/api/bookings/{booking.id}/cancel/")
        self.assertEqual(resp.status_code, 404)

    def test_profile_update_persists(self):
        client = self.client_for(self.student)
        resp = client.patch("/api/auth/me/", {"first_name": "สมศักดิ์", "last_name": "รักดี"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.student.refresh_from_db()
        self.assertEqual(self.student.first_name, "สมศักดิ์")
        self.assertEqual(self.student.last_name, "รักดี")
        # แก้ email/role ผ่านโปรไฟล์ไม่ได้
        client.patch("/api/auth/me/", {"role": "staff", "email": "x@x.com"}, format="json")
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, "student")
        self.assertEqual(self.student.email, "s1@example.ac.th")

    def test_change_password(self):
        client = self.client_for(self.student)
        bad = client.post("/api/auth/change-password/", {"old_password": "nope", "new_password": "NewPass!word456"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = client.post("/api/auth/change-password/", {"old_password": "Pass!word123", "new_password": "NewPass!word456"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password("NewPass!word456"))

    def test_createsuperuser_gets_staff_role(self):
        admin = User.objects.create_superuser(username="root", email="root@example.ac.th", password="Pass!word123")
        self.assertEqual(admin.role, "staff")

    def test_unit_status_guard(self):
        booking = self.book()
        client = self.client_for(self.staff)
        resp = client.patch(f"/api/staff/units/{booking.unit_id}/", {"status": "disabled"}, format="json")
        self.assertEqual(resp.status_code, 400)  # กำลังถูกจองอยู่ แก้สถานะไม่ได้
        free_unit = EquipmentUnit.objects.exclude(pk=booking.unit_id).first()
        resp = client.patch(f"/api/staff/units/{free_unit.id}/", {"status": "disabled"}, format="json")
        self.assertEqual(resp.status_code, 200)
        resp = client.patch(f"/api/staff/units/{free_unit.id}/", {"status": "borrowed"}, format="json")
        self.assertEqual(resp.status_code, 400)

    def test_staff_add_unit_and_category_and_penalty_settings(self):
        client = self.client_for(self.staff)
        resp = client.post(f"/api/staff/equipment/{self.equipment.id}/units/", {"serial_number": "NB-003"}, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(self.equipment.available_units, 3)
        dup = client.post(f"/api/staff/equipment/{self.equipment.id}/units/", {"serial_number": "NB-003"}, format="json")
        self.assertEqual(dup.status_code, 400)

        resp = client.post("/api/staff/equipment-categories/", {"name": "บอร์ด"}, format="json")
        self.assertEqual(resp.status_code, 201)
        resp = client.post("/api/staff/equipment/", {
            "category": resp.data["id"], "name": "ESP32", "max_borrow_days": 7, "is_active": True,
        }, format="json")
        self.assertEqual(resp.status_code, 201)

        resp = client.patch("/api/staff/penalty-settings/", {"suspension_days": 5, "overdue_days_threshold": 2}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(PenaltySettings.get_solo().suspension_days, 5)
        bad = client.patch("/api/staff/penalty-settings/", {"suspension_days": 0}, format="json")
        self.assertEqual(bad.status_code, 400)

    def test_staff_create_and_import_students(self):
        client = self.client_for(self.staff)
        resp = client.post("/api/staff/students/", {
            "email": "new@example.ac.th", "first_name": "ใหม่", "last_name": "ทดสอบ", "student_id": "6509999",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        new_user = User.objects.get(email="new@example.ac.th")
        self.assertFalse(new_user.has_usable_password())  # ต้องตั้งรหัสผ่านเองผ่าน "ลืมรหัสผ่าน"

        resp = client.post("/api/staff/students/import/", {"students": [
            {"email": "a@example.ac.th", "first_name": "เอ", "last_name": "หนึ่ง", "student_id": "7001"},
            {"email": "new@example.ac.th", "first_name": "ซ้ำ", "last_name": "", "student_id": "7002"},
            {"email": "not-an-email", "first_name": "ผิด", "last_name": "", "student_id": ""},
        ]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["created"], 1)
        self.assertEqual(resp.data["skipped"], 2)

    def test_dashboard_summary_counts(self):
        booking = self.book(self.student)
        confirm_pickup(booking, self.staff)
        Booking.objects.filter(pk=booking.pk).update(requested_end_date=self.today - timedelta(days=1))
        resp = self.client_for(self.staff).get("/api/staff/dashboard-summary/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["overdue_count"], 1)  # นับรวมแม้ job ยังไม่ทันรัน
        self.assertEqual(resp.data["borrowed_count"], 0)
        self.assertEqual(resp.data["available_units"], 1)
