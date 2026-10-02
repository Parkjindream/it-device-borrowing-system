"""
โมดูล E: ระบบแจ้งเตือนอีเมล

หลักการ: ทุกฟังก์ชันในไฟล์นี้ "ต้องไม่ทำให้ระบบล่ม" แม้อีเมลส่งไม่สำเร็จ
(เช่น SMTP ล่ม, ผู้ใช้ไม่มีอีเมล) — จับ exception เองแล้วบันทึกผลลัพธ์ลง
NotificationLog ไว้เสมอ เพื่อให้เจ้าหน้าที่ตรวจสอบย้อนหลังได้ว่าอีเมลไหนส่งไม่ผ่าน

จุดที่เรียกใช้ไฟล์นี้:
- services.create_booking()   -> notify_booking_confirmed
- services.confirm_return()   -> notify_return_success, notify_suspended (ถ้าโดนโทษ)
- jobs.cancel_expired_bookings() -> notify_auto_cancelled
- jobs.run_daily_due_date_checks() -> notify_reminder_due_soon / due_today / overdue
"""
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import NotificationLog, PenaltySettings


def _send(user, trigger, subject, message, booking=None):
    """ส่งอีเมล 1 ฉบับ + บันทึกผลลง NotificationLog เสมอไม่ว่าจะสำเร็จหรือไม่"""
    email_to = user.email
    is_success = True
    error_message = ""

    if not email_to:
        is_success = False
        error_message = "ผู้ใช้ไม่มีอีเมลในระบบ"
    else:
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email_to],
                fail_silently=False,
            )
        except Exception as exc:  # กันทุกกรณี SMTP ล่ม/ตั้งค่าอีเมลผิด ไม่ให้ทั้ง request ล่มตาม
            is_success = False
            error_message = str(exc)

    NotificationLog.objects.create(
        booking=booking,
        user=user,
        trigger=trigger,
        email_to=email_to or "",
        is_success=is_success,
        error_message=error_message,
    )
    return is_success


def notify_booking_confirmed(booking):
    equipment_name = booking.unit.equipment.name
    expires_local = timezone.localtime(booking.booking_expires_at)
    subject = f"ยืนยันการจองอุปกรณ์ '{equipment_name}' สำเร็จ"
    message = (
        f"คุณได้จองอุปกรณ์ '{equipment_name}' เรียบร้อยแล้ว\n"
        f"รหัสการจอง: {booking.booking_code}\n\n"
        f"กรุณามารับอุปกรณ์ที่เคาน์เตอร์ก่อนวันที่ {expires_local:%d/%m/%Y เวลา %H:%M น.}\n"
        f"หากไม่มารับภายในเวลาดังกล่าว ระบบจะยกเลิกการจองนี้ให้อัตโนมัติ\n\n"
        f"กำหนดคืน: {booking.requested_end_date:%d/%m/%Y}"
    )
    _send(booking.student, NotificationLog.Trigger.BOOKING_CONFIRMED, subject, message, booking=booking)


def notify_pickup_success(booking):
    equipment_name = booking.unit.equipment.name
    subject = f"รับอุปกรณ์ '{equipment_name}' เรียบร้อยแล้ว"
    message = (
        f"เจ้าหน้าที่ได้ส่งมอบอุปกรณ์ '{equipment_name}' (รหัสการจอง {booking.booking_code}) ให้คุณเรียบร้อยแล้ว\n"
        f"กรุณานำมาคืนภายในวันที่ {booking.requested_end_date:%d/%m/%Y}\n\n"
        f"ระบบจะส่งอีเมลเตือนให้อีกครั้งก่อนถึงกำหนดคืน"
    )
    _send(booking.student, NotificationLog.Trigger.PICKUP_SUCCESS, subject, message, booking=booking)


def notify_reminder_due_soon(booking):
    equipment_name = booking.unit.equipment.name
    subject = f"แจ้งเตือน: พรุ่งนี้ครบกำหนดคืน '{equipment_name}'"
    message = (
        f"อุปกรณ์ '{equipment_name}' (รหัสการจอง {booking.booking_code}) ของคุณ\n"
        f"จะครบกำหนดคืนในวันพรุ่งนี้ ({booking.requested_end_date:%d/%m/%Y})\n\n"
        f"กรุณานำมาคืนที่เคาน์เตอร์ตามกำหนด เพื่อไม่ให้บัญชีถูกพักสิทธิ์การจอง"
    )
    _send(booking.student, NotificationLog.Trigger.REMINDER_DUE_SOON, subject, message, booking=booking)


