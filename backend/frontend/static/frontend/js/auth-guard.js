/**
 * เรียกใช้ที่บนสุดของหน้าที่ต้องล็อกอินก่อนเข้าถึง (dashboard ทุกหน้า)
 * requiredRole: "student" | "staff" | null (null = ล็อกอินแล้วเข้าได้ทุก role)
 *
 * เซิร์ฟเวอร์เช็คล็อกอิน/role ให้แล้วก่อนส่งหน้านี้มา (frontend/decorators.py: role_required)
 * ฟังก์ชันนี้จึงมีหน้าที่หลักแค่ดึงข้อมูลผู้ใช้จาก /auth/me/ มาใช้ในหน้า
 * ถ้า token ใน localStorage ไม่ตรงกับ session (เช่นล้างข้อมูลเบราว์เซอร์) ให้ออกจากระบบให้สะอาดแล้วล็อกอินใหม่
 */
async function requireAuth(requiredRole = null) {
  if (!Api.isLoggedIn()) {
    location.href = APP.urls.logout;
    return null;
  }

  const { ok, data } = await Api.get("/auth/me/");
  if (!ok) {
    Api.clearSession();
    location.href = APP.urls.logout;
    return null;
  }

  Api.setSession(Api.getToken(), data);

  if (requiredRole && data.role !== requiredRole) {
    // token เป็นของคนละบัญชีกับ session ที่เปิดหน้านี้ — ออกจากระบบให้หมดก่อน
    Api.clearSession();
    location.href = APP.urls.logout;
    return null;
  }

  return data;
}

async function logout() {
  // API ลบทั้ง token และ session ให้ในครั้งเดียว
  await Api.post("/auth/logout/", null);
  Api.clearSession();
  location.href = APP.urls.login;
}
