let currentUser = null;
let allEquipment = [];
const MAX_ADVANCE_DAYS = 7; // ต้องตรงกับ DEFAULT_MAX_ADVANCE_DAYS ฝั่ง backend (จองล่วงหน้าได้ไม่เกินกี่วัน)
let currentMaxBorrowDays = 1; // จำนวนวันยืมสูงสุดของอุปกรณ์ที่กำลังจอง (เป็นแค่เพดาน ไม่ใช่จำนวนวันที่บังคับ)
let activeBooking = null; // รายการที่ยังไม่จบของฉัน (รอรับของ/กำลังยืม/เกินกำหนด) — มีได้สูงสุด 1 รายการ

document.addEventListener("DOMContentLoaded", async () => {
  currentUser = await requireAuth("student");
  if (!currentUser) return; // requireAuth เด้งหน้าไปแล้วถ้าไม่ผ่าน

  document.getElementById("welcome-text").textContent =
    `สวัสดี, ${currentUser.first_name || currentUser.username}`;

  renderSuspendedBanner();

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
  startLiveRefresh();
});

/** พักสิทธิ์ "จริง ณ ตอนนี้" (ใช้ค่าที่ backend คำนวณให้ ซึ่งคำนึงถึงวันหมดพักสิทธิ์แล้ว) */
function isSuspendedNow() {
  if (!currentUser) return false;
  return Boolean(currentUser.is_currently_suspended ?? currentUser.is_suspended);
}

function renderSuspendedBanner() {
  const banner = document.getElementById("suspended-banner");
  if (!banner) return;
  if (isSuspendedNow()) {
    banner.textContent = currentUser.suspended_until
      ? `บัญชีของคุณถูกพักสิทธิ์การจองอุปกรณ์ใหม่ถึงวันที่ ${formatDate(currentUser.suspended_until)}`
      : "บัญชีของคุณถูกพักสิทธิ์การจองอุปกรณ์ใหม่ชั่วคราว";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

/**
 * อัปเดตหน้าเองทุก 30 วินาที (และทันทีที่กลับมาเปิดแท็บ) — ไม่ต้องกดรีเฟรชเอง
 * เช่น เจ้าหน้าที่กดรับคืนแล้ว ปุ่ม "จอง" ที่ถูกล็อกจะปลดเอง / ถูกพักสิทธิ์แล้วแถบเตือนขึ้นเอง
 * ไม่รีเฟรชทับตอนมีหน้าต่างจอง/โปรไฟล์เปิดอยู่ (กันข้อมูลที่กำลังกรอกหาย)
 */
const LIVE_REFRESH_MS = 30000;
let liveRefreshBusy = false;

async function liveRefreshOnce() {
  if (liveRefreshBusy || document.hidden) return;
  if (document.querySelector(".modal-backdrop:not(.hidden)")) return;
  liveRefreshBusy = true;
  try {
    const me = await Api.get("/auth/me/");
    if (me.ok && me.data) {
      currentUser = me.data;
      renderSuspendedBanner();
    }
    const historyTab = document.getElementById("tab-history");
    if (historyTab && !historyTab.classList.contains("hidden")) await loadBookingHistory();
    else await loadEquipment();
  } finally {
    liveRefreshBusy = false;
  }
}

function startLiveRefresh() {
  setInterval(liveRefreshOnce, LIVE_REFRESH_MS);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) liveRefreshOnce(); });
}

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
  const disableBooking = outOfStock || isSuspendedNow() || Boolean(activeBooking);

  card.innerHTML = `
    <img src="${equipmentImageSrc(eq)}" alt="${eq.name}" class="w-full h-32 object-contain rounded-lg bg-[var(--paper)] p-2 mb-3">
    <div class="flex items-center justify-between mb-3">
      <span class="text-xs font-medium text-[var(--ink)]/50">${eq.category?.name ?? ""}</span>
      <span class="badge ${outOfStock ? "badge-cancelled" : "badge-available"}">
        เหลือ ${eq.available_units}/${eq.total_units}
      </span>
    </div>
    <h3 class="font-display font-medium mb-1.5">${eq.name}</h3>
    <p class="text-xs text-[var(--ink)]/55 mb-2">ยืมได้สูงสุด ${eq.max_borrow_days} วัน/ครั้ง</p>
    <p class="text-xs text-[var(--ink)]/65 mb-4 card-specs hidden" style="white-space: pre-line; display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden;"></p>
    <button class="btn btn-primary btn-block mt-auto book-btn" ${disableBooking ? "disabled" : ""}>
      ${outOfStock ? "ของหมดชั่วคราว" : (activeBooking ? "มีรายการค้างอยู่" : "จองอุปกรณ์นี้")}
    </button>
  `;

  const specsText = (eq.specifications || "").trim();
  if (specsText) {
    const specsEl = card.querySelector(".card-specs");
    specsEl.textContent = specsText;
    specsEl.classList.remove("hidden");
  }

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

