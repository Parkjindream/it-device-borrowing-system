# หมายเหตุโมดูล C (การจอง) + D (รับ-คืน) + F (บทลงโทษ)

## รายการ Endpoint ทั้งหมดที่เพิ่มเข้ามาในขั้นนี้

### ฝั่งนักศึกษา
| Method | URL | ทำอะไร |
|---|---|---|
| GET | `/api/bookings/` | ดูประวัติ/รายการจองของตัวเอง |
| POST | `/api/bookings/` | จองอุปกรณ์ใหม่ — ส่ง `{equipment_id, start_date, end_date}` |
| POST | `/api/bookings/<id>/cancel/` | ยกเลิกการจอง (ทำได้แค่ตอนสถานะ "รอรับของ") |

### ฝั่งเจ้าหน้าที่
| Method | URL | ทำอะไร |
|---|---|---|
| GET | `/api/staff/bookings/?status=&search=` | ดูคิวงานทั้งหมด กรอง/ค้นหาได้ |
| GET | `/api/staff/bookings/lookup/?code=BK-XXXX` | **สแกน QR แล้วดึงข้อมูลมาแสดง** (ไม่เปลี่ยนสถานะใดๆ) |
| POST | `/api/staff/bookings/<id>/confirm-pickup/` | เจ้าหน้าที่กดยืนยันส่งมอบของจริง |
| POST | `/api/staff/bookings/<id>/confirm-return/` | เจ้าหน้าที่กดยืนยันรับของคืนจริง |
| POST | `/api/staff/students/<id>/unsuspend/` | ปลดพักสิทธิ์ก่อนกำหนด (กรณีพิเศษ) |

## Flow การสแกน QR ที่ต้องเข้าใจให้ตรงกับเอกสาร

```
นักศึกษาโชว์ QR (booking_code) ที่หน้าจอมือถือ
        ↓
เจ้าหน้าที่สแกน → เรียก GET /staff/bookings/lookup/?code=...
        ↓
ระบบ "แค่" แสดงข้อมูล: ชื่อนักศึกษา, อุปกรณ์, สถานะปัจจุบัน ขึ้นจอเจ้าหน้าที่
        ↓
เจ้าหน้าที่ตรวจสอบตัวจริง (หน้าคน + สภาพอุปกรณ์) ด้วยสายตา
        ↓
เจ้าหน้าที่กดปุ่ม "ยืนยัน" บนหน้าจอ → เรียก POST .../confirm-pickup/ (หรือ confirm-return/)
        ↓
ตรงนี้เท่านั้นที่สถานะจะเปลี่ยนจริงในฐานข้อมูล
```

การแยกขั้น "ดู" กับ "ยืนยัน" ออกจากกันเป็น 2 endpoint คนละตัว คือหัวใจของกฎ
"สแกน QR ≠ ยืนยันอัตโนมัติ" — ถ้าจะมี bug ในโปรเจกต์นี้ จุดนี้คือจุดที่ห้ามพลาดที่สุด

## บทลงโทษ (โมดูล F) ผูกอยู่ที่ไหน

ไม่ได้แยกเป็น endpoint ของตัวเอง แต่คำนวณอัตโนมัติ**ทันทีที่เจ้าหน้าที่กด
confirm-return** ในไฟล์ `services.py` ฟังก์ชัน `confirm_return()`:
- เทียบ `วันนี้` กับ `requested_end_date` (วันครบกำหนดคืน)
- ถ้าเกิน ≥ `PenaltySettings.overdue_days_threshold` วัน → สั่งพักสิทธิ์บัญชีทันที
  (`is_suspended=True`, `suspended_until` = วันนี้ + `suspension_days`)
- เกณฑ์ทั้งสองตัวเลขนี้ปรับได้จากหน้าแอดมิน (`/admin/rental/penaltysettings/`)
  ไม่ต้องแก้โค้ด

## Scheduled Jobs (ต้องตั้งค่าเพิ่มตอน deploy จริง)

ไฟล์ `rental/jobs.py` มี 2 ฟังก์ชันที่ผูกไว้ใน `settings.CRONJOBS` แล้ว:
- `cancel_expired_bookings` — รันทุก 1 ชม. (จัดการ no-show)
- `run_daily_due_date_checks` — รันวันละครั้ง (เปลี่ยนสถานะเป็น "เกินกำหนด")

**สำคัญ**: `django-crontab` ทำงานเฉพาะบน Linux/Mac (ใช้ระบบ cron ของ OS)
ถ้า deploy บน Windows หรือ container ที่ไม่มี cron daemon ต้องใช้วิธีอื่นแทน เช่น
Celery Beat หรือตั้ง cron job ระดับ server เรียก
`python manage.py runcrons` เอง — จะแนะนำวิธีติดตั้งจริงตอนขั้น deploy

คำสั่งเปิดใช้งาน cron (รันครั้งเดียวหลัง deploy บน Linux/Mac):
```bash
python manage.py crontab add     # เพิ่ม cron job เข้าระบบ
python manage.py crontab show    # เช็คว่าเพิ่มสำเร็จ
```

## สิ่งที่ยังไม่ทำในขั้นนี้ (รอโมดูล E)

`run_daily_due_date_checks()` เปลี่ยนสถานะให้แล้ว แต่ **ยังไม่ส่งอีเมล**
แจ้งเตือนใกล้ครบกำหนด/ถึงกำหนด/เกินกำหนด — จะเพิ่มโค้ดส่งอีเมลเข้าไปใน
ฟังก์ชันนี้ตอนทำโมดูล E ในขั้นตอนถัดไป (มี field `last_reminder_sent_date`
เตรียมไว้ในตาราง Booking แล้วเพื่อกันส่งซ้ำ)

## วิธีทดสอบด้วย curl (หลังตั้งระบบเสร็จตาม 7 ขั้นตอนก่อนหน้า)

```bash
# 1. login เป็นนักศึกษา ได้ token มา
curl -X POST http://127.0.0.1:8000/api/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email":"student@example.com","password":"xxxx"}'

# 2. จองอุปกรณ์ (ใส่ token ที่ได้จากขั้น 1)
curl -X POST http://127.0.0.1:8000/api/bookings/ \
  -H "Authorization: Token <TOKEN>" -H "Content-Type: application/json" \
  -d '{"equipment_id":1,"start_date":"2026-09-27","end_date":"2026-09-30"}'

# 3. login เป็นเจ้าหน้าที่ แล้วค้นรายการจองด้วย booking_code ที่ได้จากขั้น 2
curl -H "Authorization: Token <STAFF_TOKEN>" \
  "http://127.0.0.1:8000/api/staff/bookings/lookup/?code=BK-XXXXXXXXXX"

# 4. เจ้าหน้าที่ยืนยันส่งมอบ
curl -X POST http://127.0.0.1:8000/api/staff/bookings/<id>/confirm-pickup/ \
  -H "Authorization: Token <STAFF_TOKEN>" -H "Content-Type: application/json" \
  -d '{"condition_note":"สภาพดี"}'
```
