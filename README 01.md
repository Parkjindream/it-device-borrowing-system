# ระบบยืม-คืนอุปกรณ์ไอที — คู่มือโปรเจกต์ฉบับเต็ม

ทั้งระบบเป็นโปรเจกต์ Django เดียวในโฟลเดอร์ **`backend/`** (Django + Django REST Framework + PostgreSQL):
- **`backend/rental/`** — REST API ทั้งหมด อยู่ใต้ `/api/`
- **`backend/frontend/`** — หน้าเว็บ (Django templates + Tailwind CSS + JavaScript) อยู่ที่ `/`
  - `templates/frontend/` หน้าเว็บทุกหน้า (`base.html` + `partials/` ที่ใช้ร่วมกัน)
  - `static/frontend/` css/js/รูป/ฟอนต์ — Django เสิร์ฟเองด้วย WhiteNoise
  - หน้าแรก render รายการอุปกรณ์ฝั่งเซิร์ฟเวอร์, หน้า dashboard เช็คล็อกอิน/role ฝั่งเซิร์ฟเวอร์ก่อนส่งหน้า
    ส่วนที่โต้ตอบใน dashboard (จอง/รับ-คืน/จัดการคลัง/สถิติ) เป็น JavaScript เรียก REST API

ล็อกอินครั้งเดียวได้ทั้ง token (JS ใช้เรียก API) และ session cookie (ใช้เปิดหน้า dashboard)

| URL | หน้า |
|---|---|
| `/` | หน้าแรก |
| `/login/`, `/forgot-password/`, `/reset-password/`, `/set-password/` | เข้าสู่ระบบ / ลืมรหัสผ่าน |
| `/student/` | หน้าหลักนักศึกษา (ต้องล็อกอินเป็นนักศึกษา) |
| `/staff/` | แผงควบคุมเจ้าหน้าที่ (ต้องล็อกอินเป็นเจ้าหน้าที่) |
| `/api/...` | REST API |

ลิงก์แบบเดิม (`login.html`, `reset-password.html?uid=..`, `staff/dashboard.html` ฯลฯ) เด้งไป URL ใหม่ให้อัตโนมัติ

---

## 0) สิ่งที่แก้ไข/เพิ่มในรอบล่าสุด (สรุปให้เห็นภาพ)

> **ถ้าอัปเดตโค้ดจากรอบก่อนหน้า ต้องรันคำสั่งนี้ก่อนเสมอ** (มีการเพิ่มค่าใน enum ของ NotificationLog):
> ```bash
> python manage.py makemigrations rental
> python manage.py migrate
> ```

**บั๊กที่แก้แล้ว:**
- **ลืมรหัสผ่านใช้ไม่ได้เมื่อทดสอบซ้ำหลายรอบ** — สาเหตุคือ endpoint "ขอลิงก์" กับ "ยืนยันรหัสใหม่"
  เดิมใช้โควต้าจำกัดจำนวนครั้งร่วมกัน (throttle 5 ครั้ง/ชั่วโมงต่อ IP) ทำให้โดนบล็อกเงียบๆ ตอนทดสอบสลับไปมา
  แก้แยกโควต้าออกจากกันแล้ว (10 ครั้ง/ชั่วโมง ต่อ endpoint) และแปลข้อความ error เป็นไทยให้เข้าใจง่ายขึ้น
  ถ้ายังไม่ได้อีเมล เช็ค log ฝั่ง backend terminal ได้เลย (มี log บอกว่าหาบัญชีเจอไหม/ส่งอีเมลสำเร็จไหม)
  หรือดูประวัติผ่าน `/api/staff/notifications/`
- **บั๊กร้ายแรงที่พบระหว่างตรวจโค้ด (ยังไม่ทันมีคนเจอ):** ฟังก์ชัน `debounce()` เดิมอยู่ในไฟล์ที่หน้า
  เจ้าหน้าที่ไม่ได้โหลด จะทำให้ **หน้าแดชบอร์ดเจ้าหน้าที่พังทั้งหน้าไม่โหลดอะไรเลย** ทันทีที่เปิดแท็บ
  "จัดการนักศึกษา" — แก้โดยย้ายฟังก์ชันนี้ไปไว้ในไฟล์ที่ทุกหน้าโหลดร่วมกันแล้ว
