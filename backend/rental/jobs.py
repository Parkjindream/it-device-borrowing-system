"""
งานที่รันอัตโนมัติตามตารางเวลา — เรียกใช้ผ่านคำสั่ง `python manage.py run_scheduler`
(ดูไฟล์ management/commands/run_scheduler.py) แทนการพึ่ง cron ของระบบปฏิบัติการ
เพื่อให้รันได้เหมือนกันทั้งบน Windows ตอนพัฒนา และใน container เดียวกันตอน deploy จริงด้วย Docker

- cancel_expired_bookings()   : เรียกทุกรอบสั้น ๆ (ค่าเริ่มต้นทุก 15 นาที) — จัดการกรณี "ไม่มารับของ" (no-show)
- run_daily_due_date_checks() : เรียกวันละครั้ง — ปลดพักสิทธิ์ที่ครบกำหนด, เปลี่ยนสถานะเกินกำหนด, ส่งอีเมลแจ้งเตือน (โมดูล E)

หมายเหตุ: ทั้งสองฟังก์ชันนี้ไม่ต้อง real-time ตามที่เอกสารกำหนด (ข้อ "แจ้งเตือนไม่ต้อง
real-time") ต่างจากจำนวนอุปกรณ์คงเหลือซึ่งคำนวณสดทุกครั้งที่ query อยู่แล้วในโมเดล
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Booking, EquipmentUnit, NotificationLog, User
from .notifications import (
    notify_auto_cancelled,
    notify_reminder_due_soon,
    notify_reminder_due_today,
    notify_reminder_overdue,
)


def cancel_expired_bookings():
    """
    โมดูล C: จัดการ 'ไม่มารับของ' (no-show)
    ถ้านักศึกษาไม่มารับอุปกรณ์ภายในเวลาที่กำหนด (booking_expires_at) ให้ระบบ
    ยกเลิกการจองอัตโนมัติ คืนอุปกรณ์ชิ้นนั้นกลับเป็น 'ว่าง' และแจ้งอีเมลให้ทราบ
    """
    now = timezone.now()

    # ดึงแค่ ID มาก่อน เพื่อไม่ต้องถือ lock ยาว ๆ ระหว่างวนลูปหลายรายการ
    expired_ids = list(
        Booking.objects.filter(
            status=Booking.Status.AWAITING_PICKUP,
            booking_expires_at__lt=now,
        ).values_list("id", flat=True)
    )

    for booking_id in expired_ids:
        cancelled_booking = None
        with transaction.atomic():
            booking = Booking.objects.select_for_update().select_related(
                "student", "unit", "unit__equipment"
            ).get(pk=booking_id)

            # เช็คซ้ำอีกครั้งกันกรณีเจ้าหน้าที่เพิ่งกดยืนยันรับของไปพอดีก่อน job นี้จะรันถึง
            if booking.status != Booking.Status.AWAITING_PICKUP:
                continue

            unit = EquipmentUnit.objects.select_for_update().get(pk=booking.unit_id)
            unit.status = EquipmentUnit.Status.AVAILABLE
            unit.save(update_fields=["status", "updated_at"])

            booking.status = Booking.Status.CANCELLED
            booking.cancel_reason = Booking.CancelReason.NO_SHOW
            booking.cancelled_at = timezone.now()
            booking.save(update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"])
            cancelled_booking = booking

        # ส่งอีเมลหลัง transaction ของรายการนี้ commit แล้วเท่านั้น
        if cancelled_booking is not None:
            notify_auto_cancelled(cancelled_booking)


def lift_expired_suspensions():
    """
    โมดูล F: ปลดพักสิทธิ์อัตโนมัติเมื่อครบกำหนด (suspended_until ถึงแล้ว)
    คืนค่าจำนวนบัญชีที่ปลดให้
    """
    today = timezone.localdate()
    return User.objects.filter(
        is_suspended=True, suspended_until__isnull=False, suspended_until__lte=today,
    ).update(is_suspended=False, suspended_until=None, suspended_reason="")


def run_daily_due_date_checks():
    """
    โมดูล D + E + F: ทำงานวันละครั้ง แบ่งเป็นขั้นย่อย

    0. ปลดพักสิทธิ์ที่ครบกำหนดแล้ว
    1. เตือนล่วงหน้า 1 วันก่อนครบกำหนดคืน
    2. เตือนในวันที่ครบกำหนดคืนพอดี
    3. เปลี่ยนสถานะรายการที่เลยกำหนดคืนแล้วเป็น "เกินกำหนด"
    4. เตือนซ้ำรายวันสำหรับรายการที่ "เกินกำหนด" อยู่แล้ว
    5. เคลียร์ประวัติอีเมล/ประวัติการยืมที่จบแล้วและเก่าเกินกำหนดเก็บ (กันฐานข้อมูลโตไม่จำกัด)

    ใช้ Booking.last_reminder_sent_date กันส่งอีเมลซ้ำมากกว่า 1 ครั้งต่อวัน
    ต่อ 1 รายการจอง แม้ job จะถูกรันซ้ำในวันเดียวกันด้วยเหตุผลใดก็ตาม
    """
    today = timezone.localdate()
    tomorrow = today + timedelta(days=1)

    lift_expired_suspensions()

    base_qs = Booking.objects.select_related("student", "unit", "unit__equipment")

    # --- 1) เตือนล่วงหน้า 1 วัน ---
    due_soon_qs = base_qs.filter(
        status=Booking.Status.BORROWED, requested_end_date=tomorrow,
    ).exclude(last_reminder_sent_date=today)
    for booking in due_soon_qs:
        notify_reminder_due_soon(booking)
        booking.last_reminder_sent_date = today
        booking.save(update_fields=["last_reminder_sent_date"])

    # --- 2) เตือนถึงวันครบกำหนดพอดี ---
    due_today_qs = base_qs.filter(
        status=Booking.Status.BORROWED, requested_end_date=today,
    ).exclude(last_reminder_sent_date=today)
    for booking in due_today_qs:
        notify_reminder_due_today(booking)
        booking.last_reminder_sent_date = today
        booking.save(update_fields=["last_reminder_sent_date"])

    # --- 3) เปลี่ยนสถานะเป็น "เกินกำหนด" ---
    Booking.objects.filter(
        status=Booking.Status.BORROWED, requested_end_date__lt=today,
    ).update(status=Booking.Status.OVERDUE, updated_at=timezone.now())

    # --- 4) เตือนซ้ำรายวันสำหรับรายการที่เกินกำหนดอยู่แล้ว ---
    overdue_qs = base_qs.filter(
        status=Booking.Status.OVERDUE,
    ).exclude(last_reminder_sent_date=today)
    for booking in overdue_qs:
        notify_reminder_overdue(booking)
        booking.last_reminder_sent_date = today
        booking.save(update_fields=["last_reminder_sent_date"])

    # --- 5) เคลียร์ข้อมูลเก่าอัตโนมัติ กันฐานข้อมูลโตไม่จำกัด ---
    cleanup_old_notification_logs()
    cleanup_old_booking_history()


def cleanup_old_notification_logs(retention_days=None):
    """
    ลบ NotificationLog ที่เก่ากว่า retention_days วัน (ค่าเริ่มต้นจาก
    settings.NOTIFICATION_LOG_RETENTION_DAYS) — ประวัติอีเมลไม่ใช่ข้อมูลสำคัญระยะยาว
    แค่ไว้เช็คว่าส่งสำเร็จหรือไม่ จึงเก็บสั้น ๆ พอ คืนค่าจำนวนแถวที่ลบไป
    """
    days = retention_days if retention_days is not None else settings.NOTIFICATION_LOG_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    deleted_count, _ = NotificationLog.objects.filter(sent_at__lt=cutoff).delete()
    return deleted_count


def cleanup_old_booking_history(retention_days=None):
    """
    ลบ Booking ที่ "จบแล้ว" (คืนแล้ว/ยกเลิก) และเก่ากว่า retention_days วัน
    (ค่าเริ่มต้นจาก settings.BOOKING_HISTORY_RETENTION_DAYS)

    ไม่แตะรายการที่ยังไม่จบ (รอรับของ/กำลังยืม/เกินกำหนด) ไม่ว่าจะเก่าแค่ไหนก็ตาม
    เพื่อความปลอดภัย — เผื่อกรณีข้อมูลผิดปกติที่ยังไม่ถูกจัดการ จะไม่มีวันถูกลบทิ้งไปเฉย ๆ
    คืนค่าจำนวนแถวที่ลบไป
    """
    days = retention_days if retention_days is not None else settings.BOOKING_HISTORY_RETENTION_DAYS
    cutoff = timezone.now() - timedelta(days=days)
    deleted_count, _ = Booking.objects.filter(
        status__in=[Booking.Status.RETURNED, Booking.Status.CANCELLED],
        updated_at__lt=cutoff,
    ).delete()
    return deleted_count