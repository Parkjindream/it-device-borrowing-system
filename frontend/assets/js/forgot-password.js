document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("forgot-form");
  const messageBox = document.getElementById("form-message");
  const submitBtn = document.getElementById("submit-btn");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังส่ง...";

    const email = new FormData(form).get("email");
    const { data } = await Api.post("/auth/password-reset/", { email }, { auth: false });

    // ตอบข้อความเดียวกันเสมอไม่ว่าอีเมลนี้จะมีอยู่จริงหรือไม่ (ฝั่ง backend ตั้งใจออกแบบไว้แบบนี้
    // เพื่อความปลอดภัย ไม่ให้ใครเดาได้ว่าอีเมลไหนมีอยู่ในระบบ)
    messageBox.textContent = data?.detail || "หากอีเมลนี้มีอยู่ในระบบ เราได้ส่งลิงก์ไปให้แล้ว กรุณาตรวจสอบอีเมลของคุณ";
    messageBox.style.background = "#eafaf3";
    messageBox.style.color = "#1f7a4d";
    messageBox.classList.remove("hidden");

    submitBtn.textContent = "ส่งอีกครั้ง";
    submitBtn.disabled = false;
  });
});