- **"Cannot GET /login.html" ตอน logout** — เกิดจาก JS ใช้ path แบบ `/login.html` (absolute) ซึ่งจะพังถ้า
  เว็บเซิร์ฟเวอร์ไม่ได้รันจากในโฟลเดอร์ `frontend/` เป๊ะ ๆ (เช่นเปิดทั้งโปรเจกต์ด้วย VS Code Live Server)
  แก้เป็น path แบบสัมพัทธ์ทั้งหมดแล้ว ใช้ได้ไม่ว่าจะรันจากไหน
- **หน้าจอไม่แสดง "เกินกำหนด"** — เดิม frontend อ่านสถานะดิบจากฐานข้อมูล (`status`) ซึ่งจะเปลี่ยนเป็น
  `overdue` ก็ต่อเมื่อ scheduled job รันไปแล้วเท่านั้น (ไม่ใช่เรียลไทม์) ทั้งที่ backend มีการคำนวณ
  "เกินกำหนดจริงหรือยัง" แบบสดอยู่แล้ว (`is_overdue_now`) แก้ให้ frontend ใช้ค่านี้แสดงป้ายสถานะเสมอ
- ตอนแรก `EquipmentUnit` serializer บังคับให้ต้องส่ง field `equipment` เองตอนเพิ่มเครื่องใหม่ ทั้งที่
  ควรตั้งจาก URL อัตโนมัติ — แก้แล้ว
- `createsuperuser` เดิมสร้างบัญชีเป็น "นักศึกษา" โดยไม่ได้ตั้งใจ (เพราะ role default ในโมเดลคือ student)
  แก้ให้ `createsuperuser` ตั้งเป็น "เจ้าหน้าที่" (staff) ให้ถูกต้องเสมอ

**เพิ่มใหม่:**
- แก้ไขโปรไฟล์ตัวเอง (ชื่อ-นามสกุล) + เปลี่ยนรหัสผ่าน จากหน้านักศึกษาได้แล้ว (`PATCH /api/auth/me/`,
  `POST /api/auth/change-password/`)
- อีเมลแจ้งเตือนครบทุกจุดที่ควรมี: จองสำเร็จ, **รับของสำเร็จ (ใหม่)**, เตือนก่อนครบกำหนด 1 วัน,
  เตือนถึงวันครบกำหนด, เตือนซ้ำรายวันตอนเกินกำหนด (พร้อมบอกกติกาบทลงโทษจริงจากค่าที่แอดมินตั้งไว้),
  แจ้งพักสิทธิ์, แจ้งคืนสำเร็จ, แจ้งยกเลิกอัตโนมัติ — ดูประวัติอีเมลทั้งหมดได้ที่ `/api/staff/notifications/`
- เจ้าหน้าที่ตั้งค่าเกณฑ์บทลงโทษเองได้ผ่าน API (`/api/staff/penalty-settings/`) ไม่ต้องแก้โค้ด
- เจ้าหน้าที่เพิ่ม/นำเข้านักศึกษาได้ผ่าน API (`/api/staff/students/`, `/api/staff/students/import/`)
- อัปโหลดรูปอุปกรณ์ได้จริงตอนเพิ่ม/แก้ไขรุ่นอุปกรณ์ ถ้ายังไม่มีรูป frontend จะโชว์ภาพประกอบสำเร็จรูป
  ให้แทน (เดาจากชื่อรุ่น: โน้ตบุ๊ก/iPad/ESP32/ESP8266/Raspberry Pi/Arduino) ที่ `backend/frontend/static/frontend/img/products/`
- หน้าแรกดึงรายการอุปกรณ์จริงจากระบบมาโชว์ (endpoint สาธารณะ ไม่ต้องล็อกอิน) พร้อมภาพประกอบ
- ปรับชุดข้อมูลตัวอย่าง (`seed_demo_data`) ให้เหลือ 3 หมวดตามที่ต้องการ: โน้ตบุ๊ก, iPad (Gen 9/10),
  บอร์ดไมโครคอนโทรลเลอร์ (ESP32, ESP8266, Raspberry Pi 4, Arduino Uno)
- ชุดทดสอบอัตโนมัติ (`python manage.py test`) ครอบคลุมทุกกระบวนการหลัก
- **Docker** สำหรับ deploy จริง (ดูหัวข้อ 5)

---

