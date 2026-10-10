/**
 * ตั้งค่าที่อยู่ของ backend Django REST API
 *
 * - ตอนพัฒนาบนเครื่อง (เปิด frontend ผ่าน `python -m http.server 5500` หรือ Live Server)
 *   frontend กับ backend คนละพอร์ตกัน จึงต้องระบุ URL เต็มของ backend ตรง ๆ
 * - ตอน deploy ด้วย Docker (docker-compose) nginx จะ proxy "/api/" ไปหา backend ให้เอง
 *   ทำให้ frontend กับ backend อยู่ origin เดียวกัน ใช้ path สัมพัทธ์ "/api" ได้เลย ไม่มีปัญหา CORS
 *
 * โค้ดด้านล่างเดาให้อัตโนมัติจากพอร์ตที่ใช้เปิดหน้านี้ ไม่ต้องแก้เองตอนสลับโหมด
 * แต่ถ้าต้องการ "บังคับ" ค่าใดค่าหนึ่งแน่นอน ให้ลบทั้งฟังก์ชันด้านล่างแล้วใส่ค่าคงที่แทน เช่น:
 *   const API_BASE_URL = "https://borrow.yourcollege.ac.th/api";
 */
   // เรียก API ผ่านที่อยู่เดียวกับหน้าเว็บ (dev_server.py หรือ nginx ส่งต่อให้ backend)
const API_BASE_URL = "/api";
/*const API_BASE_URL = (() => {
  const isLocalDevServer =
    ["localhost", "127.0.0.1"].includes(location.hostname) &&
    ["5500", "8080", "5501", "3000"].includes(location.port);
  return isLocalDevServer ? "http://127.0.0.1:8000/api" : "/api";
})();**/
