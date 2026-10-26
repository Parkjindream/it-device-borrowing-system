# เอกสารนำเสนอโครงงาน — ระบบยืม-คืนอุปกรณ์ไอที (IT Device Borrowing System)

> รายวิชา **SOFTWARE DESIGN AND DEVELOPMENT 2** · นำเสนอ 29 ตุลาคม 2569

เอกสารชุดนี้เรียบเรียงจากซอร์สโค้ดจริงของโปรเจกต์ ใช้เป็น "บท" สำหรับทำสไลด์และยื่นเป็นหลักฐานประกอบการให้คะแนน ทุกจุดที่ยกตัวอย่างโค้ดอ้างอิงเป็น `ไฟล์:บรรทัด` เพื่อให้เปิดดูของจริงได้ทันที

## ภาพรวมระบบ (1 ย่อหน้า)

ระบบให้นักศึกษา "จอง → รับ → คืน" อุปกรณ์ไอที (โน้ตบุ๊ก/กล้อง ฯลฯ) และให้เจ้าหน้าที่จัดการคลัง/ยืนยันการรับ-คืน/คุมบทลงโทษ สถาปัตยกรรม: **Django 5 + Django REST Framework** (backend) · **HTML/JS + Tailwind** เสิร์ฟด้วย **nginx** (frontend) · **PostgreSQL** (ฐานข้อมูล) · **MinIO/S3** (ไฟล์อัปโหลด) · deploy ด้วย **Docker Compose** เปิดสู่อินเทอร์เน็ตผ่าน **Cloudflare Tunnel**

## สารบัญ

### ส่วนที่ 1 — อ.ไพบูลย์ (ออกแบบเชิงวัตถุ / สถาปัตยกรรม / Git / สาธิต)
| ไฟล์ | หัวข้อ |
|------|--------|
| [01-introduction.md](01-introduction.md) | บทนำและเป้าหมายของระบบ (ความเป็นมา, วัตถุประสงค์, ขอบเขต) |
| [02-architecture-and-design.md](02-architecture-and-design.md) | สถาปัตยกรรม, Class Diagram, SOLID + ตัวอย่างโค้ด |
| [03-git-collaboration.md](03-git-collaboration.md) | การทำงานร่วมกันผ่าน Git (branch, commit, PR, review) |
| [04-live-demo.md](04-live-demo.md) | สคริปต์สาธิต use case หลัก + การจัดการ edge case |
| [05-conclusion.md](05-conclusion.md) | สรุปผล, ปัญหาการออกแบบเชิงวัตถุ, โอกาส refactor |

### ส่วนที่ 2 — อ.สุระชัย (ความปลอดภัย / การติดตั้งอัตโนมัติ)
| ไฟล์ | หัวข้อ |
|------|--------|
| [06-threat-analysis.md](06-threat-analysis.md) | Threat Modeling (DFD), Misuse Case, Asset List, Security Requirements |
| [07-risk-register.md](07-risk-register.md) | ทะเบียนความเสี่ยง (Risk Register) |
| [08-secure-coding-and-refactor.md](08-secure-coding-and-refactor.md) | Secure Coding ตามหลักการ + การ Refactor |
| [09-traceability-matrix.md](09-traceability-matrix.md) | Traceability Matrix (requirement → โค้ด → เทสต์) |
| [10-cicd.md](10-cicd.md) | การติดตั้งอัตโนมัติ: CI + CD + ผลลัพธ์การติดตั้ง |

## ตารางคะแนน → ไฟล์ที่ครอบคลุม

**อ.ไพบูลย์**
| เกณฑ์ | สัดส่วน | ไฟล์ |
|------|:---:|------|
| สถาปัตยกรรม + OOP (High Cohesion / Low Coupling / SOLID / Class Diagram) | 30% | 02 |
| คุณภาพโค้ด (PEP 8, exception handling, โครงสร้างโปรเจกต์) | 20% | 02, 08, 10(lint) |
| Git & Collaboration (commit, branch, PR, การกระจายงาน) | 15% | 03 |
| สาธิต + ความสมบูรณ์ | 20% | 04 |
| นำเสนอ + ตอบคำถาม | 15% | ทุกไฟล์ (เตรียมเหตุผลเชิงออกแบบ) |

**อ.สุระชัย**
| เกณฑ์ | สัดส่วน | ไฟล์ |
|------|:---:|------|
| Threat analysis (DFD, Misuse Case, Asset List, Security Requirements) | 20% | 06 |
| Risk Register | 10% | 07 |
| Secure Coding + Refactor (อ้างหลักการ) | 20% | 08 |
| Traceability Matrix | 10% | 09 |
| การติดตั้งอัตโนมัติ (CI + CD + ผลลัพธ์) | 40% | 10 |

## แผนผังไฟล์โค้ดที่อ้างถึงบ่อย
```
backend/
├── config/settings.py        ตั้งค่า Django ทั้งหมด (อ่านจาก .env)
└── rental/                    แอปหลัก (โดเมนทั้งหมด)
    ├── models.py              โมเดล/ตารางฐานข้อมูล (Class Diagram มาจากที่นี่)
    ├── serializers.py         ตรวจ/แปลงข้อมูลเข้า-ออก (input validation)
    ├── views.py               ชั้น HTTP (controller)
    ├── services.py            ชั้น business logic (หัวใจของ Low Coupling)
    ├── permissions.py         สิทธิ์ตามบทบาท (IsStaffUser / IsStudentUser)
    ├── jobs.py                งานอัตโนมัติ (no-show, แจ้งเตือน, ปลดพักสิทธิ์)
    ├── notifications.py       ส่งอีเมล + log
    └── tests.py               เทสต์อัตโนมัติ 38 เคส
.github/workflows/             CI/CD (ci.yml, cd.yml)
docker-compose.yml             การติดตั้งจริงทั้งระบบ
```