## 1) ติดตั้งและรัน (สำหรับพัฒนา/ทดสอบบนเครื่องตัวเอง)

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows PowerShell: .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

cp ../.env.example ../.env      # .env ไฟล์เดียวที่รากโปรเจกต์ (ใช้ร่วมกับ docker) — ตั้ง DEBUG=True, SECURE_COOKIES=False

# สร้างฐานข้อมูล PostgreSQL ก่อน (ถ้ายังไม่มี)
# psql -U postgres -c "CREATE DATABASE it_lending_db;"
# หรือไม่ต้องลง PostgreSQL/MinIO เอง: ยกเฉพาะ infra จาก docker (รันที่โฟลเดอร์รากโปรเจกต์ ต้องมี .env ที่รากก่อน — หัวข้อ 5)
#   docker compose -f docker-compose.infra.yml up -d
#   runserver ต่อ PostgreSQL ที่ localhost:DB_EXPOSE_PORT และ MinIO ที่ localhost:MINIO_API_PORT ให้เองจาก .env เดียวกัน
#   ครั้งแรกรัน python manage.py ensure_media_bucket เพื่อสร้าง bucket

python manage.py testflight             # เช็คว่าต่อฐานข้อมูล + ที่เก็บไฟล์ (S3/MinIO) ได้จริง
python manage.py makemigrations rental
python manage.py migrate
python manage.py createsuperuser        # จะได้บัญชี role "เจ้าหน้าที่" อัตโนมัติ

python manage.py seed_demo_data         # ข้อมูลตัวอย่างสำหรับทดสอบ (ดูหัวข้อ 3)

python manage.py runserver
```

## 2) เปิดหน้าเว็บ

`runserver` ตัวเดียวเสิร์ฟทั้งหน้าเว็บและ API — เปิดเบราว์เซอร์ไปที่ `http://127.0.0.1:8000/` ได้เลย
(ไม่ต้องรัน `http.server`/Live Server/`dev_server.py` แยกอีกแล้ว และไม่มีปัญหา CORS)

แก้ CSS: แก้ที่ `backend/frontend/src/styles.css` แล้วคอมไพล์ด้วย Tailwind CLI จากโฟลเดอร์ `backend/frontend/`
```bash
cd backend/frontend
npx tailwindcss@3 -i src/styles.css -o static/frontend/css/style.css --minify
```

## 3) ข้อมูลตัวอย่างสำหรับทดสอบ (`seed_demo_data`)

```bash
python manage.py seed_demo_data            # เพิ่มข้อมูล (เรียกซ้ำได้ ไม่สร้างซ้ำ)
python manage.py seed_demo_data --reset    # ลบอุปกรณ์/การจองเดิมทั้งหมดก่อน แล้วสร้างชุดใหม่ (ไม่ลบบัญชีผู้ใช้)
```

สร้างให้อัตโนมัติ:
- 3 หมวดหมู่: โน้ตบุ๊ก, แท็บเล็ต (iPad), บอร์ดไมโครคอนโทรลเลอร์
- 9 รุ่นอุปกรณ์: โน้ตบุ๊ก 3 รุ่น, iPad Gen 9/10, ESP32, ESP8266, Raspberry Pi 4, Arduino Uno
บัญชีเทส:
- บัญชีเจ้าหน้าที่ 1 คน: `staff01@example.ac.th`
- บัญชีนักศึกษา 3 คน: `student01@example.ac.th`, `student02@...`, `student03@...`
- **รหัสผ่านทุกบัญชี:** `------`

> **คำเตือน:** สำหรับทดสอบเท่านั้น ห้ามรันกับฐานข้อมูลจริง และเปลี่ยนรหัสผ่านทุกบัญชีก่อนใช้งานจริงเสมอ

## 4) การรันงานอัตโนมัติ (สำคัญมาก — อ่านหัวข้อนี้ให้เข้าใจ)

ระบบมี 2 งานที่ต้อง "ถูกสั่งรัน" เป็นระยะ ไม่ได้รันอัตโนมัติเองตอน `runserver`:

| งาน | ทำอะไร | ควรรันถี่แค่ไหน |
|---|---|---|
| ยกเลิกการจองที่ไม่มารับ (no-show) | คืนอุปกรณ์เป็น "ว่าง" อัตโนมัติ | ทุก 15-60 นาที |
| ตรวจวันครบกำหนด | ปลดพักสิทธิ์ที่ครบกำหนด, เปลี่ยนสถานะเป็น "เกินกำหนด", ส่งอีเมลเตือน | วันละครั้ง |

