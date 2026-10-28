# 7. Risk Register (ทะเบียนความเสี่ยง)

เกณฑ์: Likelihood (โอกาสเกิด) × Impact (ผลกระทบ) = ระดับความเสี่ยง · L/M/H = ต่ำ/กลาง/สูง

| รหัส | ความเสี่ยง | ทรัพย์สิน | โอกาส | ผลกระทบ | ระดับ | มาตรการ / สถานะ |
|:---:|-----------|:---:|:---:|:---:|:---:|-----------------|
| R-1 | **Token ไม่มีวันหมดอายุ เก็บใน localStorage** → ถ้ามี XSS หรือเครื่องหลุด token ใช้ได้ตลอด | AS-2 | M | H | **High** | ปัจจุบัน: เพิกถอนเมื่อ logout/เปลี่ยนรหัส (`views.py:150-153`). เสนอ: กำหนด TTL + หมุน token + พิจารณา httpOnly cookie |
| R-2 | **ไม่มี Content-Security-Policy** → ลด defense-in-depth ต่อ XSS | AS-2,AS-3 | M | M | **Medium** | ปัจจุบัน: มี `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`. เสนอ: เพิ่ม `Content-Security-Policy` |
| R-3 | **`DEBUG` ค่าเริ่มต้นเป็น `True`** → ถ้าตั้ง production พลาดจะโชว์ stack trace | AS-8 | L | H | **Medium** | ป้องกันแล้วบางส่วน: ถ้า `DEBUG=False` กับคีย์ตัวอย่างระบบจะไม่ยอมบูต (`settings.py:16-19`). เสนอ: ตั้ง default เป็น `False` |
| R-4 | **ลิงก์รีเซ็ตรหัสผ่านอยู่ใน query string ของ URL** → อาจค้างใน history/log กลางทาง | AS-1 | L | M | **Low-Med** | ป้องกันแล้ว: ลิงก์ใช้ครั้งเดียว หมดอายุ 24 ชม. (`settings.py:113`), ไม่ log ลิงก์ (`views.py:180`), frontend ลบ token ออกจาก address bar |
| R-5 | **นำเข้านักศึกษาทีละมาก (สูงสุด 500 แถว/คำขอ)** → อาจถูกใช้สร้างภาระ | AS-3 | L | M | **Low-Med** | จำกัด 500/คำขอ + เฉพาะเจ้าหน้าที่ (`views.py`). เสนอ: จำกัดความถี่เพิ่มถ้าจำเป็น |
| R-6 | **ไม่มี HSTS / SSL redirect ในแอป** (TLS จบที่ Cloudflare) | AS-2 | L | M | **Low-Med** | ตั้ง secure cookie ได้ผ่าน env; เสนอ: เปิด HSTS เมื่อใช้โดเมนจริง (named tunnel) |
| R-7 | **Quick Tunnel ได้ URL สุ่ม ไม่มี SLA + มีป้ายเตือน** | ทั้งระบบ | H | L | **Medium** | เหมาะกับสาธิตเท่านั้น. เสนอ: เปลี่ยนเป็น named tunnel + โดเมนจริง (มีคอมเมนต์เตรียมไว้ใน `docker-compose.yml`) |
| R-8 | **ไฟล์สำรอง/`.env` หลุดสู่ public repo** | AS-7,AS-8 | L | H | **Medium** | ป้องกันแล้ว: ทั้งคู่อยู่ใน `.gitignore` และยืนยันว่าไม่ถูก track; มีเฉพาะไฟล์ `*.example` | 
| R-9 | **ไม่มีการเข้ารหัสไฟล์สำรองฐานข้อมูล** | AS-7 | L | H | **Medium** | เสนอ: เข้ารหัสไฟล์ backup + จำกัดสิทธิ์โฟลเดอร์ |
| R-10 | **การแจ้งเตือนพึ่ง SMTP ภายนอก** → เมลล่ม = ไม่ได้แจ้ง | AS-5 | M | L | **Low** | ป้องกันแล้ว: เมลล้มไม่ล้ม request + บันทึก `NotificationLog.is_success=False` (`notifications.py`) |

## สรุป Top 3 ที่ควรจัดการก่อน
1. **R-1** อายุ token / localStorage (ผลกระทบสูง)
2. **R-7** ย้ายจาก Quick Tunnel ไป named tunnel ก่อนใช้งานจริง
3. **R-3** ตั้ง `DEBUG=False` เป็นค่าเริ่มต้น

> ความเสี่ยงที่ "ป้องกันแล้ว" ส่วนใหญ่สะท้อนว่าทีมคิดเรื่องความปลอดภัยมาตั้งแต่ออกแบบ ส่วนที่ "เสนอ" คือ roadmap ต่อยอด เชื่อมโยงกับ [05-conclusion.md](05-conclusion.md) และ [08-secure-coding-and-refactor.md](08-secure-coding-and-refactor.md)
