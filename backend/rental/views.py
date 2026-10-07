import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.mail import send_mail
from django.db.models import Count, ProtectedError, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from rest_framework import generics, filters, status
from rest_framework.authtoken.models import Token
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .models import (
    User, EquipmentCategory, Equipment, EquipmentUnit, Booking, PenaltySettings, NotificationLog,
)
from .permissions import IsStaffUser, IsStudentUser
from .services import (
    BookingError, create_booking, cancel_booking, confirm_pickup, confirm_return, unsuspend_student,
)
from .jobs import cleanup_old_booking_history, cleanup_old_notification_logs
from .serializers import (
    UserSerializer,
    ProfileUpdateSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    EquipmentCategorySerializer,
    EquipmentListSerializer,
    EquipmentDetailSerializer,
    EquipmentWriteSerializer,
    EquipmentUnitSerializer,
    PublicEquipmentSerializer,
    BookingCreateSerializer,
    BookingSerializer,
    ConfirmPickupSerializer,
    ConfirmReturnSerializer,
    PenaltySettingsSerializer,
    StaffStudentSerializer,
    StudentCreateSerializer,
    NotificationLogSerializer,
)

logger = logging.getLogger(__name__)
token_generator = PasswordResetTokenGenerator()


def equipment_with_counts(qs):
    """แนบจำนวนเครื่องรวม/ว่างมากับ queryset ในคำสั่งเดียว (กัน query ซ้ำทีละรุ่น)"""
    return qs.annotate(
        _total_units=Count("units", filter=~Q(units__status=EquipmentUnit.Status.DISABLED)),
        _available_units=Count("units", filter=Q(units__status=EquipmentUnit.Status.AVAILABLE)),
    )


def protected_delete_error(what_thai: str) -> Response:
    """
    ข้อความมาตรฐานตอนลบไม่ได้เพราะมีประวัติการยืมอ้างอิงอยู่ (on_delete=PROTECT)
    แนะนำทางออก 2 ทาง: ปิดใช้งานแทน หรือเคลียร์ประวัติเก่าก่อนแล้วค่อยลบ
    """
    return Response(
        {
            "detail": (
                f"ลบ{what_thai}นี้ไม่ได้ เพราะยังมีประวัติการยืมที่เกี่ยวข้องอยู่ในระบบ "
                f"(เพื่อรักษาหลักฐานการยืม-คืน) ใช้ปุ่ม \"ปิดใช้งาน\" แทนได้ หรือเคลียร์ประวัติการยืม"
                f"เก่าที่จบแล้ว (คืนแล้ว/ยกเลิก) ในแท็บ \"ตั้งค่าระบบ\" ก่อน แล้วค่อยลองลบอีกครั้ง"
            )
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


def booking_queryset():
    return Booking.objects.select_related(
        "student", "unit", "unit__equipment", "unit__equipment__category"
    )


# ---------------------------------------------------------------------------
# โมดูล A: บัญชีผู้ใช้
# ---------------------------------------------------------------------------
class LoginView(APIView):
    """POST /api/auth/login/  {email, password} -> {token, user}"""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "user": UserSerializer(user).data})


