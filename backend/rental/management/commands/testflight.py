"""
ตรวจก่อนเปิดระบบ (preflight): เชื่อมต่อฐานข้อมูลและที่เก็บไฟล์อัปโหลด (S3/MinIO หรือดิสก์) ได้จริงไหม

    python manage.py testflight

- ฐานข้อมูล: ต่อได้, เวอร์ชัน PostgreSQL, มี migration ที่ยังไม่ได้รันไหม (เตือน ไม่นับว่าล้มเหลว)
- ที่เก็บไฟล์: มี bucket, ลองเขียน -> อ่าน -> ลบไฟล์ทดสอบจริง (ไฟล์อยู่ใต้ testflight/ และถูกลบทิ้งทันที)
- ไม่พิมพ์รหัสผ่าน/คีย์ลับ บอกแค่ว่าตั้งค่าไว้หรือไม่
- มีข้อใดล้มเหลว -> จบด้วย exit code 1 (docker compose ใช้ตัวนี้กัน backend เริ่มทั้งที่ระบบยังไม่พร้อม)
"""
import time
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "ทดสอบการเชื่อมต่อฐานข้อมูลและที่เก็บไฟล์ (S3/MinIO) ก่อนเปิดระบบ"

    def add_arguments(self, parser):
        parser.add_argument("--skip-db", action="store_true", help="ไม่ตรวจฐานข้อมูล")
        parser.add_argument("--skip-storage", action="store_true", help="ไม่ตรวจที่เก็บไฟล์")

    def handle(self, *args, **options):
        failures = []
        if not options["skip_db"]:
            self.run_check("ฐานข้อมูล", self.check_database, failures)
        if not options["skip_storage"]:
            self.run_check("ที่เก็บไฟล์", self.check_storage, failures)

        if failures:
            raise CommandError(f"testflight ไม่ผ่าน: {', '.join(failures)}")
        self.stdout.write(self.style.SUCCESS("testflight ผ่านทั้งหมด"))

    def run_check(self, name, check, failures):
        self.stdout.write(f"\n== {name} ==")
        started = time.monotonic()
        try:
            check()
        except Exception as exc:  # รายงานทุกข้อผิดพลาดเป็นข้อความเดียว แล้วตรวจข้อถัดไปต่อ
            failures.append(name)
            self.stdout.write(self.style.ERROR(f"  ✗ {type(exc).__name__}: {exc}"))
            return
        self.stdout.write(self.style.SUCCESS(f"  ✓ ผ่าน ({(time.monotonic() - started) * 1000:.0f} ms)"))

    def check_database(self):
        db = settings.DATABASES[DEFAULT_DB_ALIAS]
        self.stdout.write(f"  {db['USER']}@{db['HOST']}:{db['PORT']}/{db['NAME']}")
        connection = connections[DEFAULT_DB_ALIAS]
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            self.stdout.write(f"  {cursor.fetchone()[0].split(',')[0]}")

        executor = MigrationExecutor(connection)
        pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
        if pending:
            self.stdout.write(self.style.WARNING(
                f"  ! มี migration ที่ยังไม่ได้รัน {len(pending)} รายการ — รัน python manage.py migrate"
            ))

    def check_storage(self):
        if not settings.MINIO_ENDPOINT:
            self.stdout.write(f"  ดิสก์: {settings.MEDIA_ROOT}")
        else:
            self.stdout.write(f"  S3: {settings.AWS_S3_ENDPOINT_URL}")
            self.stdout.write(
                f"  bucket={settings.AWS_STORAGE_BUCKET_NAME} region={settings.AWS_S3_REGION_NAME} "
                f"access key={'ตั้งแล้ว' if settings.AWS_ACCESS_KEY_ID else 'ยังไม่ได้ตั้ง'}"
            )
            # แยกเช็ค bucket ก่อน จะได้บอกสาเหตุชัด ๆ (ต่อไม่ได้ / คีย์ผิด / ไม่มี bucket)
            default_storage.connection.meta.client.head_bucket(Bucket=settings.AWS_STORAGE_BUCKET_NAME)

        payload = f"testflight {uuid.uuid4()}".encode()
        name = default_storage.save(f"testflight/{uuid.uuid4().hex}.txt", ContentFile(payload))
        try:
            with default_storage.open(name) as f:
                if f.read() != payload:
                    raise RuntimeError("อ่านไฟล์ทดสอบกลับมาแล้วเนื้อหาไม่ตรงกับที่เขียน")
        finally:
            default_storage.delete(name)
        self.stdout.write("  เขียน -> อ่าน -> ลบ ไฟล์ทดสอบได้")
