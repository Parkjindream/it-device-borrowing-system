/**
 * ตรรกะของหน้า "ลืมรหัสผ่าน" — แยกออกมาเป็นไฟล์ภายนอก (เดิมฝังอยู่ใน <script> ท้าย
 * forgot-password.html) เพื่อให้สอดคล้องกับทุกหน้าอื่นในระบบที่แยกไฟล์ .js เสมอ
 * และเปลี่ยนมาใช้ extractErrorMessage() จาก api.js แทนการเขียน logic จัดการ error เอง
 * ซ้ำซ้อน — ทำให้ข้อความ error (รวมถึงตอนโดน rate-limit/429) ขึ้นเหมือนกันทุกหน้าในระบบ
 */
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $("forgot-form"), email = $("email"), btn = $("submit-btn"), msg = $("form-message");
  let busy = false, timer = null, lastEmail = "";

  function showError(t) {
    msg.style.background = "#fdecec";
    msg.style.color = "#c33c3c";
    msg.textContent = t;
    msg.classList.remove("hidden");
  }
  function setLoading(on) {
    btn.disabled = on;
    $("spin").classList.toggle("hidden", !on);
    $("btn-text").textContent = on ? "กำลังส่ง..." : "ส่งลิงก์ตั้งรหัสผ่านใหม่";
  }
  // ตอบข้อความเหมือนกันเสมอ (backend ไม่เปิดเผยว่าอีเมลนี้มีในระบบหรือไม่) — ความปลอดภัยสำคัญของหน้านี้
  const send = (address) => Api.post("/auth/password-reset/", { email: address }, { auth: false });

  function startCooldown() {
    const resend = $("resend-btn");
    let left = 60;
    resend.disabled = true;
    resend.textContent = "ส่งอีกครั้งได้ใน " + left + " วินาที";
    clearInterval(timer);
    timer = setInterval(() => {
      left--;
      if (left <= 0) { clearInterval(timer); resend.disabled = false; resend.textContent = "ส่งลิงก์อีกครั้ง"; }
      else resend.textContent = "ส่งอีกครั้งได้ใน " + left + " วินาที";
    }, 1000);
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (busy) return;
    msg.classList.add("hidden");
    const value = email.value.trim().toLowerCase();
    if (!value || !email.checkValidity()) { showError("กรุณากรอกอีเมลให้ถูกต้อง"); return email.focus(); }

    busy = true; setLoading(true);
    const { ok, data } = await send(value);
    busy = false; setLoading(false);

    if (ok) {
      lastEmail = value;
      $("sent-email").textContent = value;
      form.classList.add("hidden");
      $("sent-box").classList.remove("hidden");
      startCooldown();
    } else {
      showError(extractErrorMessage(data, "ส่งไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"));
    }
  });

  $("resend-btn").addEventListener("click", async () => {
    if (busy || !lastEmail) return;
    busy = true;
    const b = $("resend-btn"); b.disabled = true; b.textContent = "กำลังส่ง...";
    const { ok, data } = await send(lastEmail);
    busy = false;
    if (ok) { startCooldown(); return; }
    b.disabled = false;
    b.textContent = extractErrorMessage(data, "ส่งไม่สำเร็จ ลองอีกครั้ง");
  });
})();