**ตอนพัฒนา/ทดสอบบนเครื่องตัวเอง** เปิด terminal ใหม่อีกอัน (แยกจาก `runserver`) แล้วรัน:

```bash
python manage.py run_scheduler
```

จะรันค้างไว้ตลอด เช็ค no-show ทุก 15 นาที และรันงานรายวันหลัง 07:00 น. ให้อัตโนมัติ

**ถ้าอยากทดสอบทันทีโดยไม่ต้องรอ** (เช่นกรณีที่คุณเจอ: ยืมเกินกำหนดแล้วอยากเห็นผลทันที) ใช้:

```bash
python manage.py run_scheduler --once
```

รันทุกงานแค่ 1 รอบแล้วจบ เปิด terminal ที่รัน `runserver` ดูควบคู่ไปด้วย จะเห็นอีเมล "เกินกำหนด..."
พิมพ์ออกมา และสถานะ booking จะเปลี่ยนเป็น "เกินกำหนด" จริงในฐานข้อมูลทันที (ไม่ต้องพึ่ง `is_overdue_now`
ที่ frontend คำนวณสดอีกต่อไป เพราะสถานะจริงเปลี่ยนแล้ว)

**ตอน deploy ด้วย Docker** มี container ชื่อ `scheduler` รันคำสั่งนี้ให้อัตโนมัติอยู่แล้ว ไม่ต้องทำอะไรเพิ่ม
(ดูหัวข้อ 5)

**ทดสอบว่าอีเมลถูกส่งจริงไหม:**
```bash
python manage.py send_test_email you@example.com
```
ถ้า `.env` ยังตั้ง `EMAIL_BACKEND` เป็น console (ค่าเริ่มต้น) คำสั่งนี้จะแค่พิมพ์อีเมลออกทาง terminal
ไม่ได้ส่งเข้ากล่องอีเมลจริง — ต้องตั้งค่า SMTP ก่อน (ดูคอมเมนต์ในไฟล์ `.env.example` วิธีตั้งผ่าน Gmail)
หรือดูประวัติอีเมลทั้งหมดที่ระบบพยายามส่ง (สำเร็จ/ไม่สำเร็จ) ผ่าน `/api/staff/notifications/`

## 5) Deploy จริงด้วย Docker

ต้องมี Docker และ Docker Compose ติดตั้งในเครื่อง/เซิร์ฟเวอร์ก่อน

```bash
cp .env.example .env              # แก้ค่าในไฟล์ .env ให้ครบ (รหัสผ่านทุกตัว, DJANGO_SECRET_KEY, อีเมล SMTP)
docker compose up -d --build      # สร้างตาราง + บัญชีแอดมินจาก DJANGO_SUPERUSER_* ให้อัตโนมัติ
docker compose exec backend python manage.py seed_demo_data   # ถ้าต้องการข้อมูลตัวอย่าง (ข้ามได้ถ้าจะกรอกข้อมูลจริงเอง)
```

เปิด `http://localhost/` (พอร์ตตาม `HTTP_PORT` ใน `.env`) — หน้า admin อยู่ที่ `/api/admin/` (เมื่อ `ENABLE_DJANGO_ADMIN=True`)

สิ่งที่ `docker compose up` เปิดให้ทั้งหมด (`docker-compose.yml` include `docker-compose.infra.yml` ให้เอง
— ใช้ `docker compose -f docker-compose.infra.yml up -d` ถ้าต้องการแค่ `db` + `minio`):

