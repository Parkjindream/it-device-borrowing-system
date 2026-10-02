document.addEventListener("DOMContentLoaded", () => {
  // ถ้าล็อกอินอยู่แล้ว ไม่ต้องให้เห็นหน้า login อีก เด้งไป dashboard ตาม role ทันที
  if (Api.isLoggedIn()) {
    const user = Api.getUser();
    location.href = user && user.role === "staff" ? "staff/dashboard.html" : "student/dashboard.html";
    return;
  }

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

    // ถ้ามาจากหน้าอื่นที่ต้องล็อกอินก่อน (ผ่าน ?next=...) ให้กลับไปหน้านั้น
    const params = new URLSearchParams(location.search);
    const next = params.get("next");

    if (next) {
      location.href = next;
    } else if (data.user.role === "staff") {
      location.href = "staff/dashboard.html";
    } else {
      location.href = "student/dashboard.html";
    }
  });
});