/** จำนวนวันแบบนับรวมวันเริ่ม เช่น 10 → 12 = 3 วัน */
function inclusiveDays(startISO, endISO) {
  const [sy, sm, sd] = startISO.split("-").map(Number);
  const [ey, em, ed] = endISO.split("-").map(Number);
  return Math.round((new Date(ey, em - 1, ed) - new Date(sy, sm - 1, sd)) / 86400000) + 1;
}

/**
 * ล็อกช่องวันที่ให้อยู่ในกรอบที่อนุญาตเท่านั้น — "ไม่เติมวันให้เอง" นักศึกษาเลือกวันเริ่มยืม/วันคืนเองทั้งหมด:
 * - ตอนเปิดหน้าจอง ทั้งสองช่องว่าง (วว/ดด/ปปปป) จนกว่านักศึกษาจะเลือกเอง
 * - วันเริ่มยืม: ตั้งแต่วันนี้ ถึงล่วงหน้าไม่เกิน MAX_ADVANCE_DAYS
 * - วันคืน: ไม่ก่อนวันเริ่ม และไม่เกินเพดานวันยืมสูงสุดของอุปกรณ์ — ในกรอบนี้เลือกกี่วันก็ได้ (1 วันขึ้นไป)
 * - ถ้าค่าที่เลือก/พิมพ์เองหลุดกรอบ (หรือวันคืนหลุดกรอบหลังเปลี่ยนวันเริ่ม) จะล้างช่องนั้นให้ว่าง
 *   พร้อมบอกเหตุผล ไม่แอบแก้เป็นวันอื่นให้
 */
