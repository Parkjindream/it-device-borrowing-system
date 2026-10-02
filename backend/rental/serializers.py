from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from .models import (
    User, EquipmentCategory, Equipment, EquipmentUnit, Booking, PenaltySettings, NotificationLog,
)

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB


def _validate_new_password(value):
    """ใช้ตัวตรวจรหัสผ่านมาตรฐานของ Django (ความยาว, ไม่ใช่เลขล้วน, ไม่ง่ายเกินไป)"""
    try:
        validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError(list(exc.messages))
    return value


# ---------------------------------------------------------------------------
# โมดูล A: บัญชีผู้ใช้
# ---------------------------------------------------------------------------
class UserSerializer(serializers.ModelSerializer):
    """ข้อมูลผู้ใช้ที่ปลอดภัยจะส่งกลับให้ frontend (ไม่มี password)"""

    # ใช้ตัวนี้แสดงผลบนหน้าเว็บ (คำนึงถึงวันหมดพักสิทธิ์แล้ว) ไม่ใช่ is_suspended ดิบ
    is_currently_suspended = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "username", "email", "first_name", "last_name",
            "role", "student_id", "is_suspended", "is_currently_suspended",
            "suspended_until", "suspended_reason",
        ]
        read_only_fields = fields


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """ผู้ใช้แก้ไขโปรไฟล์ตัวเองได้เฉพาะชื่อ-นามสกุล (อีเมล/รหัสนักศึกษา/สิทธิ์ ต้องให้เจ้าหน้าที่แก้)"""

    first_name = serializers.CharField(max_length=150, allow_blank=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)

    class Meta:
        model = User
        fields = ["first_name", "last_name"]

    def validate_first_name(self, value):
        return value.strip()

    def validate_last_name(self, value):
        return value.strip()


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate_new_password(self, value):
        return _validate_new_password(value)


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs.get("email")
        password = attrs.get("password")

        user_obj = User.objects.filter(email__iexact=email).first()
        if user_obj is None:
            raise serializers.ValidationError("อีเมลหรือรหัสผ่านไม่ถูกต้อง")

        user = authenticate(username=user_obj.username, password=password)
        if user is None:
            raise serializers.ValidationError("อีเมลหรือรหัสผ่านไม่ถูกต้อง")
        if not user.is_active:
            raise serializers.ValidationError("บัญชีนี้ถูกระงับการใช้งาน กรุณาติดต่อเจ้าหน้าที่")

        attrs["user"] = user
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)

    def validate_new_password(self, value):
        return _validate_new_password(value)


# ---------------------------------------------------------------------------
# โมดูล B: คลังอุปกรณ์
# ---------------------------------------------------------------------------
class EquipmentCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentCategory
        fields = ["id", "name"]

    def validate_name(self, value):
        value = value.strip()
        qs = EquipmentCategory.objects.filter(name__iexact=value)
        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("มีหมวดหมู่ชื่อนี้อยู่แล้ว")
        return value


class EquipmentUnitSerializer(serializers.ModelSerializer):
    class Meta:
        model = EquipmentUnit
        fields = ["id", "equipment", "serial_number", "status", "condition_note", "created_at", "updated_at"]
        # "equipment" อ่านอย่างเดียว: ตอนเพิ่มเครื่องใหม่ view จะเซ็ตให้จาก URL เสมอ
        read_only_fields = ["created_at", "updated_at", "equipment"]
        extra_kwargs = {"serial_number": {"error_messages": {"unique": "หมายเลขเครื่องนี้ถูกใช้ไปแล้ว"}}}

    def validate_serial_number(self, value):
        return value.strip()


class EquipmentListSerializer(serializers.ModelSerializer):
    """ใช้ในหน้ารายการอุปกรณ์ — โชว์จำนวนคงเหลือแบบเรียลไทม์"""

    category = EquipmentCategorySerializer(read_only=True)
    available_units = serializers.ReadOnlyField()
    total_units = serializers.ReadOnlyField()

    class Meta:
        model = Equipment
        fields = [
            "id", "name", "description", "category", "image",
            "available_units", "total_units", "max_borrow_days", "is_active",
        ]


class EquipmentDetailSerializer(EquipmentListSerializer):
    units = EquipmentUnitSerializer(many=True, read_only=True)

    class Meta(EquipmentListSerializer.Meta):
        fields = EquipmentListSerializer.Meta.fields + ["units"]


class EquipmentWriteSerializer(serializers.ModelSerializer):
    """เจ้าหน้าที่ใช้เพิ่ม/แก้ไข 'รุ่น' อุปกรณ์ (รองรับอัปโหลดรูปแบบ multipart)"""

    class Meta:
        model = Equipment
        fields = ["id", "category", "name", "description", "image", "max_borrow_days", "is_active"]

    def validate_image(self, image):
        if image and image.size > MAX_IMAGE_BYTES:
            raise serializers.ValidationError("รูปภาพต้องมีขนาดไม่เกิน 5 MB")
        return image

    def validate_max_borrow_days(self, value):
        if value < 1 or value > 60:
            raise serializers.ValidationError("จำนวนวันยืมต้องอยู่ระหว่าง 1-60 วัน")
        return value


