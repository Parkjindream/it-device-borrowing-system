"""
ทดสอบ: ลิงก์ตั้งรหัสผ่าน (หน้า set/reset password) และการส่งลิงก์ซ้ำให้นักศึกษาที่ยังไม่ตั้งรหัสผ่าน
รันด้วย: python manage.py test rental.test_account_setup_links
"""
from datetime import datetime, timedelta
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from rental import jobs
from rental.models import NotificationLog, User

BASE = "https://app.example.com"
VALIDATE = "/api/auth/password-reset-validate/"
CONFIRM = "/api/auth/password-reset-confirm/"
NEW_PASSWORD = "Brand-New-Pass-9"


def pending_student(email, **kw):
    """นักศึกษาที่เจ้าหน้าที่เพิ่มให้ โดยยังไม่ตั้งรหัสผ่าน (เหมือน StudentCreateSerializer)"""
    u = User(username=email, email=email, first_name="สมชาย", role=User.Role.STUDENT, **kw)
    u.set_unusable_password()
    u.save()
    return u


def link_for(user):
    return {
        "uid": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": PasswordResetTokenGenerator().make_token(user),
    }


def at_hour(hour):
    d = timezone.localdate()
    return mock.patch(
        "django.utils.timezone.now",
        return_value=datetime(d.year, d.month, d.day, hour, 30, tzinfo=ZoneInfo("Asia/Bangkok")),
    )


class LinkValidationTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.user = pending_student("new@x.ac.th")

    def test_fresh_link_is_valid(self):
        r = self.api.post(VALIDATE, link_for(self.user), format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"valid": True})  # ไม่เปิดเผยข้อมูลผู้ใช้

    def test_link_dies_immediately_after_password_is_set(self):
        data = link_for(self.user)
        r = self.api.post(CONFIRM, {**data, "new_password": NEW_PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))

        # เปิดลิงก์เดิมอีกครั้ง: หน้าเว็บต้องรู้ทันทีว่าใช้ไม่ได้ และส่งรหัสผ่านซ้ำก็ต้องไม่ผ่าน
        again = self.api.post(VALIDATE, data, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertIn("ถูกใช้ไปแล้ว", again.data["detail"])
        r2 = self.api.post(CONFIRM, {**data, "new_password": "Another-Pass-77"}, format="json")
        self.assertEqual(r2.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))  # รหัสผ่านไม่ถูกเปลี่ยนซ้ำ

    def test_every_older_link_dies_once_password_is_set(self):
        first, second = link_for(self.user), link_for(self.user)
        self.assertEqual(self.api.post(VALIDATE, first, format="json").status_code, 200)  # ลิงก์เก่ายังไม่หมดอายุ = ใช้ได้
        self.api.post(CONFIRM, {**second, "new_password": NEW_PASSWORD}, format="json")
        self.assertEqual(self.api.post(VALIDATE, first, format="json").status_code, 400)
        self.assertEqual(self.api.post(VALIDATE, second, format="json").status_code, 400)

    def test_link_expires_after_24_hours(self):
        data = link_for(self.user)
        later = datetime.now() + timedelta(hours=25)
        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=later):
            self.assertEqual(self.api.post(VALIDATE, data, format="json").status_code, 400)
            r = self.api.post(CONFIRM, {**data, "new_password": NEW_PASSWORD}, format="json")
        self.assertEqual(r.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_link_still_valid_just_before_24_hours(self):
        data = link_for(self.user)
        later = datetime.now() + timedelta(hours=23)
        with mock.patch.object(PasswordResetTokenGenerator, "_now", return_value=later):
            self.assertEqual(self.api.post(VALIDATE, data, format="json").status_code, 200)

    def test_bad_or_missing_parts_are_rejected_not_500(self):
        good = link_for(self.user)
        bad_inputs = [
            {}, {"uid": good["uid"]}, {"token": good["token"]},
            {"uid": good["uid"], "token": "abc-123"},
            {"uid": "!!!", "token": good["token"]},
            {"uid": urlsafe_base64_encode(force_bytes(999999)), "token": good["token"]},
            {"uid": good["uid"], "token": 12345},
        ]
        for body in bad_inputs:
            r = self.api.post(VALIDATE, body, format="json")
            self.assertEqual(r.status_code, 400, body)

    def test_deactivated_account_cannot_use_link(self):
        data = link_for(self.user)
        self.user.is_active = False
        self.user.save()
        self.assertEqual(self.api.post(VALIDATE, data, format="json").status_code, 400)
        r = self.api.post(CONFIRM, {**data, "new_password": NEW_PASSWORD}, format="json")
        self.assertEqual(r.status_code, 400)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_validate_requires_no_login(self):
        self.assertEqual(APIClient().post(VALIDATE, link_for(self.user), format="json").status_code, 200)

    def test_forgot_password_link_also_dies_after_use(self):
        """ลิงก์จากปุ่ม 'ลืมรหัสผ่าน' (คนที่มีรหัสผ่านอยู่แล้ว) ก็ต้องใช้ได้ครั้งเดียวเหมือนกัน"""
        u = User.objects.create_user(username="old@x.ac.th", email="old@x.ac.th", password="Old-Pass-12345")
        data = link_for(u)
        self.assertEqual(self.api.post(VALIDATE, data, format="json").status_code, 200)
        self.api.post(CONFIRM, {**data, "new_password": NEW_PASSWORD}, format="json")
        self.assertEqual(self.api.post(VALIDATE, data, format="json").status_code, 400)

    def test_pending_student_can_request_a_new_link_via_forgot_password(self):
        """คนที่ยังไม่เคยตั้งรหัสผ่านกด 'ลืมรหัสผ่าน' เพื่อขอลิงก์ใหม่เองได้ และลิงก์ที่ได้ใช้งานได้"""
        r = self.api.post("/api/auth/password-reset/", {"email": self.user.email}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual([m.to[0] for m in mail.outbox], ["new@x.ac.th"])
        query = mail.outbox[0].body.split("/reset-password/?", 1)[1].split()[0]
        parts = dict(kv.split("=") for kv in query.split("&"))
        self.assertEqual(self.api.post(VALIDATE, parts, format="json").status_code, 200)
        done = self.api.post(CONFIRM, {**parts, "new_password": NEW_PASSWORD}, format="json")
        self.assertEqual(done.status_code, 200)
        self.assertEqual(self.api.post(VALIDATE, parts, format="json").status_code, 400)


@override_settings(FRONTEND_URL=BASE)
class ResendPendingSetupTests(TestCase):
    def setUp(self):
        self.p1 = pending_student("p1@x.ac.th")
        self.p2 = pending_student("p2@x.ac.th")

    def logs(self, user, trigger=NotificationLog.Trigger.ACCOUNT_CREATED, ok=True):
        return NotificationLog.objects.filter(user=user, trigger=trigger, is_success=ok)

    def test_sends_working_fresh_link_to_pending_students_only(self):
        has_pw = User.objects.create_user(username="ok@x.ac.th", email="ok@x.ac.th", password="Strong-Pass-123")
        staff = User(username="st@x.ac.th", email="st@x.ac.th", role=User.Role.STAFF)
        staff.set_unusable_password()
        staff.save()
        off = pending_student("off@x.ac.th")
        off.is_active = False
        off.save()

        self.assertEqual(jobs.resend_pending_account_setup(), 2)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["p1@x.ac.th", "p2@x.ac.th"])
        for u in (has_pw, staff, off):
            self.assertEqual(self.logs(u).count(), 0)
        self.assertEqual(self.logs(self.p1).count(), 1)

        body = next(m.body for m in mail.outbox if m.to == ["p1@x.ac.th"])
        self.assertIn(f"{BASE}/reset-password/?uid=", body)
        self.assertIn("24 ชั่วโมง", body)
        self.assertIn("ทุกวัน", body)  # บอกนักศึกษาว่าจะส่งซ้ำทุกวัน
        # ลิงก์ในอีเมลใช้งานได้จริง
        query = body.split("?", 1)[1].split()[0]
        parts = dict(kv.split("=") for kv in query.split("&"))
        r = APIClient().post(VALIDATE, parts, format="json")
        self.assertEqual(r.status_code, 200)

    def test_no_duplicates_within_a_day_even_if_run_twice(self):
        self.assertEqual(jobs.resend_pending_account_setup(), 2)
        self.assertEqual(jobs.resend_pending_account_setup(), 0)  # cron สองทางรันซ้ำในวันเดียวกัน
        self.assertEqual(len(mail.outbox), 2)

    def test_resends_again_the_next_day(self):
        jobs.resend_pending_account_setup()
        NotificationLog.objects.update(sent_at=timezone.now() - timedelta(hours=24))
        mail.outbox.clear()
        self.assertEqual(jobs.resend_pending_account_setup(), 2)
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn("เตือน", mail.outbox[0].subject)

    def test_keeps_resending_every_day_until_student_sets_password(self):
        for _ in range(3):
            self.assertEqual(jobs.resend_pending_account_setup(), 2)
            NotificationLog.objects.update(sent_at=timezone.now() - timedelta(hours=24))
        # p1 ตั้งรหัสผ่านแล้ว -> หยุดส่ง; p2 ยังไม่ตั้ง -> ส่งต่อ
        data = link_for(self.p1)
        APIClient().post(CONFIRM, {**data, "new_password": NEW_PASSWORD}, format="json")
        mail.outbox.clear()
        self.assertEqual(jobs.resend_pending_account_setup(), 1)
        self.assertEqual([m.to[0] for m in mail.outbox], ["p2@x.ac.th"])

    def test_failed_send_does_not_count_as_sent(self):
        NotificationLog.objects.create(
            user=self.p1, trigger=NotificationLog.Trigger.ACCOUNT_CREATED, email_to=self.p1.email,
            is_success=False, error_message="smtp down",
        )
        self.assertEqual(jobs.resend_pending_account_setup(), 2)

    def test_skips_someone_who_just_requested_a_link_themselves(self):
        NotificationLog.objects.create(
            user=self.p1, trigger=NotificationLog.Trigger.PASSWORD_RESET_REQUESTED, email_to=self.p1.email,
        )
        self.assertEqual(jobs.resend_pending_account_setup(), 1)
        self.assertEqual([m.to[0] for m in mail.outbox], ["p2@x.ac.th"])

    def test_batch_limit_serves_longest_waiting_first(self):
        p3 = pending_student("p3@x.ac.th")
        # p1 ได้ลิงก์เมื่อ 30 ชม. ก่อน, p2 เมื่อ 50 ชม. ก่อน, p3 ไม่เคยได้ -> ลำดับ p3, p2, p1
        for u, hours in ((self.p1, 30), (self.p2, 50)):
            log = NotificationLog.objects.create(
                user=u, trigger=NotificationLog.Trigger.ACCOUNT_CREATED, email_to=u.email)
            NotificationLog.objects.filter(pk=log.pk).update(sent_at=timezone.now() - timedelta(hours=hours))
        self.assertEqual(jobs.resend_pending_account_setup(limit=2), 2)
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["p2@x.ac.th", p3.email])
        mail.outbox.clear()
        self.assertEqual(jobs.resend_pending_account_setup(limit=2), 1)  # เหลือ p1 ในรอบถัดไป
        self.assertEqual(mail.outbox[0].to, ["p1@x.ac.th"])

    @override_settings(FRONTEND_URL="")
    def test_without_site_address_nothing_is_sent(self):
        self.assertEqual(jobs.resend_pending_account_setup(), 0)
        self.assertEqual(mail.outbox, [])
        self.assertEqual(jobs.resend_pending_account_setup(base_url="https://given.example"), 2)
        self.assertIn("https://given.example/reset-password/", mail.outbox[0].body)

    def test_one_failure_does_not_stop_the_rest(self):
        real = jobs.notify_account_created

        def flaky(user, base_url, reminder=False):
            if user.pk == self.p1.pk:
                raise RuntimeError("boom")
            return real(user, base_url, reminder=reminder)

        with mock.patch("rental.jobs.notify_account_created", side_effect=flaky):
            self.assertEqual(jobs.resend_pending_account_setup(), 1)
        self.assertEqual([m.to[0] for m in mail.outbox], ["p2@x.ac.th"])

    def test_daily_job_runs_resend_and_survives_its_failure(self):
        jobs.run_daily_due_date_checks()
        self.assertEqual(len(mail.outbox), 2)
        mail.outbox.clear()
        with mock.patch("rental.jobs.resend_pending_account_setup", side_effect=RuntimeError("boom")), \
             mock.patch("rental.jobs.cleanup_old_notification_logs") as cleanup:
            with self.assertLogs("rental.jobs", level="ERROR"):
                jobs.run_daily_due_date_checks()
        cleanup.assert_called_once()  # ขั้นเคลียร์ข้อมูลยังทำงานต่อ

    def test_existing_reminder_dedupe_is_not_disturbed(self):
        """ตัดอีเมลเตือนการยืมออกจากการนับ: สร้าง log ของอีเมลเตือนคืนของ ไม่ทำให้ข้ามการส่งลิงก์"""
        NotificationLog.objects.create(
            user=self.p1, trigger=NotificationLog.Trigger.REMINDER_DUE_TODAY, email_to=self.p1.email,
        )
        self.assertEqual(jobs.resend_pending_account_setup(), 2)


@override_settings(CRON_SECRET="s3cret-value", FRONTEND_URL=BASE)
class CronResendTests(TestCase):
    URL = "/api/cron/run-jobs/"
    HDR = {"HTTP_AUTHORIZATION": "Bearer s3cret-value"}

    def setUp(self):
        self.p1 = pending_student("p1@x.ac.th")

    def test_full_cron_run_sends_setup_links(self):
        with at_hour(8):
            r = APIClient().get(self.URL, **self.HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["jobs"]["daily_due_date_checks"], "ok")
        self.assertEqual([m.to[0] for m in mail.outbox], ["p1@x.ac.th"])
        self.assertIn(f"{BASE}/reset-password/?uid=", mail.outbox[0].body)

    def test_only_expire_run_does_not_send_setup_links(self):
        with at_hour(8):
            r = APIClient().get(self.URL + "?only=expire", **self.HDR)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(mail.outbox, [])

    def test_two_full_runs_same_day_send_once(self):
        with at_hour(8):
            APIClient().get(self.URL, **self.HDR)
            APIClient().get(self.URL, **self.HDR)
        self.assertEqual(len(mail.outbox), 1)
