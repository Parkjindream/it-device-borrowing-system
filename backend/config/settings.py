"""
Django settings สำหรับระบบยืม-คืนอุปกรณ์ไอที (IT Equipment Borrowing System)

ค่าที่ต่างกันระหว่างเครื่องนักพัฒนา/เซิร์ฟเวอร์จริง อ่านจากไฟล์ .env (หรือ environment variable
ใน Docker) ทั้งหมด — ไม่ hardcode รหัสผ่านหรือคีย์ลับไว้ในโค้ด
"""
from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# --- ความปลอดภัยพื้นฐาน ---
SECRET_KEY = config("DJANGO_SECRET_KEY", default="dev-only-secret-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

# ต้องระบุ origin ของเว็บที่เข้าหน้า /admin/ ผ่าน https หรือหลัง reverse proxy
# เช่น https://borrow.college.ac.th  (คั่นด้วย , ได้หลายค่า)
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# backend ถูกเปิดสู่ภายนอกใต้ /api เท่านั้น (nginx/dev_server.py ตัด /api ออกก่อนส่งมา)
# บอก Django ไว้ ลิงก์ที่สร้างเอง (หน้า admin, redirect, ลิงก์แบ่งหน้า) จะได้ขึ้นต้นด้วย /api ถูกต้อง
FORCE_SCRIPT_NAME = config("FORCE_SCRIPT_NAME", default="/api") or None

# ใช้เมื่อรันหลัง nginx/reverse proxy ที่ทำ https ให้ (Docker ตั้งเป็น True ให้อัตโนมัติผ่าน .env)
if config("USE_X_FORWARDED_PROTO", default=False, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# คุกกี้ปลอดภัย (เปิดเมื่อใช้ https จริงเท่านั้น)
_secure_cookies = config("SECURE_COOKIES", default=False, cast=bool)
SESSION_COOKIE_SECURE = _secure_cookies
CSRF_COOKIE_SECURE = _secure_cookies

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    # โปรเจกต์ของเรา
    "rental",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- Database: PostgreSQL ---
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME", default="it_lending_db"),
        "USER": config("DB_USER", default="postgres"),
        "PASSWORD": config("DB_PASSWORD", default="postgres"),
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default="5432"),
    }
}

# --- Custom User model (นักศึกษา / เจ้าหน้าที่) ---
AUTH_USER_MODEL = "rental.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ลิงก์ตั้งรหัสผ่านใหม่หมดอายุใน 24 ชั่วโมง (ตรงกับที่เขียนไว้ในอีเมล)
PASSWORD_RESET_TIMEOUT = 60 * 60 * 24

LANGUAGE_CODE = "th"
TIME_ZONE = "Asia/Bangkok"
USE_I18N = True
USE_TZ = True

# ใช้ path เต็ม (ขึ้นต้นด้วย /) ไม่งั้น Django จะเติม /api ข้างหน้าให้ตาม FORCE_SCRIPT_NAME
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # collectstatic เก็บที่นี่ (Docker ให้ nginx เสิร์ฟ)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"          # รูปอุปกรณ์ที่เจ้าหน้าที่อัปโหลด

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Django REST Framework ---
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    # จำกัดความถี่กันเดารหัสผ่าน/ยิงอีเมลรัว ๆ (นับต่อ IP)
    "DEFAULT_THROTTLE_RATES": {
        "login": "20/min",
        # แยกโควต้า "ขอลิงก์" กับ "ยืนยันรหัสใหม่" ออกจากกัน กันโดนบล็อกไขว้กันตอนทดสอบ/ใช้งานจริง
        "password_reset_request": "10/hour",
        "password_reset_confirm": "10/hour",
        "public": "120/min",
    },
    # จำนวน proxy ที่อยู่หน้า Django (Docker + nginx = 1) เพื่ออ่าน IP จริงของผู้ใช้
    "NUM_PROXIES": config("NUM_PROXIES", default=0, cast=int),
}

# --- CORS: ให้ frontend ที่รันแยกพอร์ตตอนพัฒนาเรียก API ได้ ---
# (ตอน deploy ด้วย Docker frontend/backend อยู่ origin เดียวกันผ่าน nginx จึงไม่ต้องพึ่ง CORS)
CORS_ALLOWED_ORIGINS = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost:5500,http://127.0.0.1:5500,http://localhost:8080,http://127.0.0.1:8080",
    cast=Csv(),
)

# --- อีเมล (สำหรับระบบแจ้งเตือน โมดูล E) ---
# ค่าเริ่มต้นเป็น console = แค่พิมพ์อีเมลลง terminal ไม่ได้ส่งจริง (เหมาะกับตอนทดสอบ)
# ส่งจริงต้องตั้ง EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend + ค่า SMTP ใน .env
EMAIL_BACKEND = config("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
EMAIL_USE_SSL = config("EMAIL_USE_SSL", default=False, cast=bool)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_TIMEOUT = 20
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="ศูนย์ยืม-คืนอุปกรณ์ไอที <no-reply@it-lending.local>")

# --- URL หน้า frontend สำหรับฝัง link ในอีเมล (ตั้งรหัสผ่านใหม่) ---
# เว้นว่างไว้ = ใช้โดเมนเดียวกับที่ผู้ใช้กดขอลิงก์เข้ามา (เหมาะกับ trycloudflare ที่ URL สุ่มใหม่ทุกครั้ง
# และ dev_server.py ที่ 127.0.0.1:5500) — ตั้งค่าเมื่อมีโดเมนจริงที่แน่นอนแล้ว
FRONTEND_URL = config("FRONTEND_URL", default="").rstrip("/")
FRONTEND_RESET_PASSWORD_URL = config(
    "FRONTEND_RESET_PASSWORD_URL", default=f"{FRONTEND_URL}/reset-password.html" if FRONTEND_URL else ""
)

# --- ค่าตั้งต้นของระบบ (ค่าจริงที่เจ้าหน้าที่ปรับได้อยู่ในตาราง PenaltySettings) ---
DEFAULT_BOOKING_EXPIRE_HOURS = 24
DEFAULT_MAX_BORROW_DAYS = 7
DEFAULT_OVERDUE_DAYS_THRESHOLD = 1
DEFAULT_SUSPENSION_DAYS = 2
DEFAULT_MAX_ADVANCE_DAYS = 7   # จองล่วงหน้าได้ไม่เกินกี่วัน
# --- เคลียร์ข้อมูลเก่าอัตโนมัติ (กันฐานข้อมูลโตไม่จำกัด) ---
# ประวัติอีเมล (NotificationLog) เก็บไว้ไม่กี่วันก็พอ เพราะดูได้จาก booking โดยตรงอยู่แล้ว
NOTIFICATION_LOG_RETENTION_DAYS = config("NOTIFICATION_LOG_RETENTION_DAYS", default=7, cast=int)
# ประวัติการยืมที่ "จบแล้ว" (คืนแล้ว/ยกเลิก) เก็บไว้นานกว่า เพราะเป็นหลักฐานการยืม-คืนจริง
BOOKING_HISTORY_RETENTION_DAYS = config("BOOKING_HISTORY_RETENTION_DAYS", default=180, cast=int)

# --- Logging: ออกทาง console (Docker เก็บ log ให้ดูผ่าน docker compose logs) ---
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": config("LOG_LEVEL", default="INFO")},
}
