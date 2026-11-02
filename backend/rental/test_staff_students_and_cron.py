"""
ทดสอบ: ลบ/ปิดบัญชีนักศึกษา, endpoint งานอัตโนมัติ (/api/cron/run-jobs/), และการส่งอีเมลแบบ EMAIL_SYNC (serverless)
รันด้วย: python manage.py test rental.test_staff_students_and_cron
"""
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from rental import notifications
from rental.models import Booking, Equipment, EquipmentCategory, EquipmentUnit, NotificationLog, User


def at_hour(hour):
    """ตรึงเวลาปัจจุบันเป็น 'วันนี้ เวลา hour:30 ตามเวลาไทย' (ไม่ mock ฟังก์ชันของ timezone ทีละตัว กันรั่วไปงานอื่น)"""
    d = timezone.localdate()
    fixed = datetime(d.year, d.month, d.day, hour, 30, tzinfo=ZoneInfo("Asia/Bangkok"))
    return mock.patch("django.utils.timezone.now", return_value=fixed)


def mk_user(email, role="student", **kw):
    u = User.objects.create_user(username=email, email=email, password="pw-Strong-123", role=role, **kw)
    return u


class Base(TestCase):
    def setUp(self):
        self.staff = mk_user("staff@x.ac.th", "staff")
        self.s_no_hist = mk_user("a@x.ac.th", student_id="1")
        self.s_hist = mk_user("b@x.ac.th", student_id="2")
        self.s_open = mk_user("c@x.ac.th", student_id="3")
        cat = EquipmentCategory.objects.create(name="NB")
        eq = Equipment.objects.create(category=cat, name="Dell")
        self.u1 = EquipmentUnit.objects.create(equipment=eq, serial_number="S1")
        self.u2 = EquipmentUnit.objects.create(equipment=eq, serial_number="S2", status="reserved")
        self.u3 = EquipmentUnit.objects.create(equipment=eq, serial_number="S3", status="reserved")
        today = timezone.localdate()
        self.b_done = Booking.objects.create(
            student=self.s_hist, unit=self.u1, status="returned", requested_start_date=today,
            requested_end_date=today, booking_expires_at=timezone.now())
        self.b_open = Booking.objects.create(
            student=self.s_open, unit=self.u2, status="awaiting_pickup", requested_start_date=today,
            requested_end_date=today, booking_expires_at=timezone.now() + timedelta(hours=5))
        self.api = APIClient()
        self.api.force_authenticate(self.staff)

    def url(self, pk, suffix=""):
        return f"/api/staff/students/{pk}/{suffix}"


class StudentDeleteTests(Base):
    def test_delete_without_history(self):
        r = self.api.delete(self.url(self.s_no_hist.pk))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(User.objects.filter(pk=self.s_no_hist.pk).exists())

    def test_delete_with_history_is_blocked_and_suggests_deactivate(self):
        r = self.api.delete(self.url(self.s_hist.pk))
        self.assertEqual(r.status_code, 400)
        self.assertIn("ปิดบัญชี", r.data["detail"])
        self.assertTrue(User.objects.filter(pk=self.s_hist.pk).exists())
        self.assertTrue(Booking.objects.filter(pk=self.b_done.pk).exists())

    def test_delete_with_open_booking_is_blocked(self):
        r = self.api.delete(self.url(self.s_open.pk))
        self.assertEqual(r.status_code, 400)
        self.assertIn("ยังไม่จบ", r.data["detail"])
        self.assertTrue(User.objects.filter(pk=self.s_open.pk).exists())

    def test_student_cannot_delete(self):
        c = APIClient()
        c.force_authenticate(self.s_hist)
        self.assertEqual(c.delete(self.url(self.s_no_hist.pk)).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.s_no_hist.pk).exists())

    def test_cannot_delete_staff_via_student_endpoint(self):
        other = mk_user("s2@x.ac.th", "staff")
        self.assertEqual(self.api.delete(self.url(other.pk)).status_code, 404)
        self.assertTrue(User.objects.filter(pk=other.pk).exists())

    def test_unauthenticated(self):
        self.assertEqual(APIClient().delete(self.url(self.s_no_hist.pk)).status_code, 401)


