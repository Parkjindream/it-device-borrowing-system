"""
Business logic ของโมดูล C (การจอง) และ D (รับ-คืน) + F (บทลงโทษ)

หลักการสำคัญที่ยึดตลอดไฟล์นี้:
1. ทุกจุดที่เปลี่ยนสถานะ EquipmentUnit หรือ Booking ต้องอยู่ใน
   transaction.atomic() + select_for_update() เสมอ กัน race condition
   เวลามีคนหลายคนกดพร้อมกัน (ดูรายละเอียดเหตุผลใน SCHEMA_NOTES.md)
2. การสแกน QR ที่ฝั่ง view ทำหน้าที่แค่ "ดึงข้อมูลมาแสดง" เท่านั้น
   ฟังก์ชัน confirm_pickup / confirm_return จะถูกเรียกก็ต่อเมื่อ
   เจ้าหน้าที่กดปุ่มยืนยันเองในหน้าจอเท่านั้น ไม่มีจุดไหนเรียกอัตโนมัติจากการสแกน
3. บทลงโทษ (โมดูล F) ถูกคำนวณและใส่ตรงจุด confirm_return ทันที
   เพราะเป็นจุดเดียวที่รู้ "วันที่คืนจริง" เทียบกับ "วันครบกำหนด"
4. อีเมลแจ้งเตือนส่งหลัง transaction commit แล้วเท่านั้น (ไม่ถือ DB lock ระหว่างส่งเมล)
"""
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Booking, Equipment, EquipmentUnit, PenaltySettings, User
from .notifications import (
    notify_booking_confirmed,
    notify_cancelled_by_student,
    notify_pickup_success,
    notify_return_success,
    notify_suspended,
)


class BookingError(Exception):
    """ข้อผิดพลาดทางธุรกิจ (ไม่ใช่ bug) เช่น ของหมด, ยกเลิกไม่ได้ ฯลฯ
    view จะจับ exception นี้แล้วแปลงเป็น HTTP 400 พร้อมข้อความที่อ่านรู้เรื่อง"""


def compute_pickup_deadline(start_date, expire_hours):
    """
    เวลาหมดอายุการจอง (ต้องมารับก่อนเวลานี้)

    - จองสำหรับ "วันนี้"      -> นับจากตอนนี้ + expire_hours
    - จองล่วงหน้า (วันเริ่มยืมอยู่ในอนาคต) -> นับจาก 00:00 ของวันเริ่มยืม + expire_hours
      (ถ้านับจากตอนกดจอง การจองล่วงหน้าจะถูกยกเลิกอัตโนมัติก่อนถึงวันยืมจริง)
    """
    tz = timezone.get_current_timezone()
    start_of_start_day = timezone.make_aware(datetime.combine(start_date, time.min), tz)
    base = max(timezone.now(), start_of_start_day)
    return base + timedelta(hours=expire_hours)


