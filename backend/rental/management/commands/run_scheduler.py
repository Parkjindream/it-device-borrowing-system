"""
ตัวรันงานอัตโนมัติ (แทน cron) — ใช้ได้ทั้ง Windows, Mac, Linux และใน Docker

    python manage.py run_scheduler            # รันค้างไว้ตลอด (เปิดอีก terminal หนึ่ง)
    python manage.py run_scheduler --once     # รันทุกงาน 1 รอบแล้วจบ (ไว้ทดสอบ)

งานที่ทำ:
- ทุก --interval วินาที (ค่าเริ่มต้น 900 = 15 นาที): ยกเลิกการจองที่ไม่มารับตามเวลา (no-show)
- วันละครั้งหลัง --daily-hour นาฬิกา (ค่าเริ่มต้น 07:00 เวลาไทย): ปลดพักสิทธิ์ที่ครบกำหนด,
  เปลี่ยนสถานะ "เกินกำหนด", ส่งอีเมลเตือนใกล้ครบกำหนด/ถึงกำหนด/เกินกำหนด
  (กันส่งซ้ำด้วย Booking.last_reminder_sent_date แม้ restart กลางวัน)
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.utils import timezone

from rental.jobs import cancel_expired_bookings, run_daily_due_date_checks

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "รันงานอัตโนมัติของระบบยืม-คืน (no-show, แจ้งเตือน, ปลดพักสิทธิ์)"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="รันทุกงาน 1 รอบแล้วออก")
        parser.add_argument("--interval", type=int, default=900, help="ช่วงเวลาเช็ค no-show (วินาที)")
        parser.add_argument("--daily-hour", type=int, default=7, help="ชั่วโมงที่เริ่มรันงานรายวัน (0-23)")

    def handle(self, *args, **options):
        if options["once"]:
            cancel_expired_bookings()
            run_daily_due_date_checks()
            self.stdout.write(self.style.SUCCESS("รันงานอัตโนมัติครบ 1 รอบแล้ว"))
            return

        self.stdout.write(self.style.SUCCESS(
            f"เริ่มรัน scheduler (เช็คทุก {options['interval']} วินาที, งานรายวันหลัง {options['daily_hour']:02d}:00) — กด Ctrl+C เพื่อหยุด"
        ))
        last_daily_date = None
        while True:
            try:
                cancel_expired_bookings()
                now = timezone.localtime()
                if now.hour >= options["daily_hour"] and last_daily_date != now.date():
                    run_daily_due_date_checks()
                    last_daily_date = now.date()
                    self.stdout.write(f"[{now:%Y-%m-%d %H:%M}] รันงานรายวันเรียบร้อย")
            except Exception:  # งานพลาดรอบหนึ่งต้องไม่ทำให้ scheduler ตายทั้งตัว
                logger.exception("scheduler: เกิดข้อผิดพลาดในรอบนี้ จะลองใหม่รอบถัดไป")
            time.sleep(options["interval"])
