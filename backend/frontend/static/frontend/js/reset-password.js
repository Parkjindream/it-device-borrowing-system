/**
 * หน้านี้คือปลายทางที่ลิงก์ในอีเมล "ลืมรหัสผ่าน" พาผู้ใช้มา — อ่าน uid/token จาก
 * query string ของ URL (เช่น reset-password.html?uid=xxx&token=yyy) แล้วส่งไปยืนยัน
 * พร้อมรหัสผ่านใหม่ที่หน้า /auth/password-reset-confirm/
 *
 * ลิงก์ในอีเมลใช้ได้ครั้งเดียวและหมดอายุใน 24 ชั่วโมง — เปิดหน้ามาจะเช็คกับเซิร์ฟเวอร์ทันที
 * ถ้าใช้ไม่ได้จะซ่อนฟอร์มแล้วพาไปขอลิงก์ใหม่ (ไม่ต้องรอกรอกรหัสผ่านก่อนค่อยรู้)
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

  // ลิงก์ใช้ไม่ได้ (หมดอายุ / ตั้งรหัสผ่านไปแล้ว / ไม่สมบูรณ์) -> ซ่อนฟอร์ม บอกเหตุผล และพาไปขอลิงก์ใหม่
  function blockForm(text) {
    const urls = (window.APP && window.APP.urls) || {};
    const loginHref = urls.login || "login.html";
    const forgotHref = urls.forgotPassword || urls.forgot_password || loginHref.replace("login", "forgot-password");

    form.classList.add("hidden");
    submitBtn.disabled = true;

    let panel = document.getElementById("link-invalid");
    if (!panel) {
      panel = document.createElement("div");
      panel.id = "link-invalid";
      panel.className = "auth-card";
      panel.setAttribute("role", "alert");
      panel.innerHTML =
        '<p id="link-invalid-text" class="mb-4 font-semibold" style="color:#c33c3c"></p>' +
        '<p class="mb-5 text-sm opacity-80">ถ้ายังไม่ได้ตั้งรหัสผ่าน ระบบจะส่งลิงก์ใหม่ให้ทางอีเมลทุกวัน ' +
        'หรือกดขอลิงก์ใหม่ด้วยตัวเองได้ทันที ถ้าตั้งรหัสผ่านไปแล้วให้เข้าสู่ระบบได้เลย</p>' +
        '<a id="link-invalid-new" class="btn btn-primary btn-lg btn-block mb-3"></a>' +
        '<a id="link-invalid-login" class="btn btn-block"></a>';
      form.parentNode.insertBefore(panel, form);
    }
    panel.querySelector("#link-invalid-text").textContent = text;
    const newBtn = panel.querySelector("#link-invalid-new");
    newBtn.textContent = "ขอลิงก์ตั้งรหัสผ่านใหม่";
    newBtn.href = forgotHref;
    const loginBtn = panel.querySelector("#link-invalid-login");
    loginBtn.textContent = "ไปหน้าเข้าสู่ระบบ";
    loginBtn.href = loginHref;
  }

  if (!uid || !token) {
    blockForm("ลิงก์นี้ไม่สมบูรณ์ กรุณาขอลิงก์ตั้งรหัสผ่านใหม่อีกครั้ง");
    return;
  }

  // เช็คลิงก์ตั้งแต่เปิดหน้า — บล็อกฟอร์มเฉพาะเมื่อเซิร์ฟเวอร์ตอบชัดเจนว่าลิงก์ใช้ไม่ได้ (400)
  // ถ้าเช็คไม่ได้เพราะเน็ตหลุด/โดนจำกัดความถี่ ปล่อยให้กรอกต่อได้ (ตอนกดบันทึกเซิร์ฟเวอร์ตรวจซ้ำอีกชั้น)
  submitBtn.disabled = true;
  Api.post("/auth/password-reset-validate/", { uid, token }, { auth: false }).then(({ ok, status, data }) => {
    if (!ok && status === 400) {
      blockForm(extractErrorMessage(data, "ลิงก์นี้หมดอายุหรือถูกใช้ไปแล้ว"));
      return;
    }
    submitBtn.disabled = false;
  });

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

    const { ok, status, data } = await Api.post("/auth/password-reset-confirm/", {
      uid, token, new_password: newPassword,
    }, { auth: false });

    // ลิงก์เพิ่งหมดอายุ/ถูกใช้ไประหว่างที่เปิดหน้าค้างไว้ -> สลับเป็นหน้าลิงก์ใช้ไม่ได้
    if (!ok && status === 400 && /ลิงก์/.test((data && data.detail) || "")) {
      blockForm(extractErrorMessage(data, "ลิงก์นี้หมดอายุหรือถูกใช้ไปแล้ว"));
      return;
    }
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