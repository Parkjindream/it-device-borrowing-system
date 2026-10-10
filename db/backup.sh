#!/bin/sh
# สำรองฐานข้อมูลอัตโนมัติ — รันใน container "db-backup" (image postgres เดียวกับ db จะได้ pg_dump เวอร์ชันตรงกัน)
#
# - สำรองทันทีตอน container เริ่ม (เช็คได้เลยว่าใช้งานได้) แล้วทุกวันเวลา BACKUP_HOUR:00
# - เก็บไว้ที่ ./backups บนเครื่องเซิร์ฟเวอร์ ชื่อไฟล์ it_lending_db-YYYYmmdd-HHMMSS.dump (รูปแบบ custom ของ pg_dump)
# - ลบไฟล์ที่เก่ากว่า BACKUP_KEEP_DAYS วันทิ้งอัตโนมัติ
#
# กู้คืน (หยุดเว็บก่อน กันมีคนเขียนข้อมูลระหว่างกู้):
#   docker compose stop backend scheduler
#   docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < backups/<ไฟล์>.dump
#   docker compose start backend scheduler
set -eu

BACKUP_DIR=/backups
BACKUP_HOUR=${BACKUP_HOUR:-2}
BACKUP_KEEP_DAYS=${BACKUP_KEEP_DAYS:-14}

backup() {
    name="${PGDATABASE}-$(date +%Y%m%d-%H%M%S).dump"
    # เขียนลงไฟล์ชั่วคราวก่อน dump เสร็จค่อยเปลี่ยนชื่อ กันได้ไฟล์ครึ่ง ๆ กลาง ๆ ถ้าล่มกลางทาง
    if pg_dump --format=custom --file="$BACKUP_DIR/.$name.part"; then
        mv "$BACKUP_DIR/.$name.part" "$BACKUP_DIR/$name"
        # ให้เจ้าของไฟล์ตรงกับโฟลเดอร์ backups บนเครื่อง (ไม่งั้นเป็น root ต้อง sudo ถึงจะลบ/ย้ายได้)
        chown "$(stat -c %u:%g "$BACKUP_DIR")" "$BACKUP_DIR/$name"
        echo "$(date '+%F %T') สำรองสำเร็จ: $name ($(du -h "$BACKUP_DIR/$name" | cut -f1))"
    else
        rm -f "$BACKUP_DIR/.$name.part"
        echo "$(date '+%F %T') สำรองล้มเหลว — จะลองใหม่รอบถัดไป" >&2
    fi
    find "$BACKUP_DIR" -maxdepth 1 -name "${PGDATABASE}-*.dump" -mtime +"$BACKUP_KEEP_DAYS" -print -delete
}

seconds_until_next_run() {
    # ตัด 0 นำหน้าออก ไม่งั้น sh มองเป็นเลขฐาน 8 (เช่น 08, 09 จะ error)
    h=$(date +%H); m=$(date +%M); s=$(date +%S)
    now=$(( ${h#0} * 3600 + ${m#0} * 60 + ${s#0} ))
    wait=$(( (BACKUP_HOUR * 3600 - now + 86400) % 86400 ))
    [ "$wait" -eq 0 ] && wait=86400
    echo "$wait"
}

echo "สำรองฐานข้อมูล $PGDATABASE ทุกวันเวลา $BACKUP_HOUR:00 ($TZ) เก็บย้อนหลัง $BACKUP_KEEP_DAYS วัน"
backup
while true; do
    sleep "$(seconds_until_next_run)"
    backup
done