function syncBookingDates() {
  const form = document.getElementById("booking-form");
  const hint = document.getElementById("modal-duration-summary");
  const today = toISODate(new Date());
  const latestStart = addDaysISO(today, MAX_ADVANCE_DAYS);
  let warning = "";

  form.start_date.min = today;
  form.start_date.max = latestStart;
  let start = form.start_date.value;
  if (start && (start < today || start > latestStart)) {
    warning = `เลือกวันเริ่มยืมได้ตั้งแต่ ${formatDate(today)} ถึง ${formatDate(latestStart)} เท่านั้น`;
    form.start_date.value = "";
    start = "";
  }

  // กรอบวันคืน: เลือกวันเริ่มแล้ว = start..start+เพดาน-1 / ยังไม่เลือก = กรอบรวมกว้างสุด (ไว้ให้ปฏิทินไม่บล็อกเกินจำเป็น)
  const endMin = start || today;
  const endMax = addDaysISO(start || latestStart, currentMaxBorrowDays - 1);
  form.end_date.min = endMin;
  form.end_date.max = endMax;
  let end = form.end_date.value;
  if (end && (end < endMin || end > endMax)) {
    warning = warning || (start
      ? `วันคืนต้องอยู่ระหว่าง ${formatDate(endMin)} ถึง ${formatDate(endMax)} (ยืมได้สูงสุด ${currentMaxBorrowDays} วัน) กรุณาเลือกวันคืนใหม่`
      : `วันคืนเลือกได้ไม่เกิน ${formatDate(endMax)} กรุณาเลือกใหม่`);
    form.end_date.value = "";
    end = "";
  }

  document.getElementById("modal-equipment-meta").textContent =
    `ยืมได้สูงสุด ${currentMaxBorrowDays} วัน/ครั้ง — เลือกวันเริ่มยืมและวันคืนเองได้อิสระ (กี่วันก็ได้ ไม่เกินที่กำหนด) ` +
    `· จองล่วงหน้าได้ไม่เกิน ${MAX_ADVANCE_DAYS} วัน`;

  hint.style.color = warning ? "#c33c3c" : "";
  if (warning) {
    hint.textContent = warning;
  } else if (start && end) {
    hint.textContent = `ยืมทั้งหมด ${inclusiveDays(start, end)} วัน (${formatDate(start)} – ${formatDate(end)})`;
  } else if (start) {
    hint.textContent = `เลือกวันคืนได้ไม่เกิน ${formatDate(endMax)}`;
  } else {
    hint.textContent = "";
  }
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

    const formData = new FormData(form);
    if (!formData.get("start_date") || !formData.get("end_date")) {
      errorBox.textContent = "กรุณาเลือกวันเริ่มยืมและวันคืนให้ครบ";
      errorBox.classList.remove("hidden");
      return;
    }

    const submitBtn = document.getElementById("modal-submit-btn");
    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังจอง...";

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
  // เปิดมาทั้งสองช่องต้องว่าง (ไม่เติมวันให้) — นักศึกษาเลือกวันเริ่มยืม/วันคืนเองภายใต้เพดานของอุปกรณ์
  form.start_date.value = "";
  form.end_date.value = "";
  syncBookingDates();

  // สเปกอุปกรณ์ (ข้อความอิสระ): ใช้ textContent + white-space:pre-line เพื่อคงการขึ้นบรรทัดและกัน HTML injection
  const specsText = (eq.specifications || "").trim();
  const specsWrap = document.getElementById("modal-equipment-specs-wrap");
  document.getElementById("modal-equipment-specs").textContent = specsText;
  specsWrap.classList.toggle("hidden", !specsText);

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
          รหัส ${booking.booking_code} · วันยืม ${formatDate(booking.requested_start_date)} – กำหนดคืน ${formatDate(booking.requested_end_date)}
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

/** ย่อรูปก่อนอัปโหลด: ด้านยาวสุด 800px, JPEG คุณภาพ 0.85 (รูปโปรไฟล์ไม่ต้องใหญ่ → อัปเร็ว ไม่ชนขีดจำกัดขนาดไฟล์) */
function compressImage(file, maxSide = 800, quality = 0.85) {
  return new Promise((resolve) => {
    if (!file || !file.type.startsWith("image/")) return resolve(file);
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => resolve(blob ? new File([blob], "profile.jpg", { type: "image/jpeg" }) : file),
        "image/jpeg",
        quality
      );
    };
    img.onerror = () => { URL.revokeObjectURL(url); resolve(file); };
    img.src = url;
  });
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
    const originalLabel = submitBtn.textContent;
    submitBtn.textContent = "กำลังอัปโหลด...";

    const fd = new FormData();
    fd.set("first_name", profileForm.first_name.value);
    fd.set("last_name", profileForm.last_name.value);
    fd.set("student_id", profileForm.student_id.value);
    const imageFile = document.getElementById("profile-image-input").files[0];
    if (imageFile) fd.set("profile_image", await compressImage(imageFile));

    const { ok, status, data } = await Api.postFormData("/auth/me/", fd, { method: "PATCH" });
    submitBtn.disabled = false;
    submitBtn.textContent = originalLabel;

    if (!ok) {
      errorBox.textContent = status === 413
        ? "ไฟล์รูปใหญ่เกินไป กรุณาเลือกรูปที่เล็กกว่านี้"
        : extractErrorMessage(data, "บันทึกไม่สำเร็จ");
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