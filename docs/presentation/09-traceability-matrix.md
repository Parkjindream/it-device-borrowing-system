# 9. Traceability Matrix

โยง **ความต้องการ (functional โมดูล A–G / security SR)** → **endpoint** → **โค้ดที่รับผิดชอบ** → **control ด้านความปลอดภัย** → **เทสต์ที่ยืนยัน** เพื่อพิสูจน์ว่าทุกความต้องการถูกพัฒนาและทดสอบจริง (endpoint ทั้งหมดมา from `rental/urls.py`, prefix `/api`)

## 9.1 Functional Requirements → โค้ด → เทสต์

| Req | ความสามารถ | Endpoint | View (`views.py`) | Control | เทสต์ (`tests.py`) |
|:---:|-----------|----------|-------------------|---------|---------------------|
| A-1 | ล็อกอินรับ token | `POST /auth/login/` | `LoginView` | AllowAny + throttle `login` | `test_login_returns_token_and_user`, `test_login_wrong_password` |
| A-2 | ออกจากระบบ (ลบ token) | `POST /auth/logout/` | `LogoutView` | IsAuthenticated | (ครอบใน flow auth) |
| A-3 | ดู/แก้โปรไฟล์ตัวเอง | `GET/PATCH /auth/me/` | `MeView` | เฉพาะ field ที่อนุญาต | `test_profile_update_persists` |
| A-4 | เปลี่ยนรหัสผ่าน | `POST /auth/change-password/` | `ChangePasswordView` | ตรวจรหัสเดิม + เพิกถอน token | `test_change_password` |
| A-5 | ขอ/ยืนยันลิงก์ตั้งรหัสใหม่ | `POST /auth/password-reset[-confirm]/` | `PasswordReset*View` | AllowAny + throttle + anti-enumeration | `test_reset_link_uses_request_host_when_url_not_set` |
| B-1 | ดูอุปกรณ์สาธารณะ | `GET /public/equipment/` | `PublicEquipmentListView` | AllowAny + throttle `public` | `test_anonymous_blocked_but_public_equipment_open` |
| B-2 | ดู/ค้นอุปกรณ์ (ล็อกอิน) | `GET /equipment/`, `/equipment/<id>/` | `EquipmentList/DetailView` | IsAuthenticated | (ครอบใน flow) |
| B-3 | เจ้าหน้าที่จัดการรุ่น/หมวด | `.../staff/equipment[-categories]/...` | `StaffEquipment*`, `StaffCategory*` | IsStaffUser | `test_staff_add_unit_and_category_and_penalty_settings` |
| B-4 | จัดการชิ้น (unit) + กันแก้สถานะมั่ว | `.../staff/units/<id>/` | `StaffEquipmentUnitDetailView` | IsStaffUser + guard สถานะ | `test_unit_status_guard` |
| C-1 | นักศึกษาจอง (1 คน 1 รายการ) | `POST /bookings/` | `MyBookingListCreateView` | IsStudentUser + `create_booking()` | `test_full_flow...`, `test_same_student_cannot_double_book_same_model`, `test_out_of_stock_rejected`, `test_invalid_dates_rejected` |
| C-2 | ยกเลิก/ลบ/เคลียร์ประวัติ | `POST /bookings/<id>/cancel/` ฯลฯ | `MyBookingCancel/Delete/HistoryClear` | IsStudentUser + owner check | `test_cancel_returns_unit_to_stock`, `test_student_cannot_cancel_others_booking` |
| D-1 | ค้นด้วย QR (อ่านอย่างเดียว) | `GET /staff/bookings/lookup/` | `StaffBookingLookupView` | IsStaffUser + read-only | `test_qr_lookup_does_not_change_status` |
| D-2 | ยืนยันรับ | `POST /staff/bookings/<id>/confirm-pickup/` | `StaffConfirmPickupView` | IsStaffUser + `confirm_pickup()` | `test_full_flow_book_pickup_return` |
| D-3 | ยืนยันคืน (+ชำรุด) | `POST /staff/bookings/<id>/confirm-return/` | `StaffConfirmReturnView` | IsStaffUser + `confirm_return()` | `test_cannot_confirm_return_before_pickup`, `test_return_on_time_no_penalty` |
| E-1 | log การแจ้งเตือน | `GET /staff/notifications/` | `StaffNotificationListView` | IsStaffUser | `test_email_failure_is_logged_not_raised` |
| F-1 | ตั้งค่าบทลงโทษ | `GET/PATCH /staff/penalty-settings/` | `StaffPenaltySettingsView` | IsStaffUser | `test_threshold_setting_is_respected` |
| F-2 | พักสิทธิ์อัตโนมัติเมื่อคืนช้า | (เกิดใน `confirm_return`) | `services.py:207-219` | — | `test_late_return_suspends_student_and_sends_emails`, `test_still_suspended_before_end_date` |
| F-3 | ปลดพักสิทธิ์ (เจ้าหน้าที่/อัตโนมัติ) | `POST /staff/students/<id>/unsuspend/` | `StaffUnsuspendStudentView` | IsStaffUser | `test_staff_can_unsuspend`, `test_suspension_lifts_on_return_date_and_by_job` |
| F-4 | จัดการ/นำเข้านักศึกษา | `.../staff/students/...`, `/import/` | `StaffStudent*View` | IsStaffUser | `test_staff_create_and_import_students` |
| G-1 | สรุปภาพรวม | `GET /staff/dashboard-summary/` | `StaffDashboardSummaryView` | IsStaffUser | `test_dashboard_summary_counts` |
| —  | no-show ยกเลิกอัตโนมัติ | (scheduler) | `jobs.py` | — | `test_no_show_is_cancelled_and_stock_restored`, `test_picked_up_booking_not_cancelled_by_job` |
| —  | อีเมลเตือนรายวัน กันซ้ำ | (scheduler) | `jobs.py` | — | `test_daily_job_reminders_overdue_and_no_duplicates`, `test_due_soon_and_due_today_reminders` |

## 9.2 Security Requirements → เทสต์

| SR | สรุป | ยืนยันด้วยเทสต์ |
|:---:|------|-----------------|
| SR-1 | ต้องยืนยันตัวตนก่อนเข้าถึง | `test_anonymous_blocked_but_public_equipment_open` |
| SR-2 | แยกสิทธิ์ตามบทบาท | `test_student_cannot_use_staff_endpoints`, `test_staff_cannot_book` |
| SR-2 | superuser เป็น staff เสมอ | `test_createsuperuser_gets_staff_role` |
| SR-7 | ไม่เปิดเผยว่าบัญชีมีอยู่ | `test_login_wrong_password`, `test_reset_link_uses_request_host_when_url_not_set` |
| SR-8 | seed บัญชีจาก env ไม่ทับของเดิม/ไม่สร้างถ้าไม่มี env | `test_ensure_superuser_creates_once_and_never_overwrites`, `test_ensure_superuser_skips_without_env`, `test_ensure_user_creates_regular_student_once` |
| SR-10 | สถานะเปลี่ยนแบบ atomic + owner check | `test_qr_lookup_does_not_change_status`, `test_student_cannot_cancel_others_booking`, `test_unit_status_guard` |

> รวมเทสต์ **49 เคส ผ่านทั้งหมด** — ทุกแถวข้างบนมีหลักฐานการทดสอบ ครอบคลุม functional + security
