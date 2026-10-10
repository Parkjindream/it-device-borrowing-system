let currentUser = null;
let allEquipment = [];
const MAX_ADVANCE_DAYS = 7; // ต้องตรงกับ DEFAULT_MAX_ADVANCE_DAYS ฝั่ง backend (จองล่วงหน้าได้ไม่เกินกี่วัน)
let currentMaxBorrowDays = 1; // จำนวนวันยืมสูงสุดของอุปกรณ์ที่กำลังจอง
let activeBooking = null; // รายการที่ยังไม่จบของฉัน (รอรับของ/กำลังยืม/เกินกำหนด) — มีได้สูงสุด 1 รายการ

document.addEventListener("DOMContentLoaded", async () => {
  currentUser = await requireAuth("student");
  if (!currentUser) return; // requireAuth เด้งหน้าไปแล้วถ้าไม่ผ่าน

  document.getElementById("welcome-text").textContent =
    `สวัสดี, ${currentUser.first_name || currentUser.username}`;

  if (currentUser.is_suspended) {
    const banner = document.getElementById("suspended-banner");
    banner.textContent = currentUser.suspended_until
      ? `บัญชีของคุณถูกพักสิทธิ์การจองอุปกรณ์ใหม่ถึงวันที่ ${formatDate(currentUser.suspended_until)}`
      : "บัญชีของคุณถูกพักสิทธิ์การจองอุปกรณ์ใหม่ชั่วคราว";
    banner.classList.remove("hidden");
  }

  document.getElementById("logout-btn").addEventListener("click", logout);
  updateNavbarAvatar();
  setupTabs();
  setupBookingModal();
  setupProfileModal();
  setupClearMyHistory();

  await loadCategories();
  await loadEquipment();
  await loadBookingHistory();

  document.getElementById("search-input").addEventListener("input", debounce(loadEquipment, 350));
  document.getElementById("category-select").addEventListener("change", loadEquipment);
});

function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => {
        b.classList.remove("border-[var(--navy)]", "text-[var(--navy)]");
        b.classList.add("border-transparent", "text-[var(--ink)]/55");
      });
      btn.classList.add("border-[var(--navy)]", "text-[var(--navy)]");
      btn.classList.remove("border-transparent", "text-[var(--ink)]/55");

      const tab = btn.dataset.tab;
      document.getElementById("tab-borrow").classList.toggle("hidden", tab !== "borrow");
      document.getElementById("tab-history").classList.toggle("hidden", tab !== "history");
      if (tab === "history") loadBookingHistory();
    });
  });
}

async function loadCategories() {
  const { ok, data } = await Api.get("/equipment-categories/");
  if (!ok) return;
  const select = document.getElementById("category-select");
  data.forEach((cat) => {
    const opt = document.createElement("option");
    opt.value = cat.id;
    opt.textContent = cat.name;
    select.appendChild(opt);
  });
}

