FROM nginx:1.27-alpine

# ลบไฟล์ตัวอย่างของ nginx image ทิ้งก่อน
RUN rm -rf /usr/share/nginx/html/*

# ไฟล์เว็บ frontend ทั้งหมด (html/css/js/รูปภาพ)
COPY . /usr/share/nginx/html

# ไฟล์ตั้งค่านี้จะถูก mount ทับอีกทีจาก docker-compose (ดู volumes) แต่ใส่ default ไว้กันพลาด
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