class PublicEquipmentSerializer(serializers.ModelSerializer):
    """ข้อมูลอุปกรณ์แบบสาธารณะ (หน้าแรก ไม่ต้องล็อกอิน) — เฉพาะที่แสดงโชว์ได้"""

    category = serializers.CharField(source="category.name", read_only=True)
    available_units = serializers.ReadOnlyField()
    total_units = serializers.ReadOnlyField()

    class Meta:
        model = Equipment
        fields = ["id", "name", "category", "image", "available_units", "total_units", "max_borrow_days"]


# ---------------------------------------------------------------------------
# โมดูล C/D: การจอง + รับ-คืนอุปกรณ์
# ---------------------------------------------------------------------------
class BookingCreateSerializer(serializers.Serializer):
    equipment_id = serializers.IntegerField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()


class BookingSerializer(serializers.ModelSerializer):
    equipment_name = serializers.CharField(source="unit.equipment.name", read_only=True)
    equipment_image = serializers.ImageField(source="unit.equipment.image", read_only=True)
    equipment_category = serializers.CharField(source="unit.equipment.category.name", read_only=True)
    unit_serial_number = serializers.CharField(source="unit.serial_number", read_only=True)
    student_name = serializers.CharField(source="student.get_full_name", read_only=True)
    # หมายเหตุ: field นี้ชื่อ student_id แต่ดึงจาก User.student_id (รหัสนักศึกษา) ผ่าน source ตรง ๆ
    # ไม่ใช่ FK id ของ Booking.student_id
    student_id = serializers.CharField(source="student.student_id", read_only=True)
    student_email = serializers.CharField(source="student.email", read_only=True)
    is_overdue_now = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id", "booking_code", "status",
            "equipment_name", "equipment_image", "equipment_category", "unit_serial_number",
            "student_name", "student_id", "student_email",
            "requested_start_date", "requested_end_date", "booking_expires_at",
            "picked_up_at", "pickup_condition_note",
            "returned_at", "return_condition_note",
            "overdue_days_at_return", "penalty_applied", "is_overdue_now",
            "cancelled_at", "cancel_reason",
            "created_at",
        ]
        read_only_fields = fields

    def get_is_overdue_now(self, obj):
        """เช็คสดตอน serialize เผื่อ scheduled job ยังไม่ทันอัปเดตสถานะ 'เกินกำหนด'"""
        if obj.status == Booking.Status.OVERDUE:
            return True
        if obj.status == Booking.Status.BORROWED:
            return obj.requested_end_date < timezone.localdate()
        return False


class ConfirmPickupSerializer(serializers.Serializer):
    condition_note = serializers.CharField(required=False, allow_blank=True, default="")


class ConfirmReturnSerializer(serializers.Serializer):
    condition_note = serializers.CharField(required=False, allow_blank=True, default="")
    is_damaged = serializers.BooleanField(required=False, default=False)


# ---------------------------------------------------------------------------
# โมดูล F: บทลงโทษ + จัดการนักศึกษา (เจ้าหน้าที่)
# ---------------------------------------------------------------------------
class PenaltySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PenaltySettings
        fields = ["overdue_days_threshold", "suspension_days", "booking_expire_hours", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_overdue_days_threshold(self, v):
        if not 1 <= v <= 60:
            raise serializers.ValidationError("ต้องอยู่ระหว่าง 1-60 วัน")
        return v

    def validate_suspension_days(self, v):
        if not 1 <= v <= 365:
            raise serializers.ValidationError("ต้องอยู่ระหว่าง 1-365 วัน")
        return v

    def validate_booking_expire_hours(self, v):
        if not 1 <= v <= 168:
            raise serializers.ValidationError("ต้องอยู่ระหว่าง 1-168 ชั่วโมง")
        return v


class StaffStudentSerializer(serializers.ModelSerializer):
    """รายชื่อนักศึกษาสำหรับเจ้าหน้าที่ (ดู/ค้นหา/ปลดล็อก)"""

    is_currently_suspended = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name", "student_id", "is_active",
            "is_suspended", "is_currently_suspended", "suspended_until", "suspended_reason",
        ]
        read_only_fields = fields


class StudentCreateSerializer(serializers.Serializer):
    """เจ้าหน้าที่เพิ่มนักศึกษา 1 คน (ไม่ตั้งรหัสผ่านก็ได้ นักศึกษาใช้ 'ลืมรหัสผ่าน' ตั้งเองครั้งแรก)"""

    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False, default="")
    student_id = serializers.CharField(max_length=20, allow_blank=True, required=False, default="")
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, default="")

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists() or User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("อีเมลนี้ถูกใช้งานในระบบแล้ว")
        return value

    def validate_student_id(self, value):
        value = value.strip()
        if value and User.objects.filter(student_id=value).exists():
            raise serializers.ValidationError("รหัสนักศึกษานี้ถูกใช้งานในระบบแล้ว")
        return value or None

    def validate_password(self, value):
        if value:
            _validate_new_password(value)
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", "")
        user = User(
            username=validated_data["email"],
            email=validated_data["email"],
            first_name=validated_data["first_name"].strip(),
            last_name=validated_data.get("last_name", "").strip(),
            student_id=validated_data.get("student_id"),
            role=User.Role.STUDENT,
        )
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save()
        return user


class NotificationLogSerializer(serializers.ModelSerializer):
    trigger_label = serializers.CharField(source="get_trigger_display", read_only=True)
    booking_code = serializers.CharField(source="booking.booking_code", read_only=True, default=None)

    class Meta:
        model = NotificationLog
        fields = ["id", "trigger", "trigger_label", "email_to", "is_success", "error_message", "booking_code", "sent_at"]
        read_only_fields = fields