class LogoutView(APIView):
    """POST /api/auth/logout/ — ลบ token ปัจจุบัน"""

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """
    GET   /api/auth/me/ — ข้อมูลผู้ใช้ที่ล็อกอินอยู่
    PATCH /api/auth/me/ — แก้ไขชื่อ-นามสกุล/รหัสนักศึกษา/รูปโปรไฟล์ของตัวเอง (บันทึกถาวร)
           รองรับทั้ง JSON ธรรมดา และ multipart/form-data (ตอนแนบรูป)
    """

    def get(self, request):
        return Response(UserSerializer(request.user, context={"request": request}).data)

    def patch(self, request):
        serializer = ProfileUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(request.user, context={"request": request}).data)


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/  {old_password, new_password}"""

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response({"detail": "รหัสผ่านปัจจุบันไม่ถูกต้อง"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=["password"])
        # ออกจากระบบอุปกรณ์อื่นทั้งหมด แต่คง token ของเครื่องที่กำลังใช้อยู่
        other_tokens = Token.objects.filter(user=user)
        if request.auth is not None and hasattr(request.auth, "key"):
            other_tokens = other_tokens.exclude(key=request.auth.key)
        other_tokens.delete()
        return Response({"detail": "เปลี่ยนรหัสผ่านสำเร็จ"})


class PasswordResetRequestView(APIView):
    """POST /api/auth/password-reset/  {email} -> ส่งอีเมลลิงก์ตั้งรหัสผ่านใหม่"""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset_request"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"]

        user = User.objects.filter(email__iexact=email, is_active=True).first()
        # log ระดับ console เสมอ (ไม่ส่งกลับไปให้ client เห็น) ไว้ให้เจ้าหน้าที่ไล่ปัญหาจาก terminal ได้ตรงจุด
        logger.info("ขอลิงก์ตั้งรหัสผ่านใหม่: email=%s พบผู้ใช้ในระบบ=%s", email, user is not None)

        email_sent = False
        if user is not None:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = token_generator.make_token(user)
            reset_link = f"{settings.FRONTEND_RESET_PASSWORD_URL}?uid={uid}&token={token}"
            try:
                send_mail(
                    subject="ตั้งรหัสผ่านใหม่ - ศูนย์ยืม-คืนอุปกรณ์ไอที",
                    message=(
                        f"คลิกลิงก์นี้เพื่อตั้งรหัสผ่านใหม่:\n{reset_link}\n\n"
                        "ลิงก์นี้จะหมดอายุใน 24 ชั่วโมง หากคุณไม่ได้ทำรายการนี้ กรุณาเพิกเฉยอีเมลนี้"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )
                email_sent = True
                logger.info("ส่งอีเมลตั้งรหัสผ่านใหม่สำเร็จ: %s (ลิงก์: %s)", email, reset_link)
            except Exception:
                logger.exception("ส่งอีเมลรีเซ็ตรหัสผ่านไม่สำเร็จ (เช็คค่า EMAIL_* ใน .env): %s", email)

            NotificationLog.objects.create(
                booking=None,
                user=user,
                trigger=NotificationLog.Trigger.PASSWORD_RESET_REQUESTED,
                email_to=email,
                is_success=email_sent,
                error_message="" if email_sent else "ส่งอีเมลไม่สำเร็จ ดู log ฝั่ง backend",
            )

        # ตอบข้อความเดียวกันเสมอ กันคนแอบเดาว่าอีเมลไหนมีอยู่ในระบบ
        return Response({"detail": "หากอีเมลนี้มีอยู่ในระบบ เราได้ส่งลิงก์ตั้งรหัสผ่านไปให้แล้ว"})


class PasswordResetConfirmView(APIView):
    """POST /api/auth/password-reset-confirm/  {uid, token, new_password}"""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "password_reset_confirm"

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            uid = force_str(urlsafe_base64_decode(data["uid"]))
            user = User.objects.get(pk=uid)
        except (User.DoesNotExist, ValueError, TypeError, OverflowError):
            return Response({"detail": "ลิงก์ไม่ถูกต้อง"}, status=status.HTTP_400_BAD_REQUEST)

        if not token_generator.check_token(user, data["token"]):
            return Response({"detail": "ลิงก์หมดอายุหรือถูกใช้ไปแล้ว"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(data["new_password"])
        user.save(update_fields=["password"])
        Token.objects.filter(user=user).delete()  # บังคับให้ login ใหม่ทุกอุปกรณ์
        return Response({"detail": "ตั้งรหัสผ่านใหม่สำเร็จ กรุณาเข้าสู่ระบบอีกครั้ง"})


# ---------------------------------------------------------------------------
# โมดูล B: คลังอุปกรณ์ (ทุกคนที่ล็อกอิน)
# ---------------------------------------------------------------------------
class PublicEquipmentListView(generics.ListAPIView):
    """
    GET /api/public/equipment/ — ไม่ต้องล็อกอิน ใช้โชว์อุปกรณ์/จำนวนว่างบนหน้าแรก
    (เปิดเผยเฉพาะชื่อ/หมวด/รูป/จำนวนว่าง ซึ่งไม่ใช่ข้อมูลส่วนบุคคล)
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public"
    serializer_class = PublicEquipmentSerializer
    pagination_class = None

    def get_queryset(self):
        qs = Equipment.objects.filter(is_active=True).select_related("category")
        return equipment_with_counts(qs).order_by("category__name", "name")


