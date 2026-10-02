/**
 * เรียกใช้ที่บนสุดของหน้าที่ต้องล็อกอินก่อนเข้าถึง (dashboard ทุกหน้า)
 * requiredRole: "student" | "staff" | null (null = ล็อกอินแล้วเข้าได้ทุก role)
 */

/**
 * คำนวณ path กลับไปยัง "รากของเว็บ frontend" แบบสัมพัทธ์ (ไม่ใช้ path ที่ขึ้นต้นด้วย "/")
 *
 * เหตุผลที่ต้องทำแบบนี้: ถ้าใช้ path เต็มแบบ "/login.html" ตรง ๆ มันจะหมายถึง
 * "รากของโดเมน" ซึ่งถูกต้องก็ต่อเมื่อเว็บเซิร์ฟเวอร์ถูกสั่งให้รันจากใน "โฟลเดอร์ frontend/"
 * เป๊ะ ๆ เท่านั้น — ถ้าเปิดทั้งโฟลเดอร์โปรเจกต์ (ที่มี backend/ กับ frontend/ อยู่ด้วยกัน)
 * ด้วย VS Code Live Server แล้วกด "Go Live" โดยไม่ได้ไล่เข้าไปในโฟลเดอร์ frontend/ ก่อน
 * รากของเว็บจะกลายเป็นโฟลเดอร์โปรเจกต์ทั้งก้อน ทำให้ "/login.html" หาไม่เจอ (ได้ error
 * "Cannot GET /login.html") เพราะไฟล์จริงอยู่ที่ "/frontend/login.html" ต่างหาก
 *
 * ฟังก์ชันนี้จึงคำนวณ path แบบสัมพัทธ์จากหน้าปัจจุบันเสมอ ไม่พึ่ง "/" นำหน้า
 */
function appRootPath() {
  const path = location.pathname;
  if (path.includes("/student/") || path.includes("/staff/")) {
    return "../";
  }
  return "";
}

async function requireAuth(requiredRole = null) {
  if (!Api.isLoggedIn()) {
    location.href = appRootPath() + "login.html";
    return null;
  }

  const { ok, data } = await Api.get("/auth/me/");
  if (!ok) {
    Api.clearSession();
    location.href = appRootPath() + "login.html";
    return null;
  }

  Api.setSession(Api.getToken(), data);

  if (requiredRole && data.role !== requiredRole) {
    // เข้าหน้าผิด role → เด้งไปหน้าของ role ตัวเองอัตโนมัติ
    const target = data.role === "staff" ? "staff/dashboard.html" : "student/dashboard.html";
    location.href = appRootPath() + target;
    return null;
  }

  return data;
}

async function logout() {
  await Api.post("/auth/logout/", null);
  Api.clearSession();
  location.href = appRootPath() + "login.html";
}