def create_booking(student, equipment_id, start_date, end_date):
    """โมดูล C ขั้นตอนที่ 1-2: นักศึกษาเลือกอุปกรณ์ + ยืนยันการจอง"""

    if not student.can_make_new_booking():
        raise BookingError("บัญชีของคุณถูกพักสิทธิ์การจองชั่วคราว ไม่สามารถจองอุปกรณ์ใหม่ได้")

    today = timezone.localdate()
    if start_date < today:
        raise BookingError("วันเริ่มยืมต้องไม่ใช่วันที่ผ่านมาแล้ว")
    if end_date < start_date:
        raise BookingError("วันครบกำหนดคืนต้องไม่ก่อนวันเริ่มยืม")
    max_advance = settings.DEFAULT_MAX_ADVANCE_DAYS
    if (start_date - today).days > max_advance:
        raise BookingError(f"จองล่วงหน้าได้ไม่เกิน {max_advance} วัน")

    with transaction.atomic():
        # ล็อกแถวนักศึกษาก่อน: กันกดจองหลายอุปกรณ์พร้อมกันแล้วหลุดกฎ "1 คน 1 เครื่อง"
        User.objects.select_for_update().get(pk=student.pk)

        try:
            # ล็อกแถว equipment ไว้ก่อน: กันเจ้าหน้าที่ปิดใช้งานพร้อมกับตอนจอง และ
            # ทำให้การเช็ค "จองรุ่นเดียวกันซ้อน" ด้านล่างเชื่อถือได้ (คำขอของนักศึกษาคนเดียวกันเข้าคิวทีละอัน)
            equipment = Equipment.objects.select_for_update().get(pk=equipment_id, is_active=True)
        except Equipment.DoesNotExist:
            raise BookingError("ไม่พบอุปกรณ์นี้ หรือถูกปิดใช้งานแล้ว")

        # นับรวมทั้งวันเริ่มและวันคืน เช่น ยืมได้สูงสุด 3 วัน: เริ่มวันที่ 10 คืนได้ไม่เกินวันที่ 12
        if (end_date - start_date).days + 1 > equipment.max_borrow_days:
            raise BookingError(f"อุปกรณ์นี้ยืมได้สูงสุด {equipment.max_borrow_days} วันต่อครั้ง")

        # กติกา: นักศึกษา 1 คน มีรายการที่ยังไม่จบได้แค่ 1 รายการ (รวมทุกรุ่นอุปกรณ์)
        # จนกว่าจะคืนของชิ้นเดิมหรือยกเลิกการจอง จึงจะจองชิ้นต่อไปได้
        active_booking = Booking.objects.filter(
            student=student,
            status__in=[Booking.Status.AWAITING_PICKUP, Booking.Status.BORROWED, Booking.Status.OVERDUE],
        ).select_related("unit__equipment").first()
        if active_booking is not None:
            raise BookingError(
                f"คุณมีรายการ '{active_booking.unit.equipment.name}' ค้างอยู่ "
                f"(รหัส {active_booking.booking_code}) — 1 คนยืมได้ครั้งละ 1 เครื่อง "
                f"กรุณาคืนของหรือยกเลิกการจองก่อน จึงจะจองชิ้นใหม่ได้"
            )

        # *** จุดกัน race condition ที่สำคัญที่สุดของทั้งระบบ ***
        unit = (
            EquipmentUnit.objects
            .select_for_update(skip_locked=True)
            .filter(equipment=equipment, status=EquipmentUnit.Status.AVAILABLE)
            .first()
        )
        if unit is None:
            raise BookingError("อุปกรณ์นี้ถูกจองครบแล้วในขณะนี้ กรุณาลองใหม่ภายหลัง")

        unit.status = EquipmentUnit.Status.RESERVED
        unit.save(update_fields=["status", "updated_at"])

        penalty_settings = PenaltySettings.get_solo()
        booking = Booking.objects.create(
            student=student,
            unit=unit,
            requested_start_date=start_date,
            requested_end_date=end_date,
            booking_expires_at=compute_pickup_deadline(start_date, penalty_settings.booking_expire_hours),
        )

    notify_booking_confirmed(booking)
    return booking


def cancel_booking(booking):
    """โมดูล C: นักศึกษายกเลิกการจองด้วยตัวเอง — ทำได้เฉพาะตอนยัง 'รอรับของ' เท่านั้น"""

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)

        if booking.status != Booking.Status.AWAITING_PICKUP:
            raise BookingError("ยกเลิกได้เฉพาะรายการที่ยังไม่มารับของเท่านั้น")

        unit = EquipmentUnit.objects.select_for_update().get(pk=booking.unit_id)
        unit.status = EquipmentUnit.Status.AVAILABLE
        unit.save(update_fields=["status", "updated_at"])

        booking.status = Booking.Status.CANCELLED
        booking.cancel_reason = Booking.CancelReason.BY_STUDENT
        booking.cancelled_at = timezone.now()
        booking.save(update_fields=["status", "cancel_reason", "cancelled_at", "updated_at"])

    # แจ้งนักศึกษาทางอีเมลว่ายกเลิกเรียบร้อยแล้ว (ส่งหลัง commit)
    notify_cancelled_by_student(booking)
    return booking


