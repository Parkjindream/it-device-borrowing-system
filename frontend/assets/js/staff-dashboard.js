let pendingConfirmAction = null; // { bookingId, type: "pickup" | "return" }

document.addEventListener("DOMContentLoaded", async () => {
  const staff = await requireAuth("staff");
  if (!staff) return;

  document.getElementById("welcome-text").textContent = `เจ้าหน้าที่: ${staff.first_name || staff.username}`;
  document.getElementById("logout-btn").addEventListener("click", logout);

  setupTabs();
  setupLookup();
  setupConfirmModal();
  setupEquipmentModal();
  setupStudentManagement();
  setupPenaltySettings();
  setupCategoryManagement();

  document.getElementById("status-filter").addEventListener("change", loadQueue);
  await loadSummary();
  await loadQueue();
});

/* ========================= การ์ดสรุปภาพรวม (โมดูล G) ========================= */

async function loadSummary() {
  const { ok, data } = await Api.get("/staff/dashboard-summary/");
  if (!ok) return;

  const cards = [
    { label: "อุปกรณ์ว่างพร้อมให้ยืม", value: data.available_units, accent: "var(--teal)" },
    { label: "รอรับของ", value: data.awaiting_pickup_count, accent: "var(--amber-dark)" },
    { label: "กำลังยืมอยู่", value: data.borrowed_count, accent: "var(--navy)" },
    { label: "เกินกำหนดคืน", value: data.overdue_count, accent: "#c33c3c" },
  ];

  const container = document.getElementById("summary-cards");
  container.innerHTML = cards.map((c) => `
    <div class="surface rounded-xl p-4">
      <p class="text-2xl font-display font-semibold" style="color:${c.accent}">${c.value}</p>
      <p class="text-xs text-[var(--ink)]/55 mt-1">${c.label}</p>
    </div>
  `).join("");
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
      ["queue", "inventory", "students", "settings", "notifications"].forEach((name) => {
        document.getElementById(`tab-${name}`).classList.toggle("hidden", tab !== name);
      });

      if (tab === "inventory") loadInventory();
      if (tab === "students") loadStudentList();
      if (tab === "settings") { loadPenaltySettings(); loadCategoryList(); }
      if (tab === "notifications") loadNotificationList();
    });
  });
}

/* ========================= คิวรับ-คืนอุปกรณ์ ========================= */

function setupLookup() {
  document.getElementById("lookup-btn").addEventListener("click", async () => {
    const code = document.getElementById("lookup-input").value.trim();
    if (!code) return;

    const resultBox = document.getElementById("lookup-result");
    const notFoundMsg = document.getElementById("lookup-not-found");
    resultBox.classList.add("hidden");
    notFoundMsg.classList.add("hidden");

    const { ok, data } = await Api.get(`/staff/bookings/lookup/?code=${encodeURIComponent(code)}`);
    if (!ok) {
      notFoundMsg.classList.remove("hidden");
      return;
    }
    resultBox.innerHTML = "";
    resultBox.appendChild(renderQueueRow(data, true));
    resultBox.classList.remove("hidden");
  });
}

async function loadQueue() {
  const statusParam = document.getElementById("status-filter").value;
  const { ok, data } = await Api.get(`/staff/bookings/${statusParam ? `?status=${statusParam}` : ""}`);
  const list = document.getElementById("queue-list");
  const emptyMsg = document.getElementById("queue-empty");
  list.innerHTML = "";

  if (!ok || !data || data.length === 0) {
    emptyMsg.classList.remove("hidden");
    return;
  }
  emptyMsg.classList.add("hidden");
  data.forEach((booking) => list.appendChild(renderQueueRow(booking, false)));
}

function renderQueueRow(booking) {
  const row = document.createElement("div");
  row.className = "surface rounded-xl p-4 flex flex-wrap items-center justify-between gap-3";

  const statusInfo = getBookingStatusDisplay(booking);

  let actionHtml = "";
  if (booking.status === "awaiting_pickup") {
    actionHtml = `<button class="btn btn-primary !py-1.5 !px-3 text-xs pickup-btn">ยืนยันรับของ</button>`;
  } else if (booking.status === "borrowed" || booking.status === "overdue") {
    actionHtml = `<button class="btn btn-primary !py-1.5 !px-3 text-xs return-btn">ยืนยันคืนของ</button>`;
  }

  row.innerHTML = `
    <div class="flex items-center gap-3 min-w-0">
      <img src="${booking.equipment_image || fallbackEquipmentImage(booking.equipment_name)}" alt="${booking.equipment_name}"
        class="w-12 h-12 rounded-lg object-contain bg-[var(--paper)] p-1 shrink-0">
      <div class="min-w-0">
        <p class="font-display font-medium text-sm truncate">${booking.equipment_name} <span class="text-[var(--ink)]/40">·</span> ${booking.unit_serial_number}</p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">
          ${booking.student_name || "-"} (${booking.student_id || "-"}) · รหัส ${booking.booking_code}
        </p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">กำหนดคืน ${formatDate(booking.requested_end_date)}</p>
      </div>
    </div>
    <div class="flex items-center gap-3 shrink-0">
      <span class="badge ${statusInfo.css}">${statusInfo.text}</span>
      ${actionHtml}
    </div>
  `;

  const pickupBtn = row.querySelector(".pickup-btn");
  if (pickupBtn) pickupBtn.addEventListener("click", () => openConfirmModal(booking.id, "pickup"));

  const returnBtn = row.querySelector(".return-btn");
  if (returnBtn) returnBtn.addEventListener("click", () => openConfirmModal(booking.id, "return"));

  return row;
}

