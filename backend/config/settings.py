"""
Django settings สำหรับระบบยืม-คืนอุปกรณ์ไอที (IT Equipment Borrowing System)

ค่าที่ต่างกันระหว่างเครื่องนักพัฒนา/เซิร์ฟเวอร์จริง อ่านจากไฟล์ .env (หรือ environment variable
ใน Docker) ทั้งหมด — ไม่ hardcode รหัสผ่านหรือคีย์ลับไว้ในโค้ด
"""
from pathlib import Path

from decouple import Config, Csv, RepositoryEmpty, RepositoryEnv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env ไฟล์เดียวที่รากโปรเจกต์ ใช้ร่วมกันทั้ง docker compose และ runserver
# ตัวแปรแวดล้อมมาก่อนเสมอ (ใน container ไม่มีไฟล์นี้ ค่ามาจาก env_file/environment ของ compose)
_env_file = BASE_DIR.parent / ".env"
config = Config(RepositoryEnv(_env_file) if _env_file.exists() else RepositoryEmpty())

# --- ความปลอดภัยพื้นฐาน ---
# Vercel ตั้งตัวแปร VERCEL=1 ให้เองทุก deployment — ใช้แยกโหมด serverless ออกจากโหมด Docker/เครื่องนักพัฒนา
ON_VERCEL = config("VERCEL", default=False, cast=bool)

SECRET_KEY = config("DJANGO_SECRET_KEY", default="dev-only-secret-change-me")
# บน Vercel ค่าเริ่มต้นเป็น False (ปลอดภัยไว้ก่อน ถ้าลืมตั้ง DEBUG จะไม่เปิดโหมดนักพัฒนาบนเว็บจริง)
DEBUG = config("DEBUG", default=not ON_VERCEL, cast=bool)
# กันเผลอเปิดใช้งานจริงด้วยคีย์ตัวอย่าง: ใครรู้คีย์นี้ปลอมลิงก์ตั้งรหัสผ่านของบัญชีไหนก็ได้ (รวมเจ้าหน้าที่)
if not DEBUG and SECRET_KEY == "dev-only-secret-change-me":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("ตั้ง DJANGO_SECRET_KEY ในไฟล์ .env เป็นค่าสุ่มของตัวเองก่อนใช้งานจริง (ห้ามใช้ค่าตัวอย่าง)")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
if ON_VERCEL and ".vercel.app" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, ".vercel.app"]   # โดเมนเริ่มต้นของ Vercel (โดเมนจริงของคุณใส่ใน ALLOWED_HOSTS)

# ต้องระบุ origin ของเว็บที่เข้าหน้า /admin/ ผ่าน https หรือหลัง reverse proxy
# เช่น https://borrow.college.ac.th  (คั่นด้วย , ได้หลายค่า)
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# Django admin (/api/admin/) — ปิดไว้ตอนใช้งานจริง ระบบนี้ใช้หน้าเจ้าหน้าที่ของเราเอง
# เปิดตอน DEBUG ให้อัตโนมัติ ถ้าต้องใช้บนเซิร์ฟเวอร์จริงให้ตั้ง ENABLE_DJANGO_ADMIN=True ใน .env
ENABLE_DJANGO_ADMIN = config("ENABLE_DJANGO_ADMIN", default=DEBUG, cast=bool)

# header ความปลอดภัยพื้นฐาน (เดิม nginx ใส่ให้) — nosniff เปิดอยู่แล้วโดย SecurityMiddleware
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "SAMEORIGIN"

# ใช้เมื่อรันหลัง nginx/reverse proxy ที่ทำ https ให้ (Docker ตั้งเป็น True ให้อัตโนมัติผ่าน .env)
# บน Vercel เปิดให้อัตโนมัติ (ไม่งั้น Django คิดว่าเป็น http -> ลิงก์ในอีเมลเป็น http:// และ CSRF ของ admin พัง)
if config("USE_X_FORWARDED_PROTO", default=ON_VERCEL, cast=bool):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# คุกกี้ปลอดภัย (เปิดเมื่อใช้ https จริงเท่านั้น) — บน Vercel เป็น https เสมอ
_secure_cookies = config("SECURE_COOKIES", default=ON_VERCEL, cast=bool)
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
    # โปรเจกต์ของเรา
    "rental",
    "frontend",   # หน้าเว็บ (Django templates + static) — ดู frontend/urls.py
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # เสิร์ฟไฟล์ static (css/js/รูป/ฟอนต์) เองจาก gunicorn ไม่ต้องมี nginx
    "whitenoise.middleware.WhiteNoiseMiddleware",
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
        # ใน container compose ส่ง DB_HOST=db/DB_PORT=5432 มาเอง — runserver ต่อพอร์ตที่ infra เปิดไว้บนเครื่อง
        "HOST": config("DB_HOST", default="localhost"),
        "PORT": config("DB_PORT", default=config("DB_EXPOSE_PORT", default="5433")),
        # serverless: ไม่ถือ connection ค้างข้าม request (Supabase pooler จัดการให้เอง)
        "CONN_MAX_AGE": config("DB_CONN_MAX_AGE", default=0, cast=int),
        # Supabase บังคับ/แนะนำ SSL — Docker ภายในเครือข่ายเดียวกันไม่ต้อง
        "OPTIONS": {"sslmode": config("DB_SSLMODE", default="require" if ON_VERCEL else "prefer")},
        # ถ้าต่อผ่าน Supabase pooler แบบ transaction (พอร์ต 6543) ต้องปิด server-side cursor
        "DISABLE_SERVER_SIDE_CURSORS": config("DB_POOLER", default=ON_VERCEL, cast=bool),
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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"   # collectstatic เก็บที่นี่ แล้ว WhiteNoise เสิร์ฟ (บีบอัด gzip ให้ด้วย)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"          # รูปอุปกรณ์ที่เจ้าหน้าที่อัปโหลด (ใช้เมื่อไม่ได้ตั้ง MINIO_ENDPOINT)
# URL สาธารณะของ bucket รูป (ถ้าตั้ง ลิงก์รูปจะชี้ตรงไปที่ storage ไม่ผ่าน Django) เช่น Supabase:
# https://<project-ref>.supabase.co/storage/v1/object/public/<bucket>   (ตรวจด้วยการเปิดรูปจริงในเบราว์เซอร์)
MEDIA_PUBLIC_BASE_URL = config("MEDIA_PUBLIC_BASE_URL", default="").rstrip("/")