/** หารายการที่ยังไม่จบของฉัน แล้วโชว์/ซ่อนแถบแจ้งเตือนเหนือรายการอุปกรณ์ */
async function refreshActiveBooking() {
  const { ok, data } = await Api.get("/bookings/");
  activeBooking = ok && Array.isArray(data)
    ? data.find((b) => ["awaiting_pickup", "borrowed", "overdue"].includes(b.status)) || null
    : null;

  let banner = document.getElementById("active-booking-banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "active-booking-banner";
    banner.className = "hidden mb-4 text-sm rounded-lg px-4 py-3";
    banner.style.background = "#fff6e0";
    banner.style.color = "#8a5a00";
    const grid = document.getElementById("equipment-grid");
    grid.parentNode.insertBefore(banner, grid);
  }
  if (activeBooking) {
    banner.textContent =
      `คุณมีรายการ "${activeBooking.equipment_name}" (รหัส ${activeBooking.booking_code}) ค้างอยู่ — ` +
      `1 คนยืมได้ครั้งละ 1 เครื่อง กรุณาคืนอุปกรณ์หรือยกเลิกการจองก่อน จึงจะจองชิ้นใหม่ได้`;
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

async function loadEquipment() {
  await refreshActiveBooking();
  const search = document.getElementById("search-input").value.trim();
  const category = document.getElementById("category-select").value;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (category) params.set("category", category);

  const { ok, data } = await Api.get(`/equipment/?${params.toString()}`);
  const grid = document.getElementById("equipment-grid");
  const emptyMsg = document.getElementById("equipment-empty");
  grid.innerHTML = "";

  if (!ok || !data || data.length === 0) {
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  allEquipment = data;

  data.forEach((eq) => grid.appendChild(renderEquipmentCard(eq)));
}

function renderEquipmentCard(eq) {
  const card = document.createElement("div");
  card.className = "surface rounded-2xl p-5 flex flex-col";

  const outOfStock = eq.available_units === 0;
  const disableBooking = outOfStock || currentUser.is_suspended || Boolean(activeBooking);

  card.innerHTML = `
    <img src="${equipmentImageSrc(eq)}" alt="${eq.name}" class="w-full h-32 object-contain rounded-lg bg-[var(--paper)] p-2 mb-3">
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs font-medium text-[var(--ink)]/50">${eq.category?.name ?? ""}</span>
      <span class="badge ${outOfStock ? "badge-cancelled" : "badge-available"}">
        เหลือ ${eq.available_units}/${eq.total_units}
      </span>
    </div>
    <h3 class="font-display font-medium mb-1.5">${eq.name}</h3>
    <p class="text-xs text-[var(--ink)]/55 mb-4">ยืมได้สูงสุด ${eq.max_borrow_days} วัน/ครั้ง</p>
    <button class="btn btn-primary btn-block mt-auto book-btn" ${disableBooking ? "disabled" : ""}>
      ${outOfStock ? "ของหมดชั่วคราว" : (activeBooking ? "มีรายการค้างอยู่" : "จองอุปกรณ์นี้")}
    </button>
  `;

  card.querySelector(".book-btn").addEventListener("click", () => openBookingModal(eq));
  return card;
}

/** แปลง Date เป็น "YYYY-MM-DD" ตามเวลาท้องถิ่น (toISOString เป็น UTC จะผิดวันตอนก่อน 07:00 น. ของไทย) */
function toISODate(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

function addDaysISO(iso, n) {
  const [y, m, d] = iso.split("-").map(Number);
  return toISODate(new Date(y, m - 1, d + n));
}

/** ล็อกช่องวันที่: เริ่มยืมได้ตั้งแต่วันนี้ถึง +7 วัน / วันคืนไม่ก่อนวันเริ่ม และไม่เกินจำนวนวันยืมสูงสุด */
function syncBookingDates() {
  const form = document.getElementById("booking-form");
  const today = toISODate(new Date());
  form.start_date.min = today;
  form.start_date.max = addDaysISO(today, MAX_ADVANCE_DAYS);

  if (!form.start_date.value || form.start_date.value < today) form.start_date.value = today;
  if (form.start_date.value > form.start_date.max) form.start_date.value = form.start_date.max;

  const start = form.start_date.value;
  const lastReturn = addDaysISO(start, currentMaxBorrowDays - 1); // นับรวมวันเริ่ม เช่น 3 วัน: 10 → 12
  form.end_date.min = start;
  form.end_date.max = lastReturn;
  if (!form.end_date.value || form.end_date.value < start || form.end_date.value > lastReturn) {
    form.end_date.value = lastReturn;
  }

  document.getElementById("modal-equipment-meta").textContent =
    `ยืมได้สูงสุด ${currentMaxBorrowDays} วัน/ครั้ง — คืนได้ไม่เกินวันที่ ${formatDate(lastReturn)} · จองล่วงหน้าได้ไม่เกิน ${MAX_ADVANCE_DAYS} วัน`;
}

function setupBookingModal() {
  const modal = document.getElementById("booking-modal");
  const form = document.getElementById("booking-form");

  form.start_date.addEventListener("change", syncBookingDates);
  form.end_date.addEventListener("change", syncBookingDates);

  document.getElementById("modal-cancel-btn").addEventListener("click", () => modal.classList.add("hidden"));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = document.getElementById("modal-error");
    errorBox.classList.add("hidden");

    const submitBtn = document.getElementById("modal-submit-btn");
    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังจอง...";

    const formData = new FormData(form);
    const { ok, data } = await Api.post("/bookings/", {
      equipment_id: Number(formData.get("equipment_id")),
      start_date: formData.get("start_date"),
      end_date: formData.get("end_date"),
    });

    submitBtn.disabled = false;
    submitBtn.textContent = "ยืนยันจอง";

    if (!ok) {
      errorBox.textContent = extractErrorMessage(data, "จองไม่สำเร็จ กรุณาลองใหม่");
      errorBox.classList.remove("hidden");
      return;
    }

    modal.classList.add("hidden");
    await loadEquipment(); // อัปเดตจำนวนคงเหลือทันที
    alert(`จองสำเร็จ! รหัสการจองของคุณคือ ${data.booking_code} — แสดงรหัสนี้ที่เคาน์เตอร์ตอนมารับของ`);
  });
}

function openBookingModal(eq) {
  const modal = document.getElementById("booking-modal");
  const form = document.getElementById("booking-form");
  form.reset();
  document.getElementById("modal-error").classList.add("hidden");
  form.equipment_id.value = eq.id;
  const modalImg = document.getElementById("modal-equipment-image");
  if (modalImg) modalImg.src = equipmentImageSrc(eq);
  document.getElementById("modal-equipment-name").textContent = eq.name;
  currentMaxBorrowDays = Math.max(1, Number(eq.max_borrow_days) || 1);
  form.start_date.value = "";
  form.end_date.value = "";
  syncBookingDates();

  modal.classList.remove("hidden");
}

/* ========================= เคลียร์ประวัติเก่าของฉัน ========================= */

function setupClearMyHistory() {
  document.getElementById("clear-my-history-btn").addEventListener("click", async () => {
    if (!confirm('ล้างประวัติการยืมของฉันที่ "จบแล้ว" (คืนแล้ว/ยกเลิก) ทั้งหมดทันที? รายการที่ยังไม่จบจะไม่ถูกแตะต้อง')) return;

    const btn = document.getElementById("clear-my-history-btn");
    const original = btn.textContent;
    btn.disabled = true;
    btn.textContent = "กำลังล้าง...";

    const { ok, data } = await Api.post("/bookings/clear-history/", { clear_all: true });

    btn.disabled = false;
    btn.textContent = original;

    if (!ok) { alert(extractErrorMessage(data, "ล้างไม่สำเร็จ")); return; }
    alert(`ล้างประวัติไปแล้ว ${data.deleted_count} รายการ`);
    await loadBookingHistory();
  });
}

async function loadBookingHistory() {
  const { ok, data } = await Api.get("/bookings/");
  const list = document.getElementById("booking-list");
  const emptyMsg = document.getElementById("booking-empty");
  list.innerHTML = "";

  if (!ok || !data || data.length === 0) {
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");

  data.forEach((booking) => list.appendChild(renderBookingRow(booking)));
}

function renderBookingRow(booking) {
  const row = document.createElement("div");
  row.className = "surface rounded-xl p-4 flex flex-wrap items-center justify-between gap-3";

  const statusInfo = getBookingStatusDisplay(booking);
  const isFinished = booking.status === "returned" || booking.status === "cancelled";

  row.innerHTML = `
    <div class="flex items-center gap-3 min-w-0">
      <img src="${booking.equipment_image || fallbackEquipmentImage(booking.equipment_name)}" alt="${booking.equipment_name}"
        class="w-12 h-12 rounded-lg object-contain bg-[var(--paper)] p-1 shrink-0">
      <div class="min-w-0">
        <p class="font-display font-medium text-sm truncate">${booking.equipment_name}</p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">
          รหัส ${booking.booking_code} · ${formatDate(booking.requested_start_date)} – ${formatDate(booking.requested_end_date)}
        </p>
      </div>
    </div>
    <div class="flex items-center gap-3 shrink-0">
      <span class="badge ${statusInfo.css}">${statusInfo.text}</span>
      ${booking.status === "awaiting_pickup" ? `<button class="btn btn-outline-navy !py-1.5 !px-3 text-xs cancel-btn">ยกเลิก</button>` : ""}
      ${isFinished ? `<button class="btn btn-outline-navy !py-1.5 !px-3 text-xs delete-booking-btn" style="color:#c33c3c;border-color:#c33c3c;">ลบ</button>` : ""}
    </div>
  `;

  const deleteBtn = row.querySelector(".delete-booking-btn");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm(`ลบประวัติการยืมรหัส "${booking.booking_code}" ทิ้ง?`)) return;
      const { ok, data } = await Api.delete(`/bookings/${booking.id}/delete/`);
      if (!ok) { alert(extractErrorMessage(data, "ลบไม่สำเร็จ")); return; }
      await loadBookingHistory();
    });
  }

  const cancelBtn = row.querySelector(".cancel-btn");
  if (cancelBtn) {
    cancelBtn.addEventListener("click", async () => {
      if (!confirm("ยืนยันยกเลิกการจองนี้หรือไม่?")) return;
      const { ok, data } = await Api.post(`/bookings/${booking.id}/cancel/`, null);
      if (!ok) {
        alert(extractErrorMessage(data, "ยกเลิกไม่สำเร็จ"));
        return;
      }
      await loadBookingHistory();
      await loadEquipment();
    });
  }

  return row;
}

