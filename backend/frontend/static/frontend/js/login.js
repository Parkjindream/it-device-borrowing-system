// ตรวจว่า ?next= ชี้ไปหน้าในเว็บเราเองเท่านั้น (กันถูกพาไปเว็บอื่นหลังล็อกอิน)
// คืนค่า URL ที่ปลอดภัย หรือ null ถ้าไม่ปลอดภัย/ไม่มีค่า
function getSafeNext(raw) {
  if (!raw) return null;
  try {
    const url = new URL(raw, location.href);
    if (url.origin !== location.origin) return null;
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.href;
  } catch (e) {
    return null;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  // ถ้าล็อกอินอยู่แล้วเซิร์ฟเวอร์เด้งไป dashboard ให้ก่อนถึงหน้านี้ (LoginPageView)
  // มาถึงตรงนี้แปลว่า session หมดแล้ว — ล้าง token เก่าที่ค้างใน localStorage ทิ้ง
  Api.clearSession();

  const form = document.getElementById("login-form");
  const errorBox = document.getElementById("form-error");
  const submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.classList.add("hidden");
    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังเข้าสู่ระบบ...";

    const formData = new FormData(form);
    const { ok, data } = await Api.post("/auth/login/", {
      email: formData.get("email"),
      password: formData.get("password"),
    }, { auth: false });

    if (!ok) {
      errorBox.textContent = extractErrorMessage(data, "อีเมลหรือรหัสผ่านไม่ถูกต้อง");
      errorBox.classList.remove("hidden");
      submitBtn.disabled = false;
      submitBtn.textContent = "เข้าสู่ระบบ";
      return;
    }

    Api.setSession(data.token, data.user);

    // ถ้ามาจากหน้าอื่นที่ต้องล็อกอินก่อน (ผ่าน ?next=...) ให้กลับไปหน้านั้น (เฉพาะหน้าในเว็บเราเอง)
    const params = new URLSearchParams(location.search);
    const next = getSafeNext(params.get("next"));

    location.href = next || dashboardUrlFor(data.user);
  });
});