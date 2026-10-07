from django.urls import path

from . import views

app_name = "rental"

urlpatterns = [
    # --- โมดูล A: บัญชีผู้ใช้ ---
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("auth/password-reset/", views.PasswordResetRequestView.as_view(), name="password-reset"),
    path("auth/password-reset-confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),

    # --- โมดูล B: คลังอุปกรณ์ (สาธารณะ + ผู้ที่ล็อกอิน) ---
    path("public/equipment/", views.PublicEquipmentListView.as_view(), name="public-equipment-list"),
    path("equipment-categories/", views.EquipmentCategoryListView.as_view(), name="equipment-category-list"),
    path("equipment/", views.EquipmentListView.as_view(), name="equipment-list"),
    path("equipment/<int:pk>/", views.EquipmentDetailView.as_view(), name="equipment-detail"),

    # --- โมดูล B: คลังอุปกรณ์ (เฉพาะเจ้าหน้าที่) ---
    path("staff/equipment-categories/", views.StaffCategoryListCreateView.as_view(), name="staff-category-list"),
    path("staff/equipment-categories/<int:pk>/", views.StaffCategoryDetailView.as_view(), name="staff-category-detail"),
    path("staff/equipment/", views.StaffEquipmentListCreateView.as_view(), name="staff-equipment-list"),
    path("staff/equipment/<int:pk>/", views.StaffEquipmentDetailView.as_view(), name="staff-equipment-detail"),
    path(
        "staff/equipment/<int:equipment_id>/units/",
        views.StaffEquipmentUnitListCreateView.as_view(),
        name="staff-equipment-unit-list",
    ),
    path("staff/units/<int:pk>/", views.StaffEquipmentUnitDetailView.as_view(), name="staff-unit-detail"),

    # --- โมดูล C: การจอง (ฝั่งนักศึกษา) ---
    path("bookings/", views.MyBookingListCreateView.as_view(), name="my-booking-list"),
    path("bookings/<int:pk>/cancel/", views.MyBookingCancelView.as_view(), name="my-booking-cancel"),
    path("bookings/<int:pk>/delete/", views.MyBookingDeleteView.as_view(), name="my-booking-delete"),
    path("bookings/clear-history/", views.MyBookingHistoryClearView.as_view(), name="my-booking-clear-history"),

    # --- โมดูล D: รับ-คืนอุปกรณ์ (ฝั่งเจ้าหน้าที่) ---
    path("staff/bookings/", views.StaffBookingListView.as_view(), name="staff-booking-list"),
    path("staff/bookings/lookup/", views.StaffBookingLookupView.as_view(), name="staff-booking-lookup"),
    path("staff/bookings/<int:pk>/confirm-pickup/", views.StaffConfirmPickupView.as_view(), name="staff-confirm-pickup"),
    path("staff/bookings/<int:pk>/confirm-return/", views.StaffConfirmReturnView.as_view(), name="staff-confirm-return"),
    path("staff/bookings/<int:pk>/delete/", views.StaffBookingDeleteView.as_view(), name="staff-booking-delete"),
    path("staff/bookings/clear-history/", views.StaffBookingHistoryClearView.as_view(), name="staff-booking-clear-history"),

    # --- โมดูล E/F/G: แจ้งเตือน, บทลงโทษ, นักศึกษา, ภาพรวม (เจ้าหน้าที่) ---
    path("staff/penalty-settings/", views.StaffPenaltySettingsView.as_view(), name="staff-penalty-settings"),
    path("staff/students/", views.StaffStudentListCreateView.as_view(), name="staff-student-list"),
    path("staff/students/import/", views.StaffStudentImportView.as_view(), name="staff-student-import"),
    path("staff/students/<int:pk>/", views.StaffStudentDetailView.as_view(), name="staff-student-detail"),
    path("staff/students/<int:pk>/unsuspend/", views.StaffUnsuspendStudentView.as_view(), name="staff-unsuspend-student"),
    path("staff/notifications/", views.StaffNotificationListView.as_view(), name="staff-notification-list"),
    path("staff/notifications/clear/", views.StaffNotificationClearView.as_view(), name="staff-notification-clear"),
    path("staff/dashboard-summary/", views.StaffDashboardSummaryView.as_view(), name="staff-dashboard-summary"),
]