class EquipmentCategoryListView(generics.ListAPIView):
    """GET /api/equipment-categories/"""

    queryset = EquipmentCategory.objects.all().order_by("name")
    serializer_class = EquipmentCategorySerializer
    permission_classes = [IsAuthenticated]


class EquipmentListView(generics.ListAPIView):
    """GET /api/equipment/?category=<id>&search=<คำค้น> — พร้อมจำนวนคงเหลือแบบเรียลไทม์"""

    serializer_class = EquipmentListSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "description"]

    def get_queryset(self):
        qs = Equipment.objects.filter(is_active=True).select_related("category")
        category_id = self.request.query_params.get("category")
        if category_id:
            qs = qs.filter(category_id=category_id)
        return equipment_with_counts(qs).order_by("name")


class EquipmentDetailView(generics.RetrieveAPIView):
    """GET /api/equipment/<id>/ (เฉพาะรุ่นที่เปิดให้ยืม)"""

    serializer_class = EquipmentDetailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Equipment.objects.filter(is_active=True).select_related("category").prefetch_related("units")
        return equipment_with_counts(qs)


# ---------------------------------------------------------------------------
# โมดูล B: จัดการคลังอุปกรณ์ (เฉพาะเจ้าหน้าที่)
# ---------------------------------------------------------------------------
class StaffCategoryListCreateView(generics.ListCreateAPIView):
    """GET/POST /api/staff/equipment-categories/ — ดู/เพิ่มหมวดหมู่อุปกรณ์"""

    queryset = EquipmentCategory.objects.all().order_by("name")
    serializer_class = EquipmentCategorySerializer
    permission_classes = [IsStaffUser]


