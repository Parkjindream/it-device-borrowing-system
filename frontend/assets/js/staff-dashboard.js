let pendingConfirmAction = null; // { bookingId, type: "pickup" | "return" }
let currentStaff = null;

document.addEventListener("DOMContentLoaded", async () => {
  const staff = await requireAuth("staff");
  if (!staff) return;
  currentStaff = staff;

  document.getElementById("welcome-text").textContent = `เจ้าหน้าที่: ${staff.first_name || staff.username}`;
  document.getElementById("logout-btn").addEventListener("click", logout);

  updateNavbarAvatar();
  setupTabs();
  setupLookup();
  setupConfirmModal();
  setupEquipmentModal();
  setupStudentManagement();
  setupPenaltySettings();
  setupCategoryManagement();
  setupClearData();
  setupProfileModal();

  document.getElementById("status-filter").addEventListener("change", loadQueue);
  setupInventoryFilter();
  await loadSummary();
  await loadQueue();
  StaffStats.start();
});

/* ========================= การ์ดสรุปภาพรวม (โมดูล G) ========================= */

async function loadSummary() {
  if (typeof loadStats === "function") loadStats(); // กราฟสถิติอัปเดตพร้อมการ์ดสรุปเสมอ
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

      if (tab === "queue") { loadSummary(); loadQueue(); }
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

/** จำนวนวันที่ยืมแบบนับรวมวันเริ่ม เช่น ยืม 16 คืน 17 = 2 วัน (อ่านจาก "YYYY-MM-DD" ตรง ๆ ไม่ผ่าน timezone) */
function bookingDurationDays(booking) {
  const [sy, sm, sd] = String(booking.requested_start_date).split("-").map(Number);
  const [ey, em, ed] = String(booking.requested_end_date).split("-").map(Number);
  const days = Math.round((new Date(ey, em - 1, ed) - new Date(sy, sm - 1, sd)) / 86400000) + 1;
  return Number.isFinite(days) ? days : "-";
}

/**
 * การ์ดแถวเดียวในคิวรับ-คืน
 * isLookupResult = true เมื่อเป็นผลลัพธ์จากช่องค้นหารหัสการจอง (เน้นกรอบให้ต่างจากรายการปกติ)
 *
 * รูปนักศึกษา: backend อาจยังไม่ได้ส่ง field รูปมาด้วยก็ได้ (เดิมไม่มี) จึงลองอ่านจากหลายชื่อ field
 * ที่เป็นไปได้ (student_profile_image ตรง ๆ หรือซ้อนอยู่ใน booking.student.profile_image) ถ้าไม่มี
 * เลยจะโชว์ไอคอนคนเปล่า ๆ แทน ไม่พังแม้ backend ยังไม่รองรับฟิลด์นี้
 */
function renderQueueRow(booking, isLookupResult = false) {
  const row = document.createElement("div");
  row.className = `surface rounded-xl p-4 flex flex-wrap items-center justify-between gap-3${
    isLookupResult ? " ring-2 ring-[var(--navy)] ring-offset-2" : ""
  }`;

  const statusInfo = getBookingStatusDisplay(booking);
  const studentPhoto = booking.student_profile_image || (booking.student && booking.student.profile_image) || "";

  let actionHtml = "";
  if (booking.status === "awaiting_pickup") {
    actionHtml = `<button class="btn btn-primary !py-1.5 !px-3 text-xs pickup-btn">ยืนยันรับของ</button>`;
  } else if (booking.status === "borrowed" || booking.status === "overdue") {
    actionHtml = `<button class="btn btn-primary !py-1.5 !px-3 text-xs return-btn">ยืนยันคืนของ</button>`;
  } else if (booking.status === "returned" || booking.status === "cancelled") {
    actionHtml = `<button class="btn btn-outline-navy !py-1.5 !px-3 text-xs delete-booking-btn" style="color:#c33c3c;border-color:#c33c3c;">ลบ</button>`;
  }

  const studentAvatarHtml = studentPhoto
    ? `<img src="${studentPhoto}" alt="รูปนักศึกษา" class="w-5 h-5 rounded-full object-cover border border-[var(--line)] shrink-0">`
    : `<span class="w-5 h-5 rounded-full flex items-center justify-center bg-[var(--paper)] border border-[var(--line)] shrink-0">
         <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" stroke-width="2.5" opacity="0.4"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8"/></svg>
       </span>`;

  row.innerHTML = `
    <div class="flex items-center gap-3 min-w-0">
      <img src="${booking.equipment_image || fallbackEquipmentImage(booking.equipment_name)}" alt="${escapeHtml(booking.equipment_name)}"
        class="w-12 h-12 rounded-lg object-contain bg-[var(--paper)] p-1 shrink-0">
      <div class="min-w-0">
        <p class="font-display font-medium text-sm truncate">${escapeHtml(booking.equipment_name)} <span class="text-[var(--ink)]/40">·</span> ${escapeHtml(booking.unit_serial_number)}</p>
        <div class="flex items-center gap-1.5 mt-0.5">
          ${studentAvatarHtml}
          <p class="text-xs text-[var(--ink)]/55 truncate">
            ${escapeHtml(booking.student_name || "-")} (${escapeHtml(booking.student_id || "-")}) · รหัส ${escapeHtml(booking.booking_code)}
          </p>
        </div>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">
          วันยืม ${formatDate(booking.requested_start_date)} · กำหนดคืน ${formatDate(booking.requested_end_date)}
          <span class="text-[var(--ink)]/40">(${bookingDurationDays(booking)} วัน)</span>
        </p>
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

  const deleteBtn = row.querySelector(".delete-booking-btn");
  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!confirm("ลบรายการนี้ทิ้งถาวรหรือไม่?")) return;
      const { ok, data } = await Api.delete(`/staff/bookings/${booking.id}/delete/`);
      if (!ok) { alert(extractErrorMessage(data, "ลบไม่สำเร็จ")); return; }
      await loadSummary();
      await loadQueue();
    });
  }

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
    row.className = "surface rounded-xl inv-card" + (eq.is_active ? "" : " is-inactive");

    const total = Number(eq.total_units) || 0;
    const avail = Number(eq.available_units) || 0;
    const pct = total > 0 ? Math.round((avail / total) * 100) : 0;
    const level = total === 0 || avail === 0 ? "out" : (pct <= 34 ? "low" : "ok");
    const levelText = total === 0 ? "ยังไม่มีเครื่อง" : (avail === 0 ? "หมดชั่วคราว" : (level === "low" ? "เหลือน้อย" : "พร้อมให้ยืม"));
    const maxDays = eq.max_borrow_days ? ` · ยืมได้สูงสุด ${Number(eq.max_borrow_days)} วัน` : "";

    row.innerHTML = `
      <div class="inv-head">
        <img src="${equipmentImageSrc(eq)}" alt="${escapeHtml(eq.name)}" class="inv-img">
        <div class="inv-info">
          <div class="inv-title">
            <p class="inv-name" title="${escapeHtml(eq.name)}">${escapeHtml(eq.name)}</p>
            <span class="inv-badge ${eq.is_active ? "inv-badge-on" : "inv-badge-off"}">${eq.is_active ? "เปิดใช้งาน" : "ปิดใช้งาน"}</span>
          </div>
          <p class="inv-cat">${escapeHtml(eq.category?.name ?? "")}${maxDays}</p>
          <p class="inventory-specs inv-specs hidden"></p>
        </div>
      </div>

      <div class="inv-stock inv-stock-${level}">
        <div class="inv-stock-top">
          <span class="inv-stock-count"><b>${avail}</b> / ${total} เครื่อง</span>
          <span class="inv-stock-state">${levelText}</span>
        </div>
        <div class="inv-bar" role="progressbar" aria-valuemin="0" aria-valuemax="${total}" aria-valuenow="${avail}" aria-label="จำนวนเครื่องที่ว่าง"><i style="width:${pct}%"></i></div>
      </div>

      <div class="inv-actions">
        <button class="btn btn-primary edit-equipment-btn">แก้ไข</button>
        <div class="inv-stepper" role="group" aria-label="จำนวนเครื่อง">
          <button class="btn btn-outline-navy remove-unit-btn" title="ลดเครื่องที่ว่างอยู่ 1 ชิ้น">− ลดเครื่อง</button>
          <button class="btn btn-outline-navy add-unit-btn" title="เพิ่มเครื่องใหม่ 1 ชิ้น">+ เพิ่มเครื่อง</button>
        </div>
        <button class="btn btn-outline-navy toggle-active-btn">${eq.is_active ? "ปิดใช้งาน" : "เปิดใช้งาน"}</button>
        <button class="btn btn-outline-navy delete-equipment-btn inv-danger">ลบทั้งรุ่น</button>
      </div>
    `;

    // สเปกเป็นข้อความอิสระหลายบรรทัด: โชว์บรรทัดเดียวย่อ ๆ ในรายการ (เต็ม ๆ ดูได้ในหน้าแก้ไข)
    const specsLine = row.querySelector(".inventory-specs");
    const specsText = (eq.specifications || "").trim().replace(/\s*\n\s*/g, " · ");
    if (specsLine && specsText) {
      specsLine.textContent = specsText;
      specsLine.title = eq.specifications;
      specsLine.classList.remove("hidden");
    }

    row.querySelector(".edit-equipment-btn").addEventListener("click", () => openEquipmentModal(eq));

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

    // "- ลดเครื่อง": ลบอุปกรณ์ "ทีละ 1 ชิ้น" ที่ยังว่างอยู่เท่านั้น (ลดจำนวนคงเหลือลง)
    // ชิ้นที่กำลังถูกจอง/ยืมอยู่จะไม่โชว์ให้เลือกลบ ต้องรับคืนหรือยกเลิกการจองก่อนเสมอ
    row.querySelector(".remove-unit-btn").addEventListener("click", async () => {
      const { ok: listOk, data: units } = await Api.get(`/staff/equipment/${eq.id}/units/`);
      if (!listOk) { alert("โหลดรายการเครื่องไม่สำเร็จ"); return; }

      const removable = units.filter((u) => u.status === "available" || u.status === "disabled");
      if (removable.length === 0) {
        alert("ไม่มีเครื่องที่ลบได้ตอนนี้ (เครื่องที่เหลือกำลังถูกจอง/ยืมอยู่ทั้งหมด)");
        return;
      }

      const serialList = removable.map((u) => u.serial_number).join(", ");
      const chosenSerial = prompt(
        `พิมพ์หมายเลขเครื่องที่จะลบออกจาก "${eq.name}"\n\nเครื่องที่ลบได้ตอนนี้: ${serialList}`,
      );
      if (!chosenSerial) return;

      const match = removable.find((u) => u.serial_number === chosenSerial.trim());
      if (!match) { alert("ไม่พบหมายเลขเครื่องนี้ในรายการที่ลบได้ กรุณาพิมพ์ให้ตรงกับที่แสดงไว้"); return; }
      if (!confirm(`ลบเครื่องหมายเลข "${match.serial_number}" ทิ้งถาวร?`)) return;

      const { ok: delOk, data: delData } = await Api.delete(`/staff/units/${match.id}/`);
      if (!delOk) { alert(extractErrorMessage(delData, "ลบไม่สำเร็จ")); return; }
      await loadInventory();
    });

    row.querySelector(".toggle-active-btn").addEventListener("click", async () => {
      const { ok: patchOk } = await Api.patch(`/staff/equipment/${eq.id}/`, { is_active: !eq.is_active });
      if (patchOk) loadInventory();
    });

    row.querySelector(".delete-equipment-btn").addEventListener("click", async () => {
      if (!confirm(`ลบ "${eq.name}" ทิ้งถาวร? (ลบไม่ได้ถ้ามีประวัติการยืมค้างอยู่ — ใช้ "ปิดใช้งาน" แทนได้)`)) return;
      const { ok: delOk, data: delData } = await Api.delete(`/staff/equipment/${eq.id}/`);
      if (!delOk) {
        alert(extractErrorMessage(delData, "ลบไม่สำเร็จ"));
        return;
      }
      await loadInventory();
    });

    row.dataset.search = `${eq.name || ""} ${eq.category?.name ?? ""}`.toLowerCase();
    row.dataset.level = eq.is_active ? level : "off";
    list.appendChild(row);
  });
  applyInventoryFilter();
}

/** ช่องค้นหารุ่นในแท็บคลังอุปกรณ์ (กรองในหน้าเว็บ ไม่เรียก API) + สรุปจำนวนใต้ช่องค้นหา */
function setupInventoryFilter() {
  const input = document.getElementById("inventory-search-input");
  if (input) input.addEventListener("input", applyInventoryFilter);
}

function applyInventoryFilter() {
  const input = document.getElementById("inventory-search-input");
  const q = (input ? input.value : "").trim().toLowerCase();
  const cards = [...document.querySelectorAll("#inventory-list > .inv-card")];
  let shown = 0;
  cards.forEach((card) => {
    const match = !q || (card.dataset.search || "").includes(q);
    card.classList.toggle("hidden", !match);
    if (match) shown += 1;
  });

  const empty = document.getElementById("inventory-empty");
  if (empty) empty.classList.toggle("hidden", cards.length === 0 || shown > 0);

  const summary = document.getElementById("inventory-summary");
  if (summary) {
    const count = (lv) => cards.filter((c) => c.dataset.level === lv).length;
    const attention = count("low") + count("out");
    summary.innerHTML = cards.length
      ? `${q ? `พบ <b>${shown}</b> จาก ` : "ทั้งหมด "}<b>${cards.length}</b> รุ่น`
        + (attention ? ` · <span class="inv-summary-warn">ต้องดูแล ${attention} รุ่น</span>` : "")
        + (count("off") ? ` · ปิดใช้งาน ${count("off")}` : "")
      : "";
  }
}

/** id ของอุปกรณ์ที่กำลังแก้ไข (null = เพิ่มรุ่นใหม่) */
let editingEquipmentId = null;

/** คืนช่องอัปโหลดรูปอุปกรณ์กลับเป็นสถานะว่าง */
function resetEquipmentImageDropzone() {
  document.getElementById("equipment-image-preview").classList.add("hidden");
  document.getElementById("equipment-image-placeholder-icon").classList.remove("hidden");
  document.getElementById("equipment-image-placeholder-text").classList.remove("hidden");
}

/** openEquipmentModal() = เพิ่มรุ่นใหม่ / openEquipmentModal(eq) = แก้ไข + เปลี่ยนรูป */
async function openEquipmentModal(eq = null) {
  editingEquipmentId = eq ? eq.id : null;
  const form = document.getElementById("equipment-form");
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
  form.reset();
  resetEquipmentImageDropzone();

  // ช่องจำนวนเครื่อง: ตอนเพิ่มใหม่ = จำนวนที่จะสร้าง / ตอนแก้ไข = จำนวนเครื่อง "ทั้งหมด" (เพิ่ม-ลดแล้วกดบันทึก)
  const unitsInput = document.getElementById("initial-units-input");
  const unitsLabel = document.getElementById("units-label");
  const unitsHint = document.getElementById("units-hint");
  if (unitsInput) unitsInput.value = eq ? eq.total_units : 1;
  if (unitsLabel) unitsLabel.textContent = eq ? "จำนวนเครื่องทั้งหมด" : "จำนวนเครื่องที่มีตอนนี้";
  if (unitsHint) {
    unitsHint.textContent = eq
      ? "เพิ่ม/ลดตัวเลขแล้วกดบันทึก ระบบจะเพิ่มหรือลบเครื่องที่ว่างให้ตรงจำนวน (เครื่องที่กำลังจอง/ยืมจะไม่ถูกลบ)"
      : "ระบบจะสร้างหมายเลขเครื่องให้อัตโนมัติ (ใส่ 0 ถ้าจะเพิ่มทีหลัง)";
  }

  const title = document.getElementById("equipment-modal-title");
  if (eq) {
    if (title) title.textContent = "แก้ไขรุ่นอุปกรณ์";
    form.name.value = eq.name;
    form.specifications.value = eq.specifications || "";
    form.max_borrow_days.value = eq.max_borrow_days;
    if (eq.category) select.value = eq.category.id;
    if (eq.image) {
      const preview = document.getElementById("equipment-image-preview");
      preview.src = eq.image;
      preview.classList.remove("hidden");
      document.getElementById("equipment-image-placeholder-icon").classList.add("hidden");
      document.getElementById("equipment-image-placeholder-text").classList.add("hidden");
    }
  } else if (title) {
    title.textContent = "เพิ่มรุ่นอุปกรณ์ใหม่";
  }

  document.getElementById("equipment-modal-error").classList.add("hidden");
  document.getElementById("equipment-modal").classList.remove("hidden");
}

function setupEquipmentModal() {
  const modal = document.getElementById("equipment-modal");
  document.getElementById("new-equipment-btn").addEventListener("click", () => openEquipmentModal());
  document.getElementById("equipment-modal-cancel").addEventListener("click", () => modal.classList.add("hidden"));

  // ปุ่ม − / + ข้างช่องจำนวนเครื่อง
  const stepUnits = (delta) => {
    const input = document.getElementById("initial-units-input");
    const next = Math.max(0, Math.min(500, (parseInt(input.value, 10) || 0) + delta));
    input.value = next;
  };
  const minusBtn = document.getElementById("units-minus-btn");
  const plusBtn = document.getElementById("units-plus-btn");
  if (minusBtn) minusBtn.addEventListener("click", () => stepUnits(-1));
  if (plusBtn) plusBtn.addEventListener("click", () => stepUnits(1));

  document.getElementById("equipment-image-input").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (!file) { resetEquipmentImageDropzone(); return; }
    const preview = document.getElementById("equipment-image-preview");
    preview.src = URL.createObjectURL(file);
    preview.classList.remove("hidden");
    document.getElementById("equipment-image-placeholder-icon").classList.add("hidden");
    document.getElementById("equipment-image-placeholder-text").classList.add("hidden");
  });

  document.getElementById("equipment-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    const errorBox = document.getElementById("equipment-modal-error");
    const submitBtn = document.getElementById("equipment-modal-submit");
    submitBtn.disabled = true;
    submitBtn.textContent = "กำลังบันทึก...";

    const formData = new FormData();
    formData.set("category", form.category.value);
    formData.set("name", form.name.value);
    formData.set("specifications", form.specifications.value);
    formData.set("max_borrow_days", form.max_borrow_days.value);
    const unitsInput = document.getElementById("initial-units-input");
    const unitsValue = unitsInput && unitsInput.value !== "" ? unitsInput.value : null;
    if (editingEquipmentId) {
      if (unitsValue !== null) formData.set("target_units", unitsValue);
    } else {
      formData.set("is_active", "true");
      formData.set("initial_units", unitsValue !== null ? unitsValue : "0");
    }
    const imageFile = document.getElementById("equipment-image-input").files[0];
    if (imageFile) formData.set("image", imageFile);

    const { ok, data } = editingEquipmentId
      ? await Api.postFormData(`/staff/equipment/${editingEquipmentId}/`, formData, { method: "PATCH" })
      : await Api.postFormData("/staff/equipment/", formData);

    submitBtn.disabled = false;
    submitBtn.textContent = "บันทึก";

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
      <div class="flex items-center gap-3 min-w-0">
        ${s.profile_image
          ? `<img src="${s.profile_image}" alt="" class="w-9 h-9 rounded-full object-cover border border-[var(--line)] shrink-0">`
          : `<span class="w-9 h-9 rounded-full flex items-center justify-center bg-[var(--paper)] border border-[var(--line)] shrink-0">
               <svg class="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="var(--ink)" stroke-width="2.2" opacity="0.4"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4.4 3.6-8 8-8s8 3.6 8 8"/></svg>
             </span>`}
        <div class="min-w-0">
          <p class="text-sm font-medium truncate">${escapeHtml(s.first_name)} ${escapeHtml(s.last_name)} <span class="text-[var(--ink)]/40">·</span> ${escapeHtml(s.email)}</p>
          <p class="text-xs text-[var(--ink)]/55 mt-0.5">
            รหัสนักศึกษา ${escapeHtml(s.student_id || "-")}
            ${s.is_currently_suspended ? `· <span class="text-[#c33c3c]">พักสิทธิ์ถึง ${s.suspended_until ? formatDate(s.suspended_until) : "-"}</span>` : ""}
          </p>
        </div>
      </div>
      <div class="flex gap-2">
        ${s.is_currently_suspended ? `<button data-student-id="${s.id}" class="btn btn-outline-navy !py-1.5 !px-3 text-xs unsuspend-row-btn">ปลดล็อก</button>` : ""}
      </div>
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

  if (data.length === 0) {
    list.innerHTML = '<p class="text-sm text-[var(--ink)]/50">ยังไม่มีหมวดหมู่</p>';
    return;
  }

  list.innerHTML = data.map((c) => `
    <div class="flex items-center justify-between rounded-lg border border-[var(--line)] px-3.5 py-2 text-sm">
      <span>${escapeHtml(c.name)}</span>
      <button data-category-id="${c.id}" data-category-name="${escapeHtml(c.name)}" class="delete-category-btn text-xs" style="color:#c33c3c;">ลบ</button>
    </div>
  `).join("");

  list.querySelectorAll(".delete-category-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm(`ลบหมวดหมู่ "${btn.dataset.categoryName}" ทิ้ง? (ลบไม่ได้ถ้ายังมีอุปกรณ์รุ่นไหนอยู่ในหมวดนี้)`)) return;
      const { ok: delOk, data: delData } = await Api.delete(`/staff/equipment-categories/${btn.dataset.categoryId}/`);
      if (!delOk) { alert(extractErrorMessage(delData, "ลบไม่สำเร็จ")); return; }
      loadCategoryList();
    });
  });
}

/* ========================= เคลียร์ข้อมูลเก่า ========================= */

function setupClearData() {
  async function clearNotifications(button) {
    // เพิ่ม confirm() ให้สมมาตรกับ clearBookingHistory() — เดิมปุ่มนี้ลบทันทีไม่มีการถามยืนยันเลย
    // ทั้งที่เป็นการลบถาวรและกดได้จาก 2 จุด (แท็บตั้งค่า + แท็บประวัติอีเมล) จึงเสี่ยงกดพลาดง่าย
    if (!confirm("ล้างประวัติอีเมลทั้งหมดทิ้งถาวรตอนนี้?")) return;

    const original = button.textContent;
    button.disabled = true;
    button.textContent = "กำลังล้าง...";
    const { ok, data } = await Api.post("/staff/notifications/clear/", { clear_all: true });
    button.disabled = false;
    button.textContent = original;
    if (!ok) { alert(extractErrorMessage(data, "ล้างไม่สำเร็จ")); return; }
    alert(`ล้างประวัติอีเมลไปแล้ว ${data.deleted_count} รายการ`);
    if (!document.getElementById("tab-notifications").classList.contains("hidden")) loadNotificationList();
  }

  async function clearBookingHistory(button) {
    if (!confirm('ล้างประวัติการยืมที่ "จบแล้ว" (คืนแล้ว/ยกเลิก) ทั้งหมดตอนนี้? รายการที่ยังไม่จบจะไม่ถูกแตะต้อง')) return;
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "กำลังล้าง...";
    const { ok, data } = await Api.post("/staff/bookings/clear-history/", { clear_all: true });
    button.disabled = false;
    button.textContent = original;
    if (!ok) { alert(extractErrorMessage(data, "ล้างไม่สำเร็จ")); return; }
    alert(`ล้างประวัติการยืมไปแล้ว ${data.deleted_count} รายการ`);
    await loadSummary();
    await loadQueue();
  }

  document.getElementById("clear-notifications-btn").addEventListener("click", (e) => clearNotifications(e.target));
  document.getElementById("clear-notifications-now-btn").addEventListener("click", (e) => clearNotifications(e.target));
  document.getElementById("clear-booking-history-btn").addEventListener("click", (e) => clearBookingHistory(e.target));
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
        <p class="text-sm font-medium">${escapeHtml(n.trigger_label)}${n.booking_code ? ` <span class="text-[var(--ink)]/40">·</span> ${escapeHtml(n.booking_code)}` : ""}</p>
        <p class="text-xs text-[var(--ink)]/55 mt-0.5">ถึง ${escapeHtml(n.email_to || "-")} · ${formatDateTime(n.sent_at)}</p>
        ${!n.is_success ? `<p class="text-xs text-[#c33c3c] mt-0.5">ส่งไม่สำเร็จ: ${escapeHtml(n.error_message || "ไม่ทราบสาเหตุ")}</p>` : ""}
      </div>
      <span class="badge ${n.is_success ? "badge-available" : "badge-overdue"}">${n.is_success ? "ส่งสำเร็จ" : "ส่งไม่สำเร็จ"}</span>
    </div>
  `).join("");
}