| service | ไฟล์ | หน้าที่ |
|---|---|---|
| `db` | infra | PostgreSQL 16 (ข้อมูลอยู่ใน volume `pgdata`) ต่อจากเครื่องเซิร์ฟเวอร์ได้ที่ `localhost:5433` |
| `minio` | infra | เก็บไฟล์อัปโหลด (รูปอุปกรณ์/รูปโปรไฟล์) ข้อมูลอยู่ที่โฟลเดอร์ `.docker-mount/minio` หน้าเว็บจัดการไฟล์ `http://localhost:9001` |
| `migrate` | หลัก | รัน migrate + สร้างแอดมิน + สร้าง bucket ใน MinIO + `testflight` ครั้งเดียวแล้วจบ (backend/scheduler รอตัวนี้ก่อน — ถ้า testflight ไม่ผ่าน backend จะไม่เริ่ม) |
| `backend` | หลัก | Django + gunicorn — ทางเข้าเดียวของเว็บ: หน้าเว็บ, API, static (WhiteNoise), `/media/` (ดึงจาก MinIO) |
| `scheduler` | หลัก | งานอัตโนมัติ (no-show, แจ้งเตือน, ปลดพักสิทธิ์) |
| `db-backup` | infra | *ปิดไว้ก่อน* — ลบ `#` ใน `docker-compose.infra.yml` เพื่อเปิด: `pg_dump` ทุกวันตี 2 ลง `./backups` เก็บ 14 วัน |
| `pgadmin` | infra | *ปิดไว้ก่อน* — ลบ `#` ใน `docker-compose.infra.yml` เพื่อเปิด แล้วเข้าที่ `http://localhost:5050` |

`db`, `minio`, `backend` ผูกพอร์ตไว้แค่ `127.0.0.1` — จากเครื่องอื่นให้ใช้ `ssh -L 5433:localhost:5433 <เซิร์ฟเวอร์>`

กู้คืนฐานข้อมูลจากไฟล์สำรอง:
```bash
docker compose stop backend scheduler
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/<ไฟล์>.dump
docker compose start backend scheduler
```

**สถาปัตยกรรมตอน deploy:** `backend container` (Django+gunicorn) เป็นทางเข้าเดียว
ผูกพอร์ตไว้ที่ `127.0.0.1:HTTP_PORT` — จะเปิดให้เครื่องอื่นเข้า ให้วาง reverse proxy (https) ไว้ข้างหน้า เสิร์ฟหน้าเว็บ (`/`), API (`/api/`), ไฟล์ static (`/static/` ผ่าน WhiteNoise บีบอัด gzip ให้)
และรูปที่อัปโหลด (`/media/` ดึงจาก MinIO) — ทุกอย่างอยู่ origin เดียวกัน **ไม่มีปัญหา CORS ทั้งตอนพัฒนาและ production**
หน้า Django admin (`/api/admin/`) ปิดไว้ตอน `DEBUG=False` (เปิดได้ด้วย `ENABLE_DJANGO_ADMIN=True` ใน `.env`)
ส่วน container `scheduler` รันงานอัตโนมัติ (no-show, แจ้งเตือน, ปลดพักสิทธิ์) แยกจากเว็บ ไม่แย่ง worker กันตอบ request

คำสั่งที่ใช้บ่อยหลัง deploy:
```bash
docker compose exec backend python manage.py testflight   # เช็คการเชื่อมต่อฐานข้อมูล + ที่เก็บไฟล์
docker compose logs -f backend      # ดู log backend (รวม error ถ้ามี)
docker compose logs -f scheduler    # ดูว่างานอัตโนมัติรันจริงไหม
docker compose exec backend python manage.py send_test_email you@example.com
docker compose down                 # หยุดทั้งหมด (ข้อมูลใน volume ยังอยู่ ไม่หาย)
docker compose up -d --build        # deploy โค้ดเวอร์ชันใหม่ทับของเดิม
```

**ก่อน deploy จริงกับข้อมูลนักศึกษาจริง ต้องทำเพิ่ม:**
1. เปลี่ยนรหัสผ่านบัญชีทดสอบทั้งหมด/ไม่รัน `seed_demo_data` กับฐานข้อมูลจริง
2. ตั้งค่า SMTP จริงใน `.env` (ไม่ใช้ console backend อีกต่อไป)
3. ตั้ง `DJANGO_SECRET_KEY` ใหม่แบบสุ่ม
4. วาง reverse proxy ที่ทำ https (ผูกโดเมนจริง) ไว้หน้า `backend` แล้วตั้งใน `.env`: `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS`/`FRONTEND_URL`
   เป็นโดเมนนั้น, `SECURE_COOKIES=True`, `USE_X_FORWARDED_PROTO=True`, `NUM_PROXIES=1`