# --- ที่เก็บไฟล์อัปโหลดบน MinIO (S3) ---
# docker compose ส่ง MINIO_ENDPOINT=http://minio:9000 ให้ container เอง
# runserver: ถ้า .env มี MINIO_ROOT_USER ใช้ MinIO ของ infra ที่ localhost / ไม่มี = เก็บลง MEDIA_ROOT
# bucket สร้างตอน migrate ใน docker หรือรันเอง: python manage.py ensure_media_bucket
_local_minio = ""
if config("MINIO_ROOT_USER", default=""):
    _local_minio = f"http://localhost:{config('MINIO_API_PORT', default='9000')}"
MINIO_ENDPOINT = config("MINIO_ENDPOINT", default=_local_minio)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
if MINIO_ENDPOINT:
    STORAGES["default"] = {"BACKEND": "config.storage.MediaStorage"}
    AWS_S3_ENDPOINT_URL = MINIO_ENDPOINT
    AWS_ACCESS_KEY_ID = config("MINIO_ACCESS_KEY", default=config("MINIO_ROOT_USER", default=""))
    AWS_SECRET_ACCESS_KEY = config("MINIO_SECRET_KEY", default=config("MINIO_ROOT_PASSWORD", default=""))
    # Django ดึงไฟล์จาก bucket นี้มาเสิร์ฟที่ /media/ (config/urls.py: serve_media_from_storage)
    AWS_STORAGE_BUCKET_NAME = config("MINIO_BUCKET", default="media")
    # MinIO ใช้ us-east-1 ได้ แต่ Supabase Storage (S3) ต้องใส่ region ของโปรเจกต์ (เช่น ap-southeast-1) ผ่าน MINIO_REGION
    AWS_S3_REGION_NAME = config("MINIO_REGION", default="us-east-1")
    AWS_S3_ADDRESSING_STYLE = "path"
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    # ชื่อไฟล์ซ้ำ -> เติมตัวสุ่มต่อท้ายเหมือนเก็บลงดิสก์ (ค่าเริ่มต้นของ S3 คือเขียนทับรูปของคนอื่น)
    AWS_S3_FILE_OVERWRITE = False

elif ON_VERCEL:
    # ดิสก์ของ Vercel เขียนไม่ได้ (read-only) — ถ้าไม่ตั้งที่เก็บรูปภายนอก การอัปโหลดรูปจะ error
    import logging as _logging

    _logging.getLogger(__name__).warning("ON_VERCEL แต่ไม่ได้ตั้ง MINIO_ENDPOINT: อัปโหลดรูปจะใช้ไม่ได้")

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
    # จำนวน reverse proxy ที่อยู่หน้า Django (0 = ไม่มี) เพื่ออ่าน IP จริงของผู้ใช้
    # บน Vercel มี proxy 1 ชั้น: ถ้าเป็น 0 ทุกคนจะถูกนับเป็น IP เดียวกัน (IP ของ proxy) แล้วโควต้า login 20/นาที
    # จะถูกแชร์ทั้งระบบ — ตรวจให้แน่ใจว่าค่านี้ถูกต้องกับ header X-Forwarded-For ที่ Vercel ส่งมา (ดูวิธีทดสอบด้านล่าง)
    "NUM_PROXIES": config("NUM_PROXIES", default=1 if ON_VERCEL else 0, cast=int),
}

# หน้า dashboard ที่ต้องล็อกอิน เด้งมาที่นี่ (frontend/decorators.py: role_required)
LOGIN_URL = "frontend:login"

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
EMAIL_TIMEOUT = config("EMAIL_TIMEOUT", default=10 if ON_VERCEL else 20, cast=int)
# serverless: function ถูกหยุดหลังตอบ response จึงส่งอีเมลใน background thread ไม่ได้ ต้องส่งให้เสร็จก่อนตอบ
EMAIL_SYNC = config("EMAIL_SYNC", default=ON_VERCEL, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="ศูนย์ยืม-คืนอุปกรณ์ไอที <no-reply@it-lending.local>")

# --- URL หน้าเว็บสำหรับฝัง link ในอีเมล (ตั้งรหัสผ่านใหม่) ---
# เว้นว่างไว้ = ใช้โดเมนเดียวกับที่ผู้ใช้กดขอลิงก์เข้ามา — ตั้งค่าเมื่อมีโดเมนจริงที่แน่นอนแล้ว
FRONTEND_URL = config("FRONTEND_URL", default="").rstrip("/")
FRONTEND_RESET_PASSWORD_URL = config(
    "FRONTEND_RESET_PASSWORD_URL", default=f"{FRONTEND_URL}/reset-password/" if FRONTEND_URL else ""
)

# --- งานอัตโนมัติผ่าน HTTP (/api/cron/run-jobs/) — เว้นว่าง = ปิด endpoint (ใช้ container scheduler แทน) ---
CRON_SECRET = config("CRON_SECRET", default="")

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