/* ========================= โปรไฟล์ของฉัน (เจ้าหน้าที่) =========================
   เวอร์ชันย่อของโปรไฟล์นักศึกษา — ตัดฟิลด์ student_id ออกเพราะไม่เกี่ยวกับเจ้าหน้าที่
   ใช้ endpoint เดียวกัน (/auth/me/, /auth/change-password/) เพราะเป็น endpoint
   ของ "ผู้ใช้ที่ล็อกอินอยู่" กลาง ๆ ไม่แยกตาม role */

function updateNavbarAvatar() {
  const avatar = document.getElementById("navbar-avatar");
  if (!avatar) return;
  if (currentStaff && currentStaff.profile_image) {
    avatar.src = currentStaff.profile_image;
    avatar.classList.remove("hidden");
  } else {
    avatar.classList.add("hidden");
  }
}

function resetProfileImageDropzone() {
  const preview = document.getElementById("profile-image-preview");
  const icon = document.getElementById("profile-image-placeholder-icon");
  if (currentStaff && currentStaff.profile_image) {
    preview.src = currentStaff.profile_image;
    preview.classList.remove("hidden");
    icon.classList.add("hidden");
  } else {
    preview.classList.add("hidden");
    icon.classList.remove("hidden");
  }
}

/** ย่อรูปก่อนอัปโหลด: ด้านยาวสุด 800px, JPEG คุณภาพ 0.85 (เหมือนฝั่งนักศึกษา) */
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
    document.getElementById("profile-email-display").value = currentStaff.email;
    profileForm.first_name.value = currentStaff.first_name || "";
    profileForm.last_name.value = currentStaff.last_name || "";
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

    currentStaff = data;
    Api.setSession(Api.getToken(), currentStaff);
    document.getElementById("welcome-text").textContent = `เจ้าหน้าที่: ${currentStaff.first_name || currentStaff.username}`;
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