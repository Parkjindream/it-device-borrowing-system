from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    User,
    EquipmentCategory,
    Equipment,
    EquipmentUnit,
    Booking,
    PenaltySettings,
    NotificationLog,
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = (
        "username", "email", "role", "student_id",
        "is_suspended", "suspended_until", "is_active",
    )
    list_filter = ("role", "is_suspended", "is_active")
    fieldsets = UserAdmin.fieldsets + (
        ("ข้อมูลระบบยืม-คืน", {
            "fields": ("role", "student_id", "is_suspended", "suspended_until", "suspended_reason"),
        }),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ("ข้อมูลระบบยืม-คืน", {"fields": ("email", "first_name", "last_name", "role", "student_id")}),
    )


@admin.register(EquipmentCategory)
class EquipmentCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


class EquipmentUnitInline(admin.TabularInline):
    model = EquipmentUnit
    extra = 0
    fields = ("serial_number", "status", "condition_note")


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "available_units", "total_units", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name",)
    inlines = [EquipmentUnitInline]


@admin.register(EquipmentUnit)
class EquipmentUnitAdmin(admin.ModelAdmin):
    list_display = ("serial_number", "equipment", "status", "updated_at")
    list_filter = ("status", "equipment__category")
    search_fields = ("serial_number", "equipment__name")


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        "booking_code", "student", "unit", "status",
        "requested_start_date", "requested_end_date",
        "picked_up_at", "returned_at", "penalty_applied",
    )
    list_filter = ("status", "penalty_applied")
    search_fields = ("booking_code", "student__username", "student__student_id", "unit__serial_number")
    readonly_fields = ("booking_code", "created_at", "updated_at")


@admin.register(PenaltySettings)
class PenaltySettingsAdmin(admin.ModelAdmin):
    list_display = ("overdue_days_threshold", "suspension_days", "booking_expire_hours", "updated_at")

    def has_add_permission(self, request):
        # Singleton: มีได้แถวเดียว
        return not PenaltySettings.objects.exists()


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("trigger", "email_to", "is_success", "sent_at")
    list_filter = ("trigger", "is_success")
    search_fields = ("email_to",)
    readonly_fields = [f.name for f in NotificationLog._meta.fields]
