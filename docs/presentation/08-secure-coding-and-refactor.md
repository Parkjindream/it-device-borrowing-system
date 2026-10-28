# 8. Secure Coding และการ Refactor (อ้างอิงตามหลักการ)

## 8.1 Secure Coding — จุดที่ทำจริง อ้างหลักการ OWASP / CWE

| หลักการ (OWASP Top 10 / CWE) | สิ่งที่ทำในโค้ด | ไฟล์:บรรทัด |
|------------------------------|-----------------|-------------|
| **A03 Injection / CWE-89 (SQLi)** | ใช้ Django ORM ล้วน ทุก query เป็น parameterized ไม่มี raw SQL/ string concatenation; ล็อกแถวด้วย `select_for_update(skip_locked=True)` | `services.py:93-99` (ทั้งไฟล์ไม่มี `.raw()`) |
| **A07 Auth Failures / CWE-307 (brute-force)** | จำกัดความถี่ด้วย `ScopedRateThrottle`: login 20/min, reset request/confirm 10/hr, public 120/min | `settings.py:159-166`, `views.py` (LoginView/PasswordReset*) |
| **A07 / CWE-256,916 (เก็บรหัสผ่าน)** | แฮชด้วย PBKDF2-SHA256 ของ Django (`set_password`/`check_password`); บัญชีที่ยังไม่ตั้งรหัสใช้ `set_unusable_password()` | `views.py:144,147,211`; `serializers.py` |
| **CWE-521 (นโยบายรหัสผ่าน)** | เปิด password validators 4 ตัว (ความยาว/ซ้ำข้อมูลผู้ใช้/รหัสนิยม/ตัวเลขล้วน) + `min_length=8` | `settings.py:105-110` |
| **A01 Broken Access Control / CWE-862** | default `IsAuthenticated` + permission class แยกบทบาท | `settings.py:156`, `permissions.py` |
| **A01 / CWE-639 (IDOR)** | queryset ของนักศึกษา filter เฉพาะของตัวเอง; ยกเลิก/ลบ booking ของคนอื่นไม่ได้ | `views.py` (My* views), test `test_student_cannot_cancel_others_booking` |
| **CWE-915 (Mass Assignment)** | serializer whitelist ฟิลด์; `email`/`role` ควบคุมฝั่งเซิร์ฟเวอร์; หลาย serializer ตั้ง `read_only_fields = fields` | `serializers.py` (ProfileUpdateSerializer), `views.py` (StaffStudentDetailView) |
| **A04 / CWE-434 (อัปโหลดไฟล์)** | จำกัดขนาดรูป ≤ 5MB + ตรวจชนิดด้วย Pillow/`ImageField` | `serializers.py` `validate_image`/`validate_profile_image` |
| **A01 Enumeration / CWE-203** | login ตอบข้อความกลาง; password-reset ตอบเหมือนกันเสมอ ไม่บอกว่าอีเมลมีจริง และไม่ log ลิงก์ | `views.py:180,183-184`; `serializers.py` |
| **CWE-798 (hardcoded secret)** | ความลับอ่านจาก `.env` ด้วย `python-decouple`; กันบูต production ด้วยคีย์ตัวอย่าง | `settings.py:13-19`; `.gitignore` (.env ไม่ถูก track) |
| **A05 Misconfiguration — security headers** | Django `SecurityMiddleware` (`X-Content-Type-Options`, `Referrer-Policy`) + `XFrameOptionsMiddleware` (`SAMEORIGIN`) | `settings.py:59,68` (`SECURE_REFERRER_POLICY`, `X_FRAME_OPTIONS`) |
| **ลดพื้นที่โจมตี** | `/api/admin/` ไม่ถูกเปิด (404) เมื่อ `ENABLE_DJANGO_ADMIN=False`; `/media/` อนุญาตเฉพาะ GET/HEAD ไม่ส่งสิทธิ์ใดต่อไป MinIO; dashboard เช็คล็อกอิน/role ฝั่งเซิร์ฟเวอร์ | `config/urls.py`; `frontend/decorators.py` |
| **CWE-613 (session/token)** | เปลี่ยน/รีเซ็ตรหัสผ่านเพิกถอน token เดิม บังคับ login ใหม่ | `views.py:150-153,213` |
| **Repudiation / audit** | บันทึกการส่งอีเมลทุกครั้งใน `NotificationLog` (สำเร็จ/ล้มเหลว); `on_delete=PROTECT` รักษาประวัติการยืม | `models.py:332-356,259,262` |
| **Resilience (เมลล่ม)** | ชั้นอีเมลกลืน exception ไม่ให้ล้ม request + บันทึกเหตุผล | `notifications.py` |

> ทุก control ข้างต้นมีเทสต์อัตโนมัติรองรับ ดูแผนที่ requirement → control → test ใน [09-traceability-matrix.md](09-traceability-matrix.md)

## 8.2 การ Refactor — เพิ่มเครื่องมือบังคับมาตรฐาน (ทำจริงในเฟสนี้)

**ปัญหา:** โปรเจกต์ไม่มี linter/formatter บังคับ ทำให้ code ที่ไม่ตรงมาตรฐาน PEP 8 หลุดเข้ามาได้

**สิ่งที่ทำ:**
1. เพิ่มการตั้งค่า **`ruff`** ที่ `backend/pyproject.toml` — เลือกกฎ `E, W, F, I, UP` (PEP 8 + จับ bug + เรียง import + ไวยากรณ์รุ่นใหม่), `line-length = 120`
2. รัน `ruff check . --fix` แก้อัตโนมัติ **21 จุด**:
   - `I001` เรียงลำดับ import ให้เป็นระเบียบ (10 จุด)
   - `W292` เติม newline ท้ายไฟล์ (10 จุด)
   - `F401` ลบ import ที่ไม่ได้ใช้ (`send_mail` ใน `views.py`) — **เป็น dead code ที่ linter จับได้ก่อนถึงรีวิว**
3. แก้ **`E501` บรรทัดยาวเกิน 120** ด้วยมือ **12 จุด** (ตัดบรรทัดให้อ่านง่ายขึ้น ไม่เปลี่ยนตรรกะ) ในไฟล์ `urls.py`, `serializers.py`, `tests.py`, `run_scheduler.py`
4. เพิ่ม **lint job ใน CI** (`.github/workflows/ci.yml`) ให้ทุก push/PR ถูกตรวจอัตโนมัติ ป้องกันปัญหาเดิมเกิดซ้ำ

**ผลลัพธ์ (ยืนยันแล้ว):**
```bash
$ cd backend && ruff check .
All checks passed!

$ python manage.py test
Ran 38 tests ... OK      # refactor ไม่กระทบพฤติกรรม เทสต์ผ่านครบเหมือนเดิม
```

**หลักการที่ยึดตอน refactor:** แก้เฉพาะเรื่อง "รูปแบบ/ความสะอาด" ที่ปลอดภัย (formatting, dead code, import order) — **ไม่แตะ business logic** จึงมีเทสต์ 38 เคสเป็นตาข่ายนิรภัยยืนยันว่าพฤติกรรมเหมือนเดิมทุกประการ (red-green-refactor: โค้ดเขียว → refactor → ยังเขียว)