function setupConfirmModal() {
  const modal = document.getElementById("confirm-modal");
  document.getElementById("confirm-modal-cancel").addEventListener("click", () => modal.classList.add("hidden"));

  document.getElementById("confirm-modal-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!pendingConfirmAction) return;

    const errorBox = document.getElementById("confirm-modal-error");
    errorBox.classList.add("hidden");
    const submitBtn = document.getElementById("confirm-modal-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังยืนยัน...";

    const formData = new FormData(event.target);
    const path = pendingConfirmAction.type === "pickup"
      ? `/staff/bookings/${pendingConfirmAction.bookingId}/confirm-pickup/`
      : `/staff/bookings/${pendingConfirmAction.bookingId}/confirm-return/`;

    const body = { condition_note: formData.get("condition_note") || "" };
    if (pendingConfirmAction.type === "return") {
      body.is_damaged = formData.get("is_damaged") === "on";
    }

    const { ok, data } = await Api.post(path, body);

    submitBtn.disabled = false;
    submitBtn.textContent = "ยืนยัน";

    if (!ok) {
      errorBox.textContent = extractErrorMessage(data, "ทำรายการไม่สำเร็จ");
      errorBox.classList.remove("hidden");
      return;
    }

    modal.classList.add("hidden");
    document.getElementById("lookup-result").classList.add("hidden");
    document.getElementById("lookup-input").value = "";
    await loadSummary();
    await loadQueue();
  });
}

function openConfirmModal(bookingId, type) {
  pendingConfirmAction = { bookingId, type };
  document.getElementById("confirm-modal-title").textContent =
    type === "pickup" ? "ยืนยันการส่งมอบอุปกรณ์" : "ยืนยันการรับคืนอุปกรณ์";
  document.getElementById("damaged-checkbox-wrap").classList.toggle("hidden", type !== "return");
  document.getElementById("confirm-modal-form").reset();
  document.getElementById("confirm-modal-error").classList.add("hidden");
  document.getElementById("confirm-modal").classList.remove("hidden");
}

/* ========================= จัดการคลังอุปกรณ์ ========================= */

async function loadInventory() {
  const { ok, data } = await Api.get("/staff/equipment/");
  const list = document.getElementById("inventory-list");
  list.innerHTML = "";
  if (!ok || !data) return;

  data.forEach((eq) => {
    const row = document.createElement("div");
    row.className = "surface rounded-xl p-4 flex flex-wrap items-center justify-between gap-3";
    row.innerHTML = `
      <div>
        <p class="font-display font-medium text-sm">${eq.name} ${eq.is_active ? "" : '<span class="text-xs text-[#c33c3c]">(ปิดใช้งาน)</span>'}</p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">${eq.category?.name ?? ""} · เหลือ ${eq.available_units}/${eq.total_units} เครื่อง</p>
      </div>
      <div class="flex gap-2">
        <button class="btn btn-outline-navy !py-1.5 !px-3 text-xs add-unit-btn">+ เพิ่มเครื่อง</button>
        <button class="btn btn-outline-navy !py-1.5 !px-3 text-xs toggle-active-btn">${eq.is_active ? "ปิดใช้งาน" : "เปิดใช้งาน"}</button>
      </div>
    `;

    row.querySelector(".add-unit-btn").addEventListener("click", async () => {
      const serial = prompt(`ระบุหมายเลขเครื่อง/ทรัพย์สินของ "${eq.name}" ที่จะเพิ่ม`);
      if (!serial) return;
      const { ok: addOk, data: addData } = await Api.post(`/staff/equipment/${eq.id}/units/`, { serial_number: serial });
      if (!addOk) {
        alert(extractErrorMessage(addData, "เพิ่มไม่สำเร็จ (หมายเลขนี้อาจถูกใช้ไปแล้ว)"));
        return;
      }
      await loadInventory();
    });

    row.querySelector(".toggle-active-btn").addEventListener("click", async () => {
      const { ok: patchOk } = await Api.patch(`/staff/equipment/${eq.id}/`, { is_active: !eq.is_active });
      if (patchOk) loadInventory();
    });

    list.appendChild(row);
  });
}

