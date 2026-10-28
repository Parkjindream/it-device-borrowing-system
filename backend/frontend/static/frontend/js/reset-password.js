/**
 * หน้านี้คือปลายทางที่ลิงก์ในอีเมล "ลืมรหัสผ่าน" พาผู้ใช้มา — อ่าน uid/token จาก
 * query string ของ URL (เช่น reset-password.html?uid=xxx&token=yyy) แล้วส่งไปยืนยัน
 * พร้อมรหัสผ่านใหม่ที่หน้า /auth/password-reset-confirm/
 */
document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("reset-form");
  const messageBox = document.getElementById("form-message");
  const submitBtn = document.getElementById("submit-btn");

  const params = new URLSearchParams(location.search);
  const uid = params.get("uid");
  const token = params.get("token");

  function showMessage(text, isError) {
    messageBox.textContent = text;
    messageBox.style.background = isError ? "#fdecec" : "#eafaf3";
    messageBox.style.color = isError ? "#c33c3c" : "#1f7a4d";
    messageBox.classList.remove("hidden");
  }

  if (!uid || !token) {
    showMessage("ลิงก์นี้ไม่สมบูรณ์ กรุณาขอลิงก์ตั้งรหัสผ่านใหม่อีกครั้ง", true);
    submitBtn.disabled = true;
    return;
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    messageBox.classList.add("hidden");

    const formData = new FormData(form);
    const newPassword = formData.get("new_password");
    const confirmPassword = formData.get("confirm_password");

    if (newPassword.length < 8) {
      showMessage("รหัสผ่านต้องมีอย่างน้อย 8 ตัวอักษร", true);
      return;
    }
    if (newPassword !== confirmPassword) {
      showMessage("รหัสผ่านทั้งสองช่องไม่ตรงกัน", true);
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังบันทึก...";

    const { ok, data } = await Api.post("/auth/password-reset-confirm/", {
      uid, token, new_password: newPassword,
    }, { auth: false });

    if (!ok) {
      showMessage(extractErrorMessage(data, "ลิงก์หมดอายุหรือไม่ถูกต้อง"), true);
      submitBtn.disabled = false;
      submitBtn.textContent = "ตั้งรหัสผ่านใหม่";
      return;
    }

    showMessage("ตั้งรหัสผ่านใหม่สำเร็จ กำลังพาไปหน้าเข้าสู่ระบบ...", false);
    form.reset();
    submitBtn.textContent = "สำเร็จแล้ว";
    setTimeout(() => (location.href = APP.urls.login), 1800);
  });
});
