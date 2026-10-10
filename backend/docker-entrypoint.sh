#!/bin/sh
# รันตอน container เริ่มทำงานเสมอ ก่อนจะ exec คำสั่งจริง (gunicorn หรือ run_scheduler)
set -e

echo "กำลังรอฐานข้อมูล ($DB_HOST:$DB_PORT) ให้พร้อมใช้งาน..."
python << 'PYEOF'
import os
import sys
import time

import psycopg2

host = os.environ.get("DB_HOST", "db")
port = int(os.environ.get("DB_PORT", 5432))
name = os.environ.get("DB_NAME", "it_lending_db")
user = os.environ.get("DB_USER", "postgres")
password = os.environ.get("DB_PASSWORD", "postgres")

for attempt in range(30):
    try:
        conn = psycopg2.connect(host=host, port=port, dbname=name, user=user, password=password)
        conn.close()
        print("เชื่อมต่อฐานข้อมูลสำเร็จ")
        sys.exit(0)
    except Exception as exc:
        print(f"ฐานข้อมูลยังไม่พร้อม (รอบที่ {attempt + 1}/30): {exc}")
        time.sleep(2)

print("เชื่อมต่อฐานข้อมูลไม่สำเร็จหลังรอ 60 วินาที", file=sys.stderr)
sys.exit(1)
PYEOF

case "$1" in
    # container "migrate" ใน docker-compose: เตรียมฐานข้อมูลครั้งเดียวแล้วจบ
    # backend/scheduler รอให้ตัวนี้เสร็จก่อนค่อยเริ่ม จะได้ไม่ migrate ชนกันตอนฐานข้อมูลยังว่าง
    migrate)
        echo "รัน migrate..."
        python manage.py migrate --noinput
        python manage.py ensure_superuser
        exit 0
        ;;
    # collectstatic จำเป็นเฉพาะ container ที่เสิร์ฟเว็บ (gunicorn) container scheduler ไม่ต้องเสียเวลาทำ
    gunicorn)
        echo "รวบรวม static files..."
        python manage.py collectstatic --noinput
        ;;
esac

exec "$@"