def notify_reminder_due_today(booking):
    equipment_name = booking.unit.equipment.name
    subject = f"แจ้งเตือน: วันนี้ครบกำหนดคืน '{equipment_name}'"
    message = (
        f"วันนี้เป็นวันครบกำหนดคืนอุปกรณ์ '{equipment_name}' (รหัสการจอง {booking.booking_code})\n\n"
        f"กรุณานำมาคืนที่เคาน์เตอร์ภายในวันนี้ เพื่อไม่ให้บัญชีถูกพักสิทธิ์การจองอุปกรณ์ใหม่"
    )
    _send(booking.student, NotificationLog.Trigger.REMINDER_DUE_TODAY, subject, message, booking=booking)


def notify_reminder_overdue(booking):
    equipment_name = booking.unit.equipment.name
    overdue_days = (timezone.localdate() - booking.requested_end_date).days
    rule = PenaltySettings.get_solo()
    subject = f"แจ้งเตือน: เกินกำหนดคืน '{equipment_name}' แล้ว {overdue_days} วัน"
    message = (
        f"อุปกรณ์ '{equipment_name}' (รหัสการจอง {booking.booking_code}) ของคุณ\n"
        f"เกินกำหนดคืนมาแล้ว {overdue_days} วัน (กำหนดคืน {booking.requested_end_date:%d/%m/%Y})\n\n"
        f"กรุณารีบนำมาคืนที่เคาน์เตอร์โดยเร็วที่สุด\n"
        f"ตามกติกาของวิทยาลัย หากคืนเกินกำหนด {rule.overdue_days_threshold} วันขึ้นไป "
        f"บัญชีของคุณจะถูกพักสิทธิ์การจองอุปกรณ์ใหม่ {rule.suspension_days} วัน "
        f"(ยังเข้าสู่ระบบและดูประวัติได้ตามปกติ)"
    )
    _send(booking.student, NotificationLog.Trigger.REMINDER_OVERDUE, subject, message, booking=booking)


def notify_return_success(booking):
    equipment_name = booking.unit.equipment.name
    subject = f"รับคืนอุปกรณ์ '{equipment_name}' เรียบร้อยแล้ว"
    message = (
        f"เจ้าหน้าที่ได้รับคืนอุปกรณ์ '{equipment_name}' (รหัสการจอง {booking.booking_code}) เรียบร้อยแล้ว\n"
        f"ขอบคุณที่ใช้บริการศูนย์ยืม-คืนอุปกรณ์ไอที"
    )
    _send(booking.student, NotificationLog.Trigger.RETURN_SUCCESS, subject, message, booking=booking)


def notify_suspended(student, booking=None):
    subject = "บัญชีของคุณถูกพักสิทธิ์การจองอุปกรณ์ชั่วคราว"
    until_text = (
        f"คุณจะกลับมาจองอุปกรณ์ใหม่ได้ตั้งแต่วันที่ {student.suspended_until:%d/%m/%Y}"
        if student.suspended_until else ""
    )
    message = (
        f"บัญชีของคุณถูกพักสิทธิ์การจองอุปกรณ์ใหม่ชั่วคราว\n"
        f"เหตุผล: {student.suspended_reason or 'คืนอุปกรณ์เกินกำหนด'}\n"
        f"{until_text}\n\n"
        f"คุณยังคงเข้าสู่ระบบและดูประวัติการยืมเดิมได้ตามปกติ "
        f"หากมีข้อสงสัยกรุณาติดต่อเจ้าหน้าที่ห้องโสตทัศนศึกษา"
    )
    _send(student, NotificationLog.Trigger.SUSPENDED, subject, message, booking=booking)


def notify_auto_cancelled(booking):
    equipment_name = booking.unit.equipment.name
    subject = f"การจอง '{equipment_name}' ถูกยกเลิกอัตโนมัติ"
    message = (
        f"การจองอุปกรณ์ '{equipment_name}' (รหัสการจอง {booking.booking_code}) ของคุณ\n"
        f"ถูกยกเลิกโดยอัตโนมัติ เนื่องจากไม่ได้มารับอุปกรณ์ภายในเวลาที่กำหนด\n\n"
        f"หากยังต้องการใช้งาน สามารถจองใหม่ได้ทันทีผ่านระบบ"
    )
    _send(booking.student, NotificationLog.Trigger.AUTO_CANCELLED, subject, message, booking=booking)