class StaffCategoryDetailView(generics.RetrieveUpdateAPIView):
    """
    PATCH  /api/staff/equipment-categories/<id>/ — เปลี่ยนชื่อหมวดหมู่
    DELETE /api/staff/equipment-categories/<id>/ — ลบหมวดหมู่ (ลบไม่ได้ถ้ายังมีอุปกรณ์รุ่นไหนใช้อยู่)
    """

    queryset = EquipmentCategory.objects.all()
    serializer_class = EquipmentCategorySerializer
    permission_classes = [IsStaffUser]

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        equipment_count = instance.equipment_list.count()
        if equipment_count > 0:
            return Response(
                {"detail": f"ลบหมวดหมู่นี้ไม่ได้ เพราะยังมีอุปกรณ์ {equipment_count} รุ่นอยู่ในหมวดนี้ ย้ายหรือลบอุปกรณ์เหล่านั้นก่อน"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instance.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffEquipmentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/staff/equipment/   — ดูทุกรุ่น (รวมที่ปิดใช้งาน)
    POST /api/staff/equipment/   — เพิ่มรุ่นอุปกรณ์ใหม่ (รองรับ multipart พร้อมรูป)
    """

    permission_classes = [IsStaffUser]

    def get_queryset(self):
        return equipment_with_counts(Equipment.objects.select_related("category")).order_by("name")

    def get_serializer_class(self):
        return EquipmentListSerializer if self.request.method == "GET" else EquipmentWriteSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        equipment = serializer.save()
        # ตอบกลับเป็นรูปแบบเดียวกับตอนอ่านรายการ (มี category เป็น object และจำนวนเครื่อง)
        out = EquipmentListSerializer(equipment, context=self.get_serializer_context())
        return Response(out.data, status=status.HTTP_201_CREATED)


class StaffEquipmentDetailView(generics.RetrieveUpdateAPIView):
    """
    GET    /api/staff/equipment/<id>/
    PATCH  /api/staff/equipment/<id>/   — แก้ไขข้อมูล/เปลี่ยนรูป/ปิดใช้งาน (is_active=false)
    DELETE /api/staff/equipment/<id>/   — ลบรุ่นอุปกรณ์นี้ทิ้งถาวร (ลบไม่ได้ถ้ามีประวัติการยืมค้างอยู่)
    """

    permission_classes = [IsStaffUser]

    def get_queryset(self):
        return equipment_with_counts(Equipment.objects.select_related("category").prefetch_related("units"))

    def get_serializer_class(self):
        return EquipmentDetailSerializer if self.request.method == "GET" else EquipmentWriteSerializer

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        fresh = self.get_queryset().get(pk=instance.pk)
        return Response(EquipmentListSerializer(fresh, context=self.get_serializer_context()).data)

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            instance.delete()
        except ProtectedError:
            return protected_delete_error("อุปกรณ์รุ่น")
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffEquipmentUnitListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/staff/equipment/<equipment_id>/units/   — ดูอุปกรณ์รายชิ้นของรุ่นนี้
    POST /api/staff/equipment/<equipment_id>/units/   — เพิ่มอุปกรณ์ชิ้นใหม่ (เพิ่มสต็อก)
    """

    serializer_class = EquipmentUnitSerializer
    permission_classes = [IsStaffUser]
    pagination_class = None

    def get_queryset(self):
        return EquipmentUnit.objects.filter(equipment_id=self.kwargs["equipment_id"]).order_by("serial_number")

    def perform_create(self, serializer):
        equipment = get_object_or_404(Equipment, pk=self.kwargs["equipment_id"])
        serializer.save(equipment=equipment)


class StaffEquipmentUnitDetailView(generics.RetrieveUpdateAPIView):
    """
    PATCH /api/staff/units/<id>/
    ใช้แก้สถานะชิ้น เช่น ปิดใช้งานเพราะชำรุด (status='disabled') / เปิดกลับ (status='available')
    พร้อมบันทึก condition_note

    กันไว้ 2 อย่าง (ระบบจองต้องเป็นผู้คุมสถานะเหล่านี้เท่านั้น):
    - ห้ามตั้งสถานะเป็น reserved/borrowed เอง
    - ห้ามเปลี่ยนสถานะของชิ้นที่กำลังถูกจอง/ยืมอยู่ (ต้องรับคืนหรือยกเลิกการจองก่อน)
    """

    queryset = EquipmentUnit.objects.all()
    serializer_class = EquipmentUnitSerializer
    permission_classes = [IsStaffUser]

    def perform_update(self, serializer):
        managed = (EquipmentUnit.Status.RESERVED, EquipmentUnit.Status.BORROWED)
        requested_status = serializer.validated_data.get("status")
        if requested_status in managed:
            raise ValidationError({"status": "ห้ามตั้งสถานะนี้เอง ระบบจองจะเปลี่ยนสถานะให้อัตโนมัติ"})
        if requested_status is not None and serializer.instance.status in managed:
            raise ValidationError(
                {"status": "อุปกรณ์ชิ้นนี้กำลังถูกจอง/ยืมอยู่ แก้สถานะไม่ได้ (ต้องรับคืนหรือยกเลิกการจองก่อน)"}
            )
        serializer.save()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        managed = (EquipmentUnit.Status.RESERVED, EquipmentUnit.Status.BORROWED)
        if instance.status in managed:
            return Response(
                {"detail": "อุปกรณ์ชิ้นนี้กำลังถูกจอง/ยืมอยู่ ลบไม่ได้ (ต้องรับคืนหรือยกเลิกการจองก่อน)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            instance.delete()
        except ProtectedError:
            return protected_delete_error("อุปกรณ์ชิ้น")
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# โมดูล C: การจอง (ฝั่งนักศึกษา)
# ---------------------------------------------------------------------------
class MyBookingListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/bookings/   — ดูประวัติ/รายการจองทั้งหมดของตัวเอง
    POST /api/bookings/   — จองอุปกรณ์ใหม่ {equipment_id, start_date, end_date}
    """

    permission_classes = [IsStudentUser]

    def get_queryset(self):
        return booking_queryset().filter(student=self.request.user).order_by("-created_at")

    def get_serializer_class(self):
        return BookingCreateSerializer if self.request.method == "POST" else BookingSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking = create_booking(
                student=request.user,
                equipment_id=serializer.validated_data["equipment_id"],
                start_date=serializer.validated_data["start_date"],
                end_date=serializer.validated_data["end_date"],
            )
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        booking = booking_queryset().get(pk=booking.pk)
        return Response(BookingSerializer(booking, context={"request": request}).data, status=status.HTTP_201_CREATED)


class MyBookingCancelView(APIView):
    """POST /api/bookings/<id>/cancel/ — นักศึกษายกเลิกการจองของตัวเอง (เฉพาะตอนยังไม่มารับ)"""

    permission_classes = [IsStudentUser]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, student=request.user)
        try:
            booking = cancel_booking(booking)
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        booking = booking_queryset().get(pk=booking.pk)
        return Response(BookingSerializer(booking, context={"request": request}).data)


class MyBookingDeleteView(APIView):
    """
    DELETE /api/bookings/<id>/delete/
    นักศึกษาลบประวัติการยืมของตัวเอง "ทีละรายการ" — ลบได้เฉพาะรายการที่จบแล้ว
    (คืนแล้ว/ยกเลิก) เท่านั้น รายการที่ยังไม่จบจะลบไม่ได้ไม่ว่ากรณีใด
    """

    permission_classes = [IsStudentUser]

    def delete(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk, student=request.user)
        if booking.status not in (Booking.Status.RETURNED, Booking.Status.CANCELLED):
            return Response(
                {"detail": "ลบได้เฉพาะรายการที่จบแล้วเท่านั้น (คืนแล้ว/ยกเลิก)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MyBookingHistoryClearView(APIView):
    """
    POST /api/bookings/clear-history/
    นักศึกษาล้างประวัติการยืมของ "ตัวเอง" ที่จบแล้ว (คืนแล้ว/ยกเลิก) ด้วยมือทันที
    ไม่แตะรายการที่ยังไม่จบ (รอรับของ/กำลังยืม/เกินกำหนด) ไม่ว่ากรณีใดก็ตาม
    ค่าเริ่มต้นลบเฉพาะรายการที่เก่ากว่าเกณฑ์ปกติ (settings.BOOKING_HISTORY_RETENTION_DAYS)
    ส่ง {"clear_all": true} มาด้วยถ้าต้องการล้างทุกรายการที่จบแล้วของตัวเองทันทีไม่สนวันที่
    """

    permission_classes = [IsStudentUser]

    def post(self, request):
        base_qs = Booking.objects.filter(
            student=request.user,
            status__in=[Booking.Status.RETURNED, Booking.Status.CANCELLED],
        )
        if request.data.get("clear_all"):
            deleted_count, _ = base_qs.delete()
        else:
            cutoff = timezone.now() - timedelta(days=settings.BOOKING_HISTORY_RETENTION_DAYS)
            deleted_count, _ = base_qs.filter(updated_at__lt=cutoff).delete()
        return Response({"deleted_count": deleted_count})


# ---------------------------------------------------------------------------
# โมดูล D: รับ-คืนอุปกรณ์ (ฝั่งเจ้าหน้าที่)
# ---------------------------------------------------------------------------
class StaffBookingListView(generics.ListAPIView):
    """
    GET /api/staff/bookings/?status=awaiting_pickup&search=<booking_code หรือรหัสนักศึกษา>

    status=overdue จะรวมรายการที่ 'เลยกำหนดคืนแล้วแต่ scheduled job ยังไม่ทันเปลี่ยนสถานะ' ด้วย
    ทำให้ตัวเลข/รายการตรงกับความจริงเสมอ ไม่ต้องรอ job รัน
    """

    serializer_class = BookingSerializer
    permission_classes = [IsStaffUser]
    filter_backends = [filters.SearchFilter]
    search_fields = ["booking_code", "student__student_id", "student__username",
                     "student__first_name", "student__last_name", "unit__serial_number"]

    def get_queryset(self):
        qs = booking_queryset().order_by("-created_at")
        status_param = self.request.query_params.get("status")
        today = timezone.localdate()
        if status_param == "overdue":
            qs = qs.filter(
                Q(status=Booking.Status.OVERDUE)
                | Q(status=Booking.Status.BORROWED, requested_end_date__lt=today)
            )
        elif status_param == "borrowed":
            qs = qs.filter(status=Booking.Status.BORROWED, requested_end_date__gte=today)
        elif status_param == "due_today":
            qs = qs.filter(status=Booking.Status.BORROWED, requested_end_date=today)
        elif status_param:
            qs = qs.filter(status=status_param)
        return qs


class StaffBookingLookupView(APIView):
    """
    GET /api/staff/bookings/lookup/?code=<booking_code>

    *** จุดสำคัญตามเอกสาร: การสแกน QR เรียก endpoint นี้เพื่อ "ดึงข้อมูลขึ้นจอ" เท่านั้น ***
    endpoint นี้ไม่เปลี่ยนสถานะอะไรทั้งสิ้น เจ้าหน้าที่ต้องกดปุ่มยืนยันเอง (คนละ endpoint)
    """

    permission_classes = [IsStaffUser]

    def get(self, request):
        code = request.query_params.get("code", "").strip().upper()
        if not code:
            return Response({"detail": "กรุณาระบุ booking code"}, status=status.HTTP_400_BAD_REQUEST)

        booking = booking_queryset().filter(booking_code=code).first()
        if booking is None:
            return Response({"detail": "ไม่พบรายการจองนี้ในระบบ"}, status=status.HTTP_404_NOT_FOUND)
        return Response(BookingSerializer(booking, context={"request": request}).data)


class StaffConfirmPickupView(APIView):
    """POST /api/staff/bookings/<id>/confirm-pickup/  {condition_note}"""

    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        serializer = ConfirmPickupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking = confirm_pickup(
                booking, staff_user=request.user,
                condition_note=serializer.validated_data["condition_note"],
            )
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        booking = booking_queryset().get(pk=booking.pk)
        return Response(BookingSerializer(booking, context={"request": request}).data)


class StaffConfirmReturnView(APIView):
    """POST /api/staff/bookings/<id>/confirm-return/  {condition_note, is_damaged}"""

    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        serializer = ConfirmReturnSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            booking = confirm_return(
                booking, staff_user=request.user,
                condition_note=serializer.validated_data["condition_note"],
                is_damaged=serializer.validated_data["is_damaged"],
            )
        except BookingError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        booking = booking_queryset().get(pk=booking.pk)
        return Response(BookingSerializer(booking, context={"request": request}).data)


class StaffBookingDeleteView(APIView):
    """
    DELETE /api/staff/bookings/<id>/delete/
    เจ้าหน้าที่ลบประวัติการยืมของนักศึกษาคนไหนก็ได้ "ทีละรายการ" — ลบได้เฉพาะรายการที่
    จบแล้ว (คืนแล้ว/ยกเลิก) เท่านั้น รายการที่ยังไม่จบจะลบไม่ได้ไม่ว่ากรณีใด
    """

    permission_classes = [IsStaffUser]

    def delete(self, request, pk):
        booking = get_object_or_404(Booking, pk=pk)
        if booking.status not in (Booking.Status.RETURNED, Booking.Status.CANCELLED):
            return Response(
                {"detail": "ลบได้เฉพาะรายการที่จบแล้วเท่านั้น (คืนแล้ว/ยกเลิก)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        booking.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# โมดูล F: บทลงโทษ + จัดการนักศึกษา (เจ้าหน้าที่เท่านั้น)
# ---------------------------------------------------------------------------
class StaffPenaltySettingsView(APIView):
    """
    GET   /api/staff/penalty-settings/ — ดูเกณฑ์ปัจจุบัน
    PATCH /api/staff/penalty-settings/ — แก้เกณฑ์ (มีผลกับการรับคืน/จองครั้งถัดไปทันที ไม่ต้องแก้โค้ด)
    """

    permission_classes = [IsStaffUser]

    def get(self, request):
        return Response(PenaltySettingsSerializer(PenaltySettings.get_solo()).data)

    def patch(self, request):
        obj = PenaltySettings.get_solo()
        serializer = PenaltySettingsSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StaffStudentListCreateView(APIView):
    """
    GET  /api/staff/students/?search=&suspended=1  — ค้นหา/ดูรายชื่อนักศึกษา
    POST /api/staff/students/                      — เพิ่มนักศึกษา 1 คน
    """

    permission_classes = [IsStaffUser]

    def get(self, request):
        qs = User.objects.filter(role=User.Role.STUDENT).order_by("first_name", "last_name", "id")
        search = request.query_params.get("search", "").strip()
        if search:
            qs = qs.filter(
                Q(email__icontains=search) | Q(first_name__icontains=search)
                | Q(last_name__icontains=search) | Q(student_id__icontains=search)
            )
        if request.query_params.get("suspended") == "1":
            qs = qs.filter(is_suspended=True).filter(
                Q(suspended_until__isnull=True) | Q(suspended_until__gt=timezone.localdate())
            )
        return Response(StaffStudentSerializer(qs[:200], many=True).data)

    def post(self, request):
        serializer = StudentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(StaffStudentSerializer(user).data, status=status.HTTP_201_CREATED)


class StaffStudentDetailView(APIView):
    """
    PATCH /api/staff/students/<id>/
    แก้ไขข้อมูลนักศึกษาที่มีอยู่แล้ว — ใช้เติมรหัสนักศึกษาที่ขาดหาย หรือแก้ชื่อ-นามสกุลให้ถูกต้อง
    (เช่นบัญชีที่เคยถูกสร้างแบบไม่ครบข้อมูลมาก่อน)
    """

    permission_classes = [IsStaffUser]

    def patch(self, request, pk):
        student = get_object_or_404(User, pk=pk, role=User.Role.STUDENT)
        allowed_fields = {"first_name", "last_name", "student_id"}
        data = {k: v for k, v in request.data.items() if k in allowed_fields}

        student_id = data.get("student_id", "").strip() if "student_id" in data else None
        if student_id:
            if User.objects.filter(student_id=student_id).exclude(pk=student.pk).exists():
                return Response({"detail": "รหัสนักศึกษานี้ถูกใช้งานโดยคนอื่นแล้ว"}, status=status.HTTP_400_BAD_REQUEST)
            data["student_id"] = student_id
        elif "student_id" in data and not student_id:
            data["student_id"] = None

        for field, value in data.items():
            setattr(student, field, value.strip() if isinstance(value, str) else value)
        student.save(update_fields=list(data.keys()) if data else ["id"])
        return Response(StaffStudentSerializer(student).data)


class StaffStudentImportView(APIView):
    """
    POST /api/staff/students/import/  {"students": [{email, first_name, last_name, student_id}, ...]}
    นำเข้านักศึกษาทีละหลายคน (สูงสุด 500 แถว/ครั้ง) — แถวไหนผิดจะข้าม แล้วรายงานเหตุผลกลับไป
    บัญชีที่สร้างจะยังไม่มีรหัสผ่าน นักศึกษาใช้ "ลืมรหัสผ่าน" เพื่อตั้งรหัสผ่านครั้งแรกเอง
    """

    permission_classes = [IsStaffUser]

    def post(self, request):
        rows = request.data.get("students")
        if not isinstance(rows, list) or not rows:
            return Response({"detail": "ไม่พบรายชื่อที่จะนำเข้า"}, status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > 500:
            return Response({"detail": "นำเข้าได้ครั้งละไม่เกิน 500 รายการ"}, status=status.HTTP_400_BAD_REQUEST)

        created, errors = 0, []
        seen_emails = set()
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                errors.append({"row": index, "reason": "รูปแบบข้อมูลไม่ถูกต้อง"})
                continue
            email = str(row.get("email", "")).strip().lower()
            if email in seen_emails:
                errors.append({"row": index, "email": email, "reason": "อีเมลซ้ำในไฟล์เดียวกัน"})
                continue
            seen_emails.add(email)

            serializer = StudentCreateSerializer(data={
                "email": email,
                "first_name": row.get("first_name", ""),
                "last_name": row.get("last_name", ""),
                "student_id": row.get("student_id", ""),
            })
            if serializer.is_valid():
                serializer.save()
                created += 1
            else:
                first_error = next(iter(serializer.errors.values()))
                errors.append({"row": index, "email": email, "reason": str(first_error[0])})

        return Response({"created": created, "skipped": len(errors), "errors": errors[:100]})


class StaffUnsuspendStudentView(APIView):
    """POST /api/staff/students/<id>/unsuspend/ — ปลดพักสิทธิ์ก่อนกำหนดในกรณีพิเศษ"""

    permission_classes = [IsStaffUser]

    def post(self, request, pk):
        student = get_object_or_404(User, pk=pk, role=User.Role.STUDENT)
        student = unsuspend_student(student)
        return Response(StaffStudentSerializer(student).data)


class StaffNotificationListView(generics.ListAPIView):
    """GET /api/staff/notifications/ — ประวัติอีเมลแจ้งเตือนล่าสุด 100 รายการ (ไว้เช็คว่าส่งสำเร็จหรือไม่)"""

    serializer_class = NotificationLogSerializer
    permission_classes = [IsStaffUser]
    pagination_class = None

    def get_queryset(self):
        return NotificationLog.objects.select_related("booking").order_by("-sent_at")[:100]


class StaffNotificationClearView(APIView):
    """
    POST /api/staff/notifications/clear/
    ล้างประวัติอีเมลด้วยมือทันที (เผื่อไม่อยากรอรอบเคลียร์อัตโนมัติรายวัน)
    ค่าเริ่มต้นลบเฉพาะรายการที่เก่ากว่าเกณฑ์ปกติ (settings.NOTIFICATION_LOG_RETENTION_DAYS)
    ส่ง {"clear_all": true} มาด้วยถ้าต้องการล้างทั้งหมดทันทีไม่สนวันที่
    """

    permission_classes = [IsStaffUser]

    def post(self, request):
        if request.data.get("clear_all"):
            deleted_count, _ = NotificationLog.objects.all().delete()
        else:
            deleted_count = cleanup_old_notification_logs()
        return Response({"deleted_count": deleted_count})


class StaffBookingHistoryClearView(APIView):
    """
    POST /api/staff/bookings/clear-history/
    ล้างประวัติการยืมที่ "จบแล้ว" (คืนแล้ว/ยกเลิก) ด้วยมือทันที — ไม่แตะรายการที่ยังไม่จบ
    (รอรับของ/กำลังยืม/เกินกำหนด) ไม่ว่ากรณีใดก็ตาม เพื่อความปลอดภัย
    ค่าเริ่มต้นลบเฉพาะรายการที่เก่ากว่าเกณฑ์ปกติ (settings.BOOKING_HISTORY_RETENTION_DAYS)
    ส่ง {"clear_all": true} มาด้วยถ้าต้องการล้างทุกรายการที่จบแล้วทันทีไม่สนวันที่
    """

    permission_classes = [IsStaffUser]

    def post(self, request):
        if request.data.get("clear_all"):
            deleted_count, _ = Booking.objects.filter(
                status__in=[Booking.Status.RETURNED, Booking.Status.CANCELLED],
            ).delete()
        else:
            deleted_count = cleanup_old_booking_history()
        return Response({"deleted_count": deleted_count})


# ---------------------------------------------------------------------------
# โมดูล G: ภาพรวม/แดชบอร์ด (เจ้าหน้าที่)
# ---------------------------------------------------------------------------
class StaffDashboardSummaryView(APIView):
    """GET /api/staff/dashboard-summary/ — ตัวเลขสรุปภาพรวม คำนวณสดทุกครั้ง"""

    permission_classes = [IsStaffUser]

    def get(self, request):
        today = timezone.localdate()
        active_units = EquipmentUnit.objects.exclude(status=EquipmentUnit.Status.DISABLED)

        data = {
            "equipment_model_count": Equipment.objects.filter(is_active=True).count(),
            "total_units": active_units.count(),
            "available_units": active_units.filter(status=EquipmentUnit.Status.AVAILABLE).count(),
            "awaiting_pickup_count": Booking.objects.filter(status=Booking.Status.AWAITING_PICKUP).count(),
            "borrowed_count": Booking.objects.filter(
                status=Booking.Status.BORROWED, requested_end_date__gte=today
            ).count(),
            "due_today_count": Booking.objects.filter(
                status=Booking.Status.BORROWED, requested_end_date=today
            ).count(),
            "overdue_count": Booking.objects.filter(
                Q(status=Booking.Status.OVERDUE)
                | Q(status=Booking.Status.BORROWED, requested_end_date__lt=today)
            ).count(),
            "suspended_student_count": User.objects.filter(
                role=User.Role.STUDENT, is_suspended=True
            ).filter(Q(suspended_until__isnull=True) | Q(suspended_until__gt=today)).count(),
        }
        return Response(data)