5. นำเข้ารายชื่อนักศึกษาจริงผ่าน `/api/staff/students/import/` (ดูหัวข้อ 6) หรือทีละคนผ่าน `/api/staff/students/`
6. แทนที่ `backend/frontend/static/frontend/img/logo.png` ด้วยโลโก้จริงของวิทยาลัย (ชื่อไฟล์เดิม ~512×512px พื้นหลังโปร่งใส)
7. คัดลอกไฟล์ใน `./backups` ออกไปเก็บนอกเครื่องเซิร์ฟเวอร์สม่ำเสมอ (`db-backup` สำรองให้ทุกวันแต่อยู่เครื่องเดียวกัน ถ้าดิสก์พังก็หายด้วย)

### Deploy บน Vercel (+ Supabase)

- **Settings > Build and Deployment:** Framework = Django, Root Directory = `backend` — ไม่ต้องตั้ง Build Command
  (Vercel รัน `collectstatic` เองแล้วเสิร์ฟ `/static/` จาก CDN)
- **Settings > Environment Variables:** `DJANGO_SECRET_KEY`, `DEBUG=False`, `ALLOWED_HOSTS=.vercel.app`,
  `CSRF_TRUSTED_ORIGINS=https://*.vercel.app`, `SECURE_COOKIES=True`, `USE_X_FORWARDED_PROTO=True`,
  `DB_*` + `MINIO_ENDPOINT`/`MINIO_ACCESS_KEY`/`MINIO_SECRET_KEY` ของ Supabase, `CRON_SECRET`, ค่า SMTP
- **migrate:** Vercel ไม่รันให้ — รันจากเครื่อง (`.env` ชี้ Supabase): `python manage.py testflight && python manage.py migrate`
- **งานอัตโนมัติ:** ไม่มี container `scheduler` — `backend/vercel.json` ตั้ง Vercel Cron เรียก `/api/cron/run-jobs/`
  วันละครั้ง 07:00 เวลาไทย (แผน Hobby รันได้แค่วันละครั้ง คลาดได้ ±59 นาที) จึงยกเลิกการจองที่ไม่มารับวันละรอบ
  แทนทุก 15 นาที — ต้องการถี่กว่านี้ใช้แผน Pro แล้วแก้ `schedule` เช่น `*/15 * * * *`

## 6) นำเข้ารายชื่อนักศึกษาจริงทีละหลายคน

```bash
POST /api/staff/students/import/
{
  "students": [
    {"email": "6501234@student.ac.th", "first_name": "สมชาย", "last_name": "ใจดี", "student_id": "6501234"},
    ...
  ]
}
```
บัญชีที่สร้างจะยังไม่มีรหัสผ่าน — นักศึกษากด "ลืมรหัสผ่าน" ที่หน้า login เพื่อตั้งรหัสผ่านครั้งแรกด้วยตัวเอง
แถวที่อีเมล/รหัสนักศึกษาซ้ำหรือรูปแบบผิดจะถูกข้ามและรายงานเหตุผลกลับมาให้ (ดูใน response `errors`)

## 7) รันชุดทดสอบอัตโนมัติ

```bash
cd backend
python manage.py test
```

ครอบคลุม: จอง→รับ→คืนครบ flow, ของหมด/จองซ้ำ, บทลงโทษ (โดนโทษ/ไม่โดน/ปลดอัตโนมัติ/ปลดโดยเจ้าหน้าที่),
no-show, การแจ้งเตือนอีเมลทุกจุด (รวมกรณีอีเมลส่งไม่ได้ต้องไม่ทำให้ระบบล่ม), สิทธิ์การเข้าถึงแยก
นักศึกษา/เจ้าหน้าที่, กฎ "สแกน QR ≠ ยืนยันอัตโนมัติ", แก้โปรไฟล์/เปลี่ยนรหัสผ่าน, จัดการนักศึกษา/นำเข้า,
ตั้งค่าบทลงโทษ, และแดชบอร์ดสรุปภาพรวม

## 8) Checklist ทดสอบ end-to-end ด้วยมือ (ผ่านหน้าเว็บจริง)