class SetActiveTests(Base):
    def test_deactivate_revokes_token_and_blocks_api(self):
        tok = Token.objects.create(user=self.s_hist)
        r = self.api.post(self.url(self.s_hist.pk, "set-active/"), {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.data["is_active"])
        self.s_hist.refresh_from_db()
        self.assertFalse(self.s_hist.is_active)
        self.assertFalse(Token.objects.filter(key=tok.key).exists())
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION=f"Token {tok.key}")
        self.assertEqual(c.get("/api/auth/me/").status_code, 401)
        # ประวัติยังอยู่
        self.assertTrue(Booking.objects.filter(pk=self.b_done.pk).exists())

    def test_reactivate(self):
        self.s_hist.is_active = False
        self.s_hist.save()
        r = self.api.post(self.url(self.s_hist.pk, "set-active/"), {"is_active": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["is_active"])

    def test_deactivate_with_open_booking_blocked(self):
        r = self.api.post(self.url(self.s_open.pk, "set-active/"), {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 400)
        self.s_open.refresh_from_db()
        self.assertTrue(self.s_open.is_active)

    def test_non_bool_rejected(self):
        for bad in ("false", 0, None):
            r = self.api.post(self.url(self.s_hist.pk, "set-active/"), {"is_active": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)

    def test_student_forbidden(self):
        c = APIClient()
        c.force_authenticate(self.s_hist)
        r = c.post(self.url(self.s_no_hist.pk, "set-active/"), {"is_active": False}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_deactivated_cannot_request_password_reset_email(self):
        self.s_hist.is_active = False
        self.s_hist.save()
        from django.core import mail
        r = APIClient().post("/api/auth/password-reset/", {"email": self.s_hist.email}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(CRON_SECRET="s3cret-value")
class CronTests(Base):
    URL = "/api/cron/run-jobs/"

    def hdr(self, v="Bearer s3cret-value"):
        return {"HTTP_AUTHORIZATION": v}

    def test_auth(self):
        c = APIClient()
        self.assertEqual(c.get(self.URL).status_code, 401)
        self.assertEqual(c.get(self.URL, **self.hdr("Bearer wrong")).status_code, 401)
        self.assertEqual(c.get(self.URL, **self.hdr("Bearer é-ไทย")).status_code, 401)  # ต้องไม่ 500
        self.assertEqual(c.get(self.URL, **self.hdr("s3cret-value")).status_code, 401)  # ไม่มี Bearer

    @override_settings(CRON_SECRET="")
    def test_disabled_without_secret(self):
        self.assertEqual(APIClient().get(self.URL, **self.hdr("Bearer ")).status_code, 404)

    def test_only_expire_cancels_expired_and_frees_unit(self):
        self.b_open.booking_expires_at = timezone.now() - timedelta(minutes=1)
        self.b_open.save()
        with mock.patch("rental.views.run_daily_due_date_checks") as daily:
            r = APIClient().get(self.URL + "?only=expire", **self.hdr())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["jobs"], {"cancel_expired_bookings": "ok"})
        daily.assert_not_called()
        self.b_open.refresh_from_db()
        self.u2.refresh_from_db()
        self.assertEqual(self.b_open.status, "cancelled")
        self.assertEqual(self.u2.status, "available")

    def test_full_run_skips_daily_before_7(self):
        with at_hour(3), \
             mock.patch("rental.views.run_daily_due_date_checks") as daily:
            r = APIClient().get(self.URL, **self.hdr())
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.data["jobs"]["daily_due_date_checks"].startswith("skipped"))
        daily.assert_not_called()

    def test_full_run_runs_daily_after_7(self):
        with at_hour(7), \
             mock.patch("rental.views.run_daily_due_date_checks") as daily:
            r = APIClient().get(self.URL, **self.hdr())
        self.assertEqual(r.status_code, 200)
        daily.assert_called_once()
        self.assertEqual(r.data["jobs"]["daily_due_date_checks"], "ok")

    def test_one_job_failure_does_not_stop_other_and_returns_500(self):
        with at_hour(9), \
             mock.patch("rental.views.cancel_expired_bookings", side_effect=RuntimeError("boom")), \
             mock.patch("rental.views.run_daily_due_date_checks") as daily:
            r = APIClient().get(self.URL, **self.hdr())
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.data["jobs"], {"cancel_expired_bookings": "error", "daily_due_date_checks": "ok"})
        daily.assert_called_once()

    def test_real_daily_job_is_idempotent_same_day(self):
        # รายการที่ครบกำหนดวันนี้ -> ส่งเตือน 1 ครั้ง แม้เรียกงานรายวัน 3 รอบ
        from django.core import mail
        today = timezone.localdate()
        self.b_open.status = "borrowed"
        self.b_open.requested_end_date = today
        self.b_open.picked_up_at = timezone.now()
        self.b_open.save()
        for _ in range(3):
            with at_hour(8):
                self.assertEqual(APIClient().get(self.URL, **self.hdr()).status_code, 200)
        self.assertEqual(sum("วันนี้ครบกำหนดคืน" in m.subject for m in mail.outbox), 1)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.smtp.EmailBackend", EMAIL_HOST="127.0.0.1",
                   EMAIL_PORT=1, EMAIL_TIMEOUT=2, EMAIL_SYNC=True)
class SyncEmailTests(TestCase):
    def test_sync_mode_logs_failure_without_thread(self):
        u = User.objects.create_user(username="u", email="u@x.ac.th", password="x")
        with mock.patch("rental.notifications.threading.Thread", side_effect=AssertionError("thread used")):
            with self.captureOnCommitCallbacks(execute=True):
                notifications.notify_password_reset(u, "https://x/reset")
        log = NotificationLog.objects.get()
        self.assertFalse(log.is_success)
        self.assertTrue(log.error_message)

    @override_settings(EMAIL_SYNC=False)
    def test_thread_mode_still_uses_thread(self):
        u = User.objects.create_user(username="u2", email="u2@x.ac.th", password="x")
        with mock.patch("rental.notifications.threading.Thread") as T:
            with self.captureOnCommitCallbacks(execute=True):
                notifications.notify_password_reset(u, "https://x/reset")
        T.assert_called_once()

    def test_bulk_welcome_sync_no_thread(self):
        u = User.objects.create_user(username="u3", email="u3@x.ac.th", password="x")
        with mock.patch("rental.notifications.threading.Thread", side_effect=AssertionError("thread used")):
            notifications.notify_accounts_created_background([u], "https://x")
        self.assertEqual(NotificationLog.objects.filter(user=u, is_success=False).count(), 1)
