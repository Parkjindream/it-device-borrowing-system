"""
โมเดลหลักของระบบยืม-คืนอุปกรณ์ไอที

3 สถานะหลักของระบบถูกออกแบบดังนี้:
1. สถานะอุปกรณ์  -> EquipmentUnit.status (นับจำนวนคงเหลือ = COUNT(status='available'))
2. สถานะการจอง   -> Booking.status
3. สถานะบัญชีผู้ใช้ -> User.is_suspended / suspended_until

หลักการสำคัญ: ทุกจุดที่เปลี่ยนสถานะ EquipmentUnit ต้องทำภายใน
transaction.atomic() + select_for_update() เพื่อกัน race condition
(ดูตัวอย่างการใช้งานจริงใน SCHEMA_NOTES.md และ services.py ในขั้นต่อไป)
"""
import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models
from django.utils import timezone


# ---------------------------------------------------------------------------
# โมดูล A: บัญชีผู้ใช้ (Authentication)
# ---------------------------------------------------------------------------
class UserManager(DjangoUserManager):
    """
    ผู้ที่สร้างด้วยคำสั่ง `createsuperuser` ต้องเป็น "เจ้าหน้าที่" (role=staff) เสมอ
    ไม่เช่นนั้นจะล็อกอินเข้าหน้าเว็บในฐานะนักศึกษา ทั้งที่ตั้งใจสร้างเป็นแอดมิน
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "staff")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    """
    ผู้ใช้ระบบ มี 2 บทบาท: นักศึกษา (student) / เจ้าหน้าที่ (staff)

    สถานะบัญชี (ข้อ 3.3 ในเอกสาร):
    - is_suspended=False  -> "ปกติ" จองได้
    - is_suspended=True   -> "ถูกพักสิทธิ์ชั่วคราว" ห้ามจองของใหม่เท่านั้น
      (ไม่กระทบ login / ดูประวัติ ซึ่งเช็คแค่ is_active ของ Django ตามปกติ)
    """

    class Role(models.TextChoices):
        STUDENT = "student", "นักศึกษา"
        STAFF = "staff", "เจ้าหน้าที่"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)
    student_id = models.CharField(
        "รหัสนักศึกษา", max_length=20, blank=True, null=True, unique=True
    )

    # --- สถานะบัญชี (โมดูล F: บทลงโทษ) ---
    is_suspended = models.BooleanField("ถูกพักสิทธิ์ชั่วคราว", default=False)
    suspended_until = models.DateField(
        "พักสิทธิ์ถึงวันที่", null=True, blank=True
    )
    suspended_reason = models.CharField(
        "เหตุผลที่พักสิทธิ์", max_length=255, blank=True
    )

    objects = UserManager()

    def can_make_new_booking(self) -> bool:
        """
        เช็คว่านักศึกษาจองของใหม่ได้หรือไม่ (ข้อ 4 ขั้นตอนที่ 1.2)

        suspended_until คือ "วันที่กลับมาจองได้อีกครั้ง" (พักสิทธิ์ 2 วัน จากวันที่ 28
        -> พัก 28,29 แล้วจองได้ตั้งแต่วันที่ 30) เช็คตรงนี้เสมอ ไม่พึ่งแค่ flag is_suspended
        เพราะ scheduled job อาจยังไม่ทันรันปลดสิทธิ์ให้
        """
        if not self.is_suspended:
            return True
        if self.suspended_until and self.suspended_until <= timezone.localdate():
            return True
        return False

    @property
    def is_currently_suspended(self) -> bool:
        """สถานะพักสิทธิ์ 'จริง ณ ตอนนี้' (ใช้แสดงผลบนหน้าเว็บ แทน is_suspended ดิบ ๆ)"""
        return not self.can_make_new_booking()

    def __str__(self):
        return f"{self.get_full_name() or self.username} ({self.get_role_display()})"


# ---------------------------------------------------------------------------
# โมดูล B: คลังอุปกรณ์ (Inventory Management)
# ---------------------------------------------------------------------------
class EquipmentCategory(models.Model):
    """หมวดหมู่อุปกรณ์ เช่น โน้ตบุ๊ก, กล้อง, ไมโครโฟน — ใช้สำหรับค้นหา/กรอง"""

    name = models.CharField("ชื่อหมวดหมู่", max_length=100, unique=True)

    class Meta:
        verbose_name = "หมวดหมู่อุปกรณ์"
        verbose_name_plural = "หมวดหมู่อุปกรณ์"

    def __str__(self):
        return self.name


class Equipment(models.Model):
    """
    'รุ่น/ประเภท' ของอุปกรณ์ เช่น 'โน้ตบุ๊ก Dell Latitude 5420'
    จำนวนคงเหลือของ Equipment ตัวนี้ = จำนวน EquipmentUnit ที่ status='available'
    (คำนวณสด ไม่เก็บเป็นตัวเลขนิ่ง เพื่อไม่ให้ข้อมูลไม่ตรงกัน)
    """

    category = models.ForeignKey(
        EquipmentCategory, on_delete=models.PROTECT, related_name="equipment_list"
    )
    name = models.CharField("ชื่ออุปกรณ์", max_length=200)
    description = models.TextField("รายละเอียด", blank=True)
    image = models.ImageField("รูปภาพ", upload_to="equipment/", blank=True, null=True)
    max_borrow_days = models.PositiveSmallIntegerField(
        "จำนวนวันยืมสูงสุดต่อครั้ง",
        default=settings.DEFAULT_MAX_BORROW_DAYS,
    )
    is_active = models.BooleanField("แสดงในรายการยืม", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "อุปกรณ์ (รุ่น)"
        verbose_name_plural = "อุปกรณ์ (รุ่น)"

    def __str__(self):
        return self.name

    # หมายเหตุ: ถ้า queryset ทำ annotate(_total_units, _available_units) มาแล้ว
    # (ดู views.equipment_with_counts) จะใช้ค่านั้นเลย ไม่ต้อง query ซ้ำทีละรุ่น
    @property
    def total_units(self) -> int:
        if hasattr(self, "_total_units"):
            return self._total_units
        return self.units.exclude(status=EquipmentUnit.Status.DISABLED).count()

    @property
    def available_units(self) -> int:
        if hasattr(self, "_available_units"):
            return self._available_units
        return self.units.filter(status=EquipmentUnit.Status.AVAILABLE).count()

    @property
    def is_out_of_stock(self) -> bool:
        return self.available_units == 0


class EquipmentUnit(models.Model):
    """
    อุปกรณ์ 'ชิ้นจริง' 1 ชิ้น (มี serial number) — สถานะย่อยตามข้อ 3.1:
    ว่าง -> ถูกจอง -> ถูกยืมอยู่ -> (กลับ) ว่าง | หรือ ปิดใช้งาน (ชำรุด/ส่งซ่อม)
    """

    class Status(models.TextChoices):
        AVAILABLE = "available", "ว่าง"
        RESERVED = "reserved", "ถูกจอง"
        BORROWED = "borrowed", "ถูกยืมอยู่"
        DISABLED = "disabled", "ปิดใช้งาน"

    equipment = models.ForeignKey(
        Equipment, on_delete=models.CASCADE, related_name="units"
    )
    serial_number = models.CharField("หมายเลขเครื่อง/ทรัพย์สิน", max_length=100, unique=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True
    )
    condition_note = models.TextField(
        "หมายเหตุสภาพอุปกรณ์ (ล่าสุด)", blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "อุปกรณ์ (ชิ้น)"
        verbose_name_plural = "อุปกรณ์ (ชิ้น)"

    def __str__(self):
        return f"{self.equipment.name} - {self.serial_number} [{self.get_status_display()}]"


# ---------------------------------------------------------------------------
# โมดูล F: ระบบบทลงโทษ (ตั้งค่าได้ - ปรับผ่านแอดมิน)
# ---------------------------------------------------------------------------
class PenaltySettings(models.Model):
    """
    ค่าตั้งต้นของระบบ (Singleton — ควรมีแถวเดียวในระบบ)
    ปรับได้โดยเจ้าหน้าที่ผ่านหน้าแอดมิน ไม่ต้องแก้โค้ด
    """

    overdue_days_threshold = models.PositiveSmallIntegerField(
        "เกินกำหนดตั้งแต่ (วัน) ถึงจะได้รับบทลงโทษ",
        default=settings.DEFAULT_OVERDUE_DAYS_THRESHOLD,
    )
    suspension_days = models.PositiveSmallIntegerField(
        "จำนวนวันพักสิทธิ์", default=settings.DEFAULT_SUSPENSION_DAYS
    )
    booking_expire_hours = models.PositiveSmallIntegerField(
        "เวลาหมดอายุการจองก่อนมารับ (ชั่วโมง)",
        default=settings.DEFAULT_BOOKING_EXPIRE_HOURS,
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ตั้งค่าระบบบทลงโทษ"
        verbose_name_plural = "ตั้งค่าระบบบทลงโทษ"

    @classmethod
    def get_solo(cls) -> "PenaltySettings":
        """ดึงค่าตั้งค่าแถวเดียว สร้างให้อัตโนมัติถ้ายังไม่มี"""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return "ตั้งค่าระบบบทลงโทษ (ค่าปัจจุบัน)"


# ---------------------------------------------------------------------------
# โมดูล C/D: การจอง + การส่งมอบ/รับคืน
# ---------------------------------------------------------------------------
def generate_booking_code() -> str:
    return f"BK-{uuid.uuid4().hex[:10].upper()}"


class Booking(models.Model):
    """
    1 แถว = 1 การยืม 1 ชิ้นอุปกรณ์ (unit) โดย 1 นักศึกษา

    สถานะ (ข้อ 3.2):
    รอรับของ -> กำลังยืม -> คืนแล้ว (ปิดเคส)
             \\-> เกินกำหนด (ระหว่างกำลังยืมแต่เลยกำหนดคืน)
             \\-> ยกเลิก (นักศึกษายกเลิกเอง หรือระบบยกเลิกอัตโนมัติกรณีไม่มารับ)
    """

    class Status(models.TextChoices):
        AWAITING_PICKUP = "awaiting_pickup", "รอรับของ"
        BORROWED = "borrowed", "กำลังยืม"
        OVERDUE = "overdue", "เกินกำหนด"
        RETURNED = "returned", "คืนแล้ว"
        CANCELLED = "cancelled", "ยกเลิก"

    class CancelReason(models.TextChoices):
        BY_STUDENT = "by_student", "ยกเลิกโดยนักศึกษา"
        NO_SHOW = "no_show", "ระบบยกเลิกอัตโนมัติ (ไม่มารับตามเวลา)"

    booking_code = models.CharField(
        max_length=20, unique=True, default=generate_booking_code, editable=False
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings"
    )
    unit = models.ForeignKey(
        EquipmentUnit, on_delete=models.PROTECT, related_name="bookings"
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.AWAITING_PICKUP, db_index=True
    )

    # --- ช่วงเวลาที่นักศึกษาต้องการยืม (ตั้งแต่ตอนจอง) ---
    requested_start_date = models.DateField("วันที่เริ่มยืม")
    requested_end_date = models.DateField("วันครบกำหนดคืน")

    # --- ควบคุมขั้นตอนที่ 1: ต้องมารับก่อนเวลานี้ ไม่งั้นระบบยกเลิกอัตโนมัติ ---
    booking_expires_at = models.DateTimeField("หมดอายุการจอง (ต้องมารับก่อน)")

    # --- ขั้นตอนที่ 2: การรับอุปกรณ์ (เจ้าหน้าที่ยืนยันเท่านั้น) ---
    picked_up_at = models.DateTimeField("เวลารับอุปกรณ์จริง", null=True, blank=True)
    pickup_condition_note = models.TextField("สภาพอุปกรณ์ตอนส่งมอบ", blank=True)
    confirmed_by_pickup = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_confirmed_pickup",
        limit_choices_to={"role": User.Role.STAFF},
    )

    # --- ขั้นตอนที่ 4: การคืนอุปกรณ์ ---
    returned_at = models.DateTimeField("เวลาคืนอุปกรณ์จริง", null=True, blank=True)
    return_condition_note = models.TextField("สภาพอุปกรณ์ตอนคืน", blank=True)
    confirmed_by_return = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bookings_confirmed_return",
        limit_choices_to={"role": User.Role.STAFF},
    )

    # --- บทลงโทษที่เกิดจาก booking นี้ (ถ้ามี) ---
    overdue_days_at_return = models.PositiveSmallIntegerField(
        "จำนวนวันที่คืนเกินกำหนด", default=0
    )
    penalty_applied = models.BooleanField("โดนบทลงโทษหรือไม่", default=False)

    # --- การยกเลิก ---
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(
        max_length=20, choices=CancelReason.choices, blank=True
    )

    # --- กันส่งอีเมลแจ้งเตือนซ้ำในวันเดียวกัน (scheduled job รันวันละครั้ง) ---
    last_reminder_sent_date = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "การจอง/ยืม"
        verbose_name_plural = "การจอง/ยืม"
        indexes = [
            models.Index(fields=["status", "requested_end_date"]),
            models.Index(fields=["status", "booking_expires_at"]),
        ]

    def __str__(self):
        return f"{self.booking_code} - {self.student} - {self.unit}"


# ---------------------------------------------------------------------------
# โมดูล E: ระบบแจ้งเตือน (log การส่งอีเมลทุกครั้ง เพื่อตรวจสอบย้อนหลังได้)
# ---------------------------------------------------------------------------
class NotificationLog(models.Model):
    class Trigger(models.TextChoices):
        BOOKING_CONFIRMED = "booking_confirmed", "จองสำเร็จ"
        PICKUP_SUCCESS = "pickup_success", "รับของสำเร็จ"
        PASSWORD_RESET_REQUESTED = "password_reset_requested", "ขอลิงก์ตั้งรหัสผ่านใหม่"
        REMINDER_DUE_SOON = "reminder_due_soon", "ใกล้ครบกำหนด (เหลือ 1 วัน)"
        REMINDER_DUE_TODAY = "reminder_due_today", "ถึงวันครบกำหนด"
        REMINDER_OVERDUE = "reminder_overdue", "เกินกำหนด (แจ้งซ้ำรายวัน)"
        SUSPENDED = "suspended", "ถูกพักสิทธิ์"
        RETURN_SUCCESS = "return_success", "คืนสำเร็จ"
        AUTO_CANCELLED = "auto_cancelled", "ยกเลิกอัตโนมัติ (ไม่มารับ)"

    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications"
    )
    trigger = models.CharField(max_length=25, choices=Trigger.choices)
    email_to = models.EmailField()
    is_success = models.BooleanField(default=True)
    error_message = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ประวัติการแจ้งเตือน"
        verbose_name_plural = "ประวัติการแจ้งเตือน"

    def __str__(self):
        return f"{self.get_trigger_display()} -> {self.email_to} ({self.sent_at:%Y-%m-%d %H:%M})"