/* ========================= รูปโปรไฟล์บน navbar ========================= */

function updateNavbarAvatar() {
  const avatar = document.getElementById("navbar-avatar");
  if (!avatar) return;
  if (currentUser && currentUser.profile_image) {
    avatar.src = currentUser.profile_image;
    avatar.classList.remove("hidden");
  } else {
    avatar.classList.add("hidden");
  }
}

/* ========================= โปรไฟล์ของฉัน ========================= */

function resetProfileImageDropzone() {
  const preview = document.getElementById("profile-image-preview");
  const icon = document.getElementById("profile-image-placeholder-icon");
  if (currentUser && currentUser.profile_image) {
    preview.src = currentUser.profile_image;
    preview.classList.remove("hidden");
    icon.classList.add("hidden");
  } else {
    preview.classList.add("hidden");
    icon.classList.remove("hidden");
  }
}

function setupProfileModal() {
  const modal = document.getElementById("profile-modal");
  const profileForm = document.getElementById("profile-form");
  const passwordForm = document.getElementById("password-form");

  document.getElementById("open-profile-btn").addEventListener("click", () => {
    document.getElementById("profile-email-display").value = currentUser.email;
    profileForm.first_name.value = currentUser.first_name || "";
    profileForm.last_name.value = currentUser.last_name || "";
    profileForm.student_id.value = currentUser.student_id || "";
    resetProfileImageDropzone();
    document.getElementById("profile-error").classList.add("hidden");
    document.getElementById("profile-success").classList.add("hidden");
    modal.classList.remove("hidden");
  });

  document.getElementById("profile-modal-close").addEventListener("click", () => modal.classList.add("hidden"));
  document.getElementById("password-modal-close").addEventListener("click", () => modal.classList.add("hidden"));

  document.getElementById("profile-image-input").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) { resetProfileImageDropzone(); return; }
    const preview = document.getElementById("profile-image-preview");
    preview.src = URL.createObjectURL(file);
    preview.classList.remove("hidden");
    document.getElementById("profile-image-placeholder-icon").classList.add("hidden");
  });

  document.querySelectorAll(".profile-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".profile-tab-btn").forEach((b) => {
        b.classList.remove("border-[var(--navy)]", "text-[var(--navy)]");
        b.classList.add("border-transparent", "text-[var(--ink)]/55");
      });
      btn.classList.add("border-[var(--navy)]", "text-[var(--navy)]");
      btn.classList.remove("border-transparent", "text-[var(--ink)]/55");
      const tab = btn.dataset.profileTab;
      profileForm.classList.toggle("hidden", tab !== "edit");
      passwordForm.classList.toggle("hidden", tab !== "password");
    });
  });

  profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = document.getElementById("profile-error");
    const successBox = document.getElementById("profile-success");
    const submitBtn = document.getElementById("profile-submit-btn");
    errorBox.classList.add("hidden");
    successBox.classList.add("hidden");
    submitBtn.disabled = true;

    const fd = new FormData();
    fd.set("first_name", profileForm.first_name.value);
    fd.set("last_name", profileForm.last_name.value);
    fd.set("student_id", profileForm.student_id.value);
    const imageFile = document.getElementById("profile-image-input").files[0];
    if (imageFile) fd.set("profile_image", imageFile);

    const { ok, data } = await Api.postFormData("/auth/me/", fd, { method: "PATCH" });
    submitBtn.disabled = false;

    if (!ok) {
      errorBox.textContent = extractErrorMessage(data, "บันทึกไม่สำเร็จ");
      errorBox.classList.remove("hidden");
      return;
    }

    currentUser = data;
    Api.setSession(Api.getToken(), currentUser);
    document.getElementById("welcome-text").textContent = `สวัสดี, ${currentUser.first_name || currentUser.username}`;
    updateNavbarAvatar();
    document.getElementById("profile-image-input").value = "";
    successBox.textContent = "บันทึกข้อมูลโปรไฟล์สำเร็จแล้ว";
    successBox.classList.remove("hidden");
  });

  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const errorBox = document.getElementById("password-error");
    const successBox = document.getElementById("password-success");
    errorBox.classList.add("hidden");
    successBox.classList.add("hidden");

    const formData = new FormData(passwordForm);
    const { ok, data } = await Api.post("/auth/change-password/", {
      old_password: formData.get("old_password"),
      new_password: formData.get("new_password"),
    });

    if (!ok) {
      errorBox.textContent = extractErrorMessage(data, "เปลี่ยนรหัสผ่านไม่สำเร็จ");
      errorBox.classList.remove("hidden");
      return;
    }
    successBox.textContent = "เปลี่ยนรหัสผ่านสำเร็จแล้ว";
    successBox.classList.remove("hidden");
    passwordForm.reset();
  });
}