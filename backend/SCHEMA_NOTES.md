# หมายเหตุการออกแบบฐานข้อมูล — ขั้นที่ 1

## ความสัมพันธ์หลัก (ER โดยย่อ)

```
User (นักศึกษา/เจ้าหน้าที่)
  └─ is_suspended, suspended_until          ← สถานะบัญชีผู้ใช้ (3.3)

EquipmentCategory
  └─ Equipment (รุ่น เช่น "โน้ตบุ๊ก Dell")
        └─ EquipmentUnit (ชิ้นจริง มี serial_number)
              └─ status: available/reserved/borrowed/disabled   ← สถานะอุปกรณ์ย่อย (3.1)

Booking (1 แถว = 1 การยืม 1 unit โดย 1 student)
  ├─ student      → FK User
  ├─ unit         → FK EquipmentUnit (ชิ้นที่ถูกจองจริง ไม่ใช่แค่ "รุ่น")
  ├─ status        ← สถานะการจอง (3.2)
  └─ NotificationLog (log การส่งอีเมลทุกครั้ง)

PenaltySettings  ← ตั้งค่าเกณฑ์ (singleton, แก้ผ่านแอดมินได้ ไม่ต้องแก้โค้ด)
```

## ทำไมจอง "unit" ไม่ใช่จอง "equipment" เฉยๆ

เอกสารระบุว่าอุปกรณ์แต่ละ**ชิ้น**มีสถานะย่อยของตัวเอง (ว่าง/ถูกจอง/ถูกยืมอยู่/ปิดใช้งาน)
ถ้า Booking ผูกกับ Equipment (รุ่น) เฉยๆ จะไม่รู้ว่า "ชิ้นไหน" ถูกส่งมอบไปจริง
ทำให้ตรวจสภาพ/ประวัติการซ่อมย้อนหลังต่อชิ้นไม่ได้ จึงผูก Booking กับ `EquipmentUnit`
โดยตรง ส่วน "จำนวนคงเหลือ" ของ Equipment คำนวณสดจาก
`COUNT(units WHERE status='available')` เสมอ ไม่เก็บเป็นตัวเลขค้างไว้
(กัน bug กรณีตัวเลขไม่ตรงกับของจริง)

## จุดที่ต้องระวัง Race Condition (สำคัญที่สุด)

เอกสารข้อ 4 ขั้นตอนที่ 5 ระบุว่าต้อง "ตรวจสอบอีกครั้งว่าของยังเหลือจริง" ตอนกดยืนยันจอง
เพื่อกันสองคนจองพร้อมกันแล้วได้ของชิ้นเดียวกันซ้อน วิธีที่ถูกต้องคือ
ใช้ `select_for_update()` ภายใน `transaction.atomic()` (จะเขียนจริงใน `services.py`
ตอนทำโมดูล C แต่โครง logic เป็นแบบนี้):

```python
from django.db import transaction
from rental.models import EquipmentUnit, Booking

def create_booking(student, equipment, start_date, end_date):
    with transaction.atomic():
        # ล็อกแถวที่จะแก้ไว้ก่อน กันคนอื่นอ่าน/แก้พร้อมกัน
        unit = (
            EquipmentUnit.objects
            .select_for_update(skip_locked=True)
            .filter(equipment=equipment, status=EquipmentUnit.Status.AVAILABLE)
            .first()
        )
        if unit is None:
            raise NoAvailableUnitError("ของหมด")

        unit.status = EquipmentUnit.Status.RESERVED
        unit.save(update_fields=["status", "updated_at"])

        booking = Booking.objects.create(
            student=student,
            unit=unit,
            requested_start_date=start_date,
            requested_end_date=end_date,
            booking_expires_at=...,  # now + PenaltySettings.booking_expire_hours
        )
        return booking
```

`skip_locked=True` ทำให้ query ข้ามแถวที่กำลังถูกล็อกโดย transaction อื่น
แทนที่จะรอ — สองคนกดพร้อมกันจะได้ unit คนละชิ้นโดยอัตโนมัติ ไม่ error

หลักการเดียวกันนี้ต้องใช้ทุกจุดที่เปลี่ยนสถานะ unit:
- ยกเลิกจอง (คืน status เป็น available)
- No-show (คืน status เป็น available)
- ยืนยันรับของ (reserved → borrowed)
- ยืนยันรับคืน (borrowed → available หรือ disabled ถ้าชำรุด)

## สถานะบัญชีผู้ใช้ไม่ใช่ boolean เดียวพอ

ใช้ `is_suspended` + `suspended_until` แยกกัน (ไม่ใช้ enum เดียว) เพราะ:
- `is_suspended` ใช้เช็คเร็วๆ ตอนจอง (index ได้)
- `suspended_until` ใช้แสดงผล "ถูกพักสิทธิ์ถึงวันที่..." ในหน้าโปรไฟล์ (ข้อ F)
- Scheduled job วันละครั้งจะ query `is_suspended=True AND suspended_until < today`
  แล้วเซ็ต `is_suspended=False` อัตโนมัติ

## ป้องกันอีเมลแจ้งเตือนซ้ำในวันเดียวกัน

Scheduled job แจ้งเตือนรันได้หลายรอบเผื่อ fail ซ้ำ จึงมีฟิลด์
`Booking.last_reminder_sent_date` กัน — เช็คก่อนส่งทุกครั้งว่า
`last_reminder_sent_date != today` ถึงจะส่งจริงแล้วอัปเดตวันที่

## ขั้นตอนถัดไปที่แนะนำ

1. รัน `pip install -r requirements.txt` และตั้งค่า PostgreSQL จริงใน `.env`
   (คัดลอกจาก `.env.example`)
2. `python manage.py makemigrations rental && python manage.py migrate`
3. `python manage.py createsuperuser` แล้วลองเข้า `/admin/` เพื่อยืนยันว่า
   models ทำงานถูกต้องก่อนเริ่มเขียน API จริง
4. ขั้นที่ 2 (แผนเดิม): เขียน Serializers + ViewSets สำหรับโมดูล A (Auth) และ
   โมดูล B (Inventory) ก่อน เพราะโมดูลอื่นต้องพึ่งพา endpoint พวกนี้