def confirm_pickup(booking, staff_user, condition_note=""):
    """
    โมดูล D ขั้นตอนที่ 3: เจ้าหน้าที่ยืนยันการส่งมอบอุปกรณ์
    ต้องถูกเรียกจากการ "กดปุ่มยืนยัน" ของเจ้าหน้าที่เท่านั้น (ไม่ใช่จากการสแกน QR)
    """

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)

        if booking.status != Booking.Status.AWAITING_PICKUP:
            raise BookingError("รายการนี้ไม่ได้อยู่ในสถานะ 'รอรับของ' แล้ว")

        unit = EquipmentUnit.objects.select_for_update().get(pk=booking.unit_id)
        if unit.status != EquipmentUnit.Status.RESERVED:
            raise BookingError("สถานะอุปกรณ์ไม่ตรงกับที่คาดไว้ กรุณาตรวจสอบก่อนส่งมอบ")

        unit.status = EquipmentUnit.Status.BORROWED
        unit.save(update_fields=["status", "updated_at"])

        booking.status = Booking.Status.BORROWED
        booking.picked_up_at = timezone.now()
        booking.pickup_condition_note = condition_note
        booking.confirmed_by_pickup = staff_user
        booking.save(update_fields=[
            "status", "picked_up_at", "pickup_condition_note", "confirmed_by_pickup", "updated_at",
        ])

    notify_pickup_success(booking)
    return booking


def confirm_return(booking, staff_user, condition_note="", is_damaged=False):
    """
    โมดูล D ขั้นตอนที่ 4: เจ้าหน้าที่ยืนยันการรับคืนอุปกรณ์
    + คำนวณและใส่บทลงโทษ (โมดูล F) ทันทีถ้าคืนเกินกำหนดเกินเกณฑ์ที่ตั้งไว้
    """

    with transaction.atomic():
        booking = Booking.objects.select_for_update().get(pk=booking.pk)

        if booking.status not in (Booking.Status.BORROWED, Booking.Status.OVERDUE):
            raise BookingError("รายการนี้ไม่ได้อยู่ในสถานะ 'กำลังยืม' หรือ 'เกินกำหนด'")

        unit = EquipmentUnit.objects.select_for_update().select_related("equipment").get(pk=booking.unit_id)
        unit.status = EquipmentUnit.Status.DISABLED if is_damaged else EquipmentUnit.Status.AVAILABLE
        if condition_note:
            unit.condition_note = condition_note
        unit.save(update_fields=["status", "condition_note", "updated_at"])

        today = timezone.localdate()
        overdue_days = max((today - booking.requested_end_date).days, 0)
        penalty_settings = PenaltySettings.get_solo()
        should_penalize = overdue_days >= penalty_settings.overdue_days_threshold

        booking.status = Booking.Status.RETURNED
        booking.returned_at = timezone.now()
        booking.return_condition_note = condition_note
        booking.confirmed_by_return = staff_user
        booking.overdue_days_at_return = overdue_days
        booking.penalty_applied = should_penalize
        booking.save(update_fields=[
            "status", "returned_at", "return_condition_note", "confirmed_by_return",
            "overdue_days_at_return", "penalty_applied", "updated_at",
        ])

        if should_penalize:
            student = booking.student
            new_until = today + timedelta(days=penalty_settings.suspension_days)
            # ถ้าเคยถูกพักสิทธิ์ค้างอยู่แล้ว ให้ใช้วันที่ไกลกว่า (ไม่ตัดโทษเดิมให้สั้นลง)
            if student.is_suspended and student.suspended_until and student.suspended_until > new_until:
                new_until = student.suspended_until
            student.is_suspended = True
            student.suspended_until = new_until
            student.suspended_reason = (
                f"คืน '{unit.equipment.name}' เกินกำหนด {overdue_days} วัน "
                f"(รหัสการจอง {booking.booking_code})"
            )
            student.save(update_fields=["is_suspended", "suspended_until", "suspended_reason"])

    notify_return_success(booking, is_damaged=is_damaged)
    if should_penalize:
        notify_suspended(booking.student, booking=booking)

    return booking


def unsuspend_student(student):
    """โมดูล F: เจ้าหน้าที่ปลดล็อกบัญชีก่อนกำหนดได้ในกรณีพิเศษ"""
    student.is_suspended = False
    student.suspended_until = None
    student.suspended_reason = ""
    student.save(update_fields=["is_suspended", "suspended_until", "suspended_reason"])
    return student