function setupEquipmentModal() {
  const modal = document.getElementById("equipment-modal");
  document.getElementById("new-equipment-btn").addEventListener("click", async () => {
    const select = document.getElementById("equipment-category-select");
    select.innerHTML = "";
    const { ok, data } = await Api.get("/equipment-categories/");
    if (ok) {
      data.forEach((cat) => {
        const opt = document.createElement("option");
        opt.value = cat.id;
        opt.textContent = cat.name;
        select.appendChild(opt);
      });
    }
    document.getElementById("equipment-form").reset();
    document.getElementById("equipment-modal-error").classList.add("hidden");
    modal.classList.remove("hidden");
  });

  document.getElementById("equipment-modal-cancel").addEventListener("click", () => modal.classList.add("hidden"));

  document.getElementById("equipment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(event.target);
    const errorBox = document.getElementById("equipment-modal-error");

    const { ok, data } = await Api.post("/staff/equipment/", {
      category: Number(formData.get("category")),
      name: formData.get("name"),
      max_borrow_days: Number(formData.get("max_borrow_days")),
      is_active: true,
    });

    if (!ok) {
      errorBox.textContent = extractErrorMessage(data, "บันทึกไม่สำเร็จ");
      errorBox.classList.remove("hidden");
      return;
    }

    modal.classList.add("hidden");
    await loadInventory();
  });
}

/* ========================= จัดการนักศึกษา ========================= */

function showMsg(el, text, isError) {
  el.textContent = text;
  el.style.background = isError ? "#fdecec" : "#eafaf3";
  el.style.color = isError ? "#c33c3c" : "#1f7a4d";
  el.classList.remove("hidden");
}

function setupStudentManagement() {
  document.getElementById("add-student-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const msgBox = document.getElementById("add-student-message");
    const formData = new FormData(form);

    const { ok, data } = await Api.post("/staff/students/", {
      email: formData.get("email"),
      first_name: formData.get("first_name"),
      last_name: formData.get("last_name") || "",
      student_id: formData.get("student_id") || "",
    });

    if (!ok) {
      showMsg(msgBox, extractErrorMessage(data, "เพิ่มไม่สำเร็จ"), true);
      return;
    }
    showMsg(msgBox, `เพิ่ม ${data.email} สำเร็จแล้ว`, false);
    form.reset();
    loadStudentList();
  });

  document.getElementById("import-btn").addEventListener("click", async () => {
    const textarea = document.getElementById("import-textarea");
    const msgBox = document.getElementById("import-message");
    const lines = textarea.value.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length === 0) return;

    const students = lines.map((line) => {
      const [email = "", first_name = "", last_name = "", student_id = ""] = line.split(",").map((s) => s.trim());
      return { email, first_name, last_name, student_id };
    });

    const { ok, data } = await Api.post("/staff/students/import/", { students });
    if (!ok) {
      showMsg(msgBox, extractErrorMessage(data, "นำเข้าไม่สำเร็จ"), true);
      return;
    }
    const errorNote = data.errors && data.errors.length
      ? ` (ข้าม ${data.skipped} แถว: ${data.errors.slice(0, 3).map((e) => `แถว ${e.row} - ${e.reason}`).join(", ")}${data.errors.length > 3 ? " ..." : ""})`
      : "";
    showMsg(msgBox, `นำเข้าสำเร็จ ${data.created} คน${errorNote}`, data.skipped > 0);
    if (data.created > 0) { textarea.value = ""; loadStudentList(); }
  });

  document.getElementById("student-search-input").addEventListener("input", debounce(loadStudentList, 350));
  document.getElementById("student-suspended-only").addEventListener("change", loadStudentList);
}