- [ ] หน้าแรก `/` แสดงรายการอุปกรณ์จริงพร้อมภาพประกอบ (ไม่ต้องล็อกอิน)
- [ ] เปิด `/staff/` หรือ `/student/` โดยไม่ล็อกอิน → เด้งไปหน้า login; นักศึกษาเปิด `/staff/` → เด้งกลับ `/student/`
- [ ] Login นักศึกษา → เห็นอุปกรณ์พร้อมภาพ → จองสำเร็จ → เช็คอีเมล "จองสำเร็จ" ใน terminal backend
- [ ] กด "โปรไฟล์ของฉัน" แก้ชื่อ → บันทึกสำเร็จ → logout แล้ว login ใหม่ → ชื่อยังเป็นชื่อที่แก้ (logout แล้วเปิด `/student/` ต้องเด้งไปหน้า login)
- [ ] เปลี่ยนรหัสผ่านในหน้าโปรไฟล์ → logout → login ด้วยรหัสใหม่ได้
- [ ] Login เจ้าหน้าที่ → ค้นรหัสการจอง → ยืนยันรับของ → เช็คอีเมล "รับของสำเร็จ" ขึ้นใน terminal
- [ ] แก้วันครบกำหนดของ booking ให้เป็นวันที่ผ่านมาแล้วผ่านหน้า Django admin (`/api/admin/`) เพื่อจำลองเกินกำหนด
- [ ] รีเฟรชหน้านักศึกษา/เจ้าหน้าที่ — **ต้องเห็นป้าย "เกินกำหนด" ทันที** แม้ยังไม่รัน `run_scheduler`
- [ ] รัน `python manage.py run_scheduler --once` → เช็คอีเมล "เกินกำหนด...พักสิทธิ์..." ขึ้นใน terminal → สถานะในฐานข้อมูลเปลี่ยนเป็น overdue จริง
- [ ] ยืนยันคืนของรายการที่เกินกำหนด → เช็คว่านักศึกษาถูกพักสิทธิ์จริง (ลอง login แล้วเห็นแบนเนอร์พักสิทธิ์) + มีอีเมล "รับคืนสำเร็จ" กับ "พักสิทธิ์" ทั้งคู่
- [ ] เจ้าหน้าที่ปลดล็อกก่อนกำหนดผ่าน `/api/staff/students/<id>/unsuspend/` (หรือผ่าน Django admin) → นักศึกษาจองใหม่ได้ทันที

## 9) เอกสารประกอบเพิ่มเติม

- `backend/SCHEMA_NOTES.md` — เหตุผลการออกแบบฐานข้อมูล + วิธีกัน race condition
- `backend/BOOKING_MODULE_NOTES.md` — รายละเอียด endpoint การจอง/รับ-คืน + ตัวอย่าง curl
- `backend/rental/tests.py` — อ่านเป็นตัวอย่างว่าแต่ละ endpoint ควรถูกใช้งานยังไง

## 10) สิ่งที่ยังไม่ได้ทำ (บอกตรง ๆ เพื่อไม่ให้เข้าใจผิดว่าเสร็จ 100%)

- **การรีดีไซน์หน้าแรกแบบเทียบเท่า Apple/Wongnai เต็มรูปแบบ** — มีส่วนโชว์อุปกรณ์จริงพร้อมภาพแล้ว
  แต่ยังไม่ได้ทำ layout ใหม่ทั้งหมดแบบ full redesign ตามภาพตัวอย่างที่เคยยกมา
- ยังไม่มีการทดสอบบนอุปกรณ์มือถือจริง (ทำ responsive ไว้แต่ควรลองเปิดจากมือถือจริงอีกครั้ง)
- ยังไม่เคยรัน Docker จริงสักครั้งในสภาพแวดล้อมนี้ (ตรวจ syntax ของทุกไฟล์ Docker แล้ว แต่คุณต้องเป็นคน
  รัน `docker compose up -d --build` ทดสอบจริงเอง — ถ้าเจอ error ส่ง log มาได้เลย)

**ที่ทำครบแล้วในรอบนี้:** แก้ไขโปรไฟล์/เปลี่ยนรหัสผ่าน, จัดการนักศึกษา (เพิ่มทีละคน/นำเข้าทีละหลายคน/
ค้นหา/ปลดล็อก), ตั้งค่าเกณฑ์บทลงโทษผ่านหน้าเว็บ, จัดการหมวดหมู่อุปกรณ์ผ่านหน้าเว็บ, ดูประวัติอีเมล
ทั้งหมดผ่านหน้าเว็บ (ไม่ต้องพึ่ง Django admin หรือ curl อีกต่อไป) — ครบทุกหัวข้อที่เคยค้างไว้

บอกมาได้เลยว่าอยากให้ทำส่วนไหนต่อในรอบถัดไป (ถ้ามี)