async function loadStudentList() {
  const search = document.getElementById("student-search-input").value.trim();
  const suspendedOnly = document.getElementById("student-suspended-only").checked;
  const params = new URLSearchParams();
  if (search) params.set("search", search);
  if (suspendedOnly) params.set("suspended", "1");

  const { ok, data } = await Api.get(`/staff/students/?${params.toString()}`);
  const list = document.getElementById("student-list");
  if (!ok || !data) { list.innerHTML = ""; return; }

  if (data.length === 0) {
    list.innerHTML = '<p class="text-sm text-[var(--ink)]/50 text-center py-6">ไม่พบนักศึกษาที่ตรงเงื่อนไข</p>';
    return;
  }

  list.innerHTML = data.map((s) => `
    <div class="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-[var(--line)] px-4 py-3">
      <div>
        <p class="text-sm font-medium">${s.first_name} ${s.last_name || ""} <span class="text-[var(--ink)]/40">·</span> ${s.email}</p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">
          รหัสนักศึกษา ${s.student_id || "-"}
          ${s.is_currently_suspended ? `· <span class="text-[#c33c3c]">พักสิทธิ์ถึง ${s.suspended_until ? formatDate(s.suspended_until) : "-"}</span>` : ""}
        </p>
      </div>
      ${s.is_currently_suspended ? `<button data-student-id="${s.id}" class="btn btn-outline-navy !py-1.5 !px-3 text-xs unsuspend-row-btn">ปลดล็อก</button>` : ""}
    </div>
  `).join("");

  list.querySelectorAll(".unsuspend-row-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const { ok: unsuspendOk, data: unsuspendData } = await Api.post(`/staff/students/${btn.dataset.studentId}/unsuspend/`, null);
      if (!unsuspendOk) { alert(extractErrorMessage(unsuspendData, "ปลดล็อกไม่สำเร็จ")); return; }
      loadStudentList();
    });
  });
}

/* ========================= ตั้งค่าเกณฑ์บทลงโทษ ========================= */

function setupPenaltySettings() {
  document.getElementById("penalty-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const msgBox = document.getElementById("penalty-message");
    const formData = new FormData(event.target);

    const { ok, data } = await Api.patch("/staff/penalty-settings/", {
      booking_expire_hours: Number(formData.get("booking_expire_hours")),
      overdue_days_threshold: Number(formData.get("overdue_days_threshold")),
      suspension_days: Number(formData.get("suspension_days")),
    });

    if (!ok) { showMsg(msgBox, extractErrorMessage(data, "บันทึกไม่สำเร็จ"), true); return; }
    showMsg(msgBox, "บันทึกการตั้งค่าสำเร็จแล้ว มีผลทันที", false);
  });
}

async function loadPenaltySettings() {
  const { ok, data } = await Api.get("/staff/penalty-settings/");
  if (!ok) return;
  const form = document.getElementById("penalty-form");
  form.booking_expire_hours.value = data.booking_expire_hours;
  form.overdue_days_threshold.value = data.overdue_days_threshold;
  form.suspension_days.value = data.suspension_days;
}

/* ========================= หมวดหมู่อุปกรณ์ ========================= */

function setupCategoryManagement() {
  document.getElementById("add-category-btn").addEventListener("click", async () => {
    const input = document.getElementById("new-category-input");
    const msgBox = document.getElementById("category-message");
    const name = input.value.trim();
    if (!name) return;

    const { ok, data } = await Api.post("/staff/equipment-categories/", { name });
    if (!ok) { showMsg(msgBox, extractErrorMessage(data, "เพิ่มไม่สำเร็จ"), true); return; }
    input.value = "";
    msgBox.classList.add("hidden");
    loadCategoryList();
  });
}

async function loadCategoryList() {
  const { ok, data } = await Api.get("/staff/equipment-categories/");
  const list = document.getElementById("category-list");
  if (!ok || !data) return;
  list.innerHTML = data.map((c) => `
    <div class="flex items-center justify-between rounded-lg border border-[var(--line)] px-3.5 py-2 text-sm">
      <span>${c.name}</span>
    </div>
  `).join("") || '<p class="text-sm text-[var(--ink)]/50">ยังไม่มีหมวดหมู่</p>';
}

/* ========================= ประวัติอีเมล (โมดูล E) ========================= */

async function loadNotificationList() {
  const { ok, data } = await Api.get("/staff/notifications/");
  const list = document.getElementById("notification-list");
  const emptyMsg = document.getElementById("notification-empty");
  list.innerHTML = "";

  if (!ok || !data || data.length === 0) { emptyMsg.classList.remove("hidden"); return; }
  emptyMsg.classList.add("hidden");

  list.innerHTML = data.map((n) => `
    <div class="surface rounded-xl p-4 flex flex-wrap items-center justify-between gap-3">
      <div>
        <p class="text-sm font-medium">${n.trigger_label}${n.booking_code ? ` <span class="text-[var(--ink)]/40">·</span> ${n.booking_code}` : ""}</p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">ถึง ${n.email_to || "-"} · ${formatDateTime(n.sent_at)}</p>
        ${!n.is_success ? `<p class="text-xs text-[#c33c3c] mt-0.5">ส่งไม่สำเร็จ: ${n.error_message || "ไม่ทราบสาเหตุ"}</p>` : ""}
      </div>
      <span class="badge ${n.is_success ? "badge-available" : "badge-overdue"}">${n.is_success ? "ส่งสำเร็จ" : "ส่งไม่สำเร็จ"}</span>
    </div>
  `).join("");
}
