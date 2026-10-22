/**
 * สถิติการยืม-คืน (หน้าเจ้าหน้าที่ แท็บ "คิวรับ-คืน")
 *
 * - คำนวณจากรายการจองจริงที่ backend ส่งมาอยู่แล้ว (GET /staff/bookings/) ไม่ต้องมี endpoint ใหม่
 * - นับตามวันที่เกิดเหตุการณ์จริงในเขตเวลา Asia/Bangkok:
 *     จอง = created_at, รับของ = picked_up_at, คืนของ = returned_at
 * - อัปเดตอัตโนมัติทุก 10 วินาที (เฉพาะตอนเปิดแท็บคิวอยู่และหน้าเว็บไม่ได้ถูกซ่อน)
 *   และอัปเดตทันทีหลังเจ้าหน้าที่กดยืนยันรับ/คืน (loadSummary เรียก loadStats)
 * - ข้อจำกัดที่ต้องรู้: ถ้าเจ้าหน้าที่ลบรายการประวัติ หรือระบบล้างประวัติเก่า รายการนั้นจะหายจากกราฟด้วย
 */
const StaffStats = (() => {
  const TZ = "Asia/Bangkok";
  const REFRESH_MS = 30000;
  const COLORS = { created: "#f2b04c", picked: "#e24a86", returned: "#1f8f6a" };

  let bookings = [];
  let range = "7"; // "7" | "30" | "w8"
  let loaded = false;
  let busy = false;
  let again = false;
  let timer = null;

  /* ---------- วันที่ (ทำเป็น "YYYY-MM-DD" ตามเวลาไทย แล้วคำนวณบนสตริงล้วน ๆ กัน timezone เพี้ยน) ---------- */
  function dayKey(value) {
    if (!value) return null;
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return null;
    return d.toLocaleDateString("en-CA", { timeZone: TZ });
  }
  function addDays(key, n) {
    const [y, m, d] = key.split("-").map(Number);
    return new Date(Date.UTC(y, m - 1, d + n)).toISOString().slice(0, 10);
  }
  function mondayOf(key) {
    const dow = (new Date(`${key}T00:00:00Z`).getUTCDay() + 6) % 7; // จันทร์ = 0
    return addDays(key, -dow);
  }
  function fmt(key, opts) {
    return new Date(`${key}T00:00:00Z`).toLocaleDateString("th-TH", { ...opts, timeZone: "UTC" });
  }

  /* ---------- สร้างช่องเวลา (bucket) ---------- */
  function buildBuckets(todayKey) {
    const weekly = range === "w8";
    const list = [];
    if (weekly) {
      const thisMonday = mondayOf(todayKey);
      for (let i = 7; i >= 0; i--) {
        const start = addDays(thisMonday, -7 * i);
        const end = addDays(start, 6);
        list.push({
          key: start,
          from: start,
          to: end,
          label: fmt(start, { day: "numeric", month: "short" }),
          title: `${fmt(start, { day: "numeric", month: "short" })} – ${fmt(end, { day: "numeric", month: "short" })}`,
          isNow: todayKey >= start && todayKey <= end,
          created: 0, picked: 0, returned: 0,
        });
      }
    } else {
      const n = Number(range);
      for (let i = n - 1; i >= 0; i--) {
        const key = addDays(todayKey, -i);
        list.push({
          key,
          from: key,
          to: key,
          label: n <= 7
            ? `${fmt(key, { weekday: "short" })} ${fmt(key, { day: "numeric" })}`
            : fmt(key, { day: "numeric", month: "short" }),
          title: fmt(key, { weekday: "long", day: "numeric", month: "long" }),
          isNow: i === 0,
          created: 0, picked: 0, returned: 0,
        });
      }
    }
    return list;
  }

  function compute() {
    const todayKey = dayKey(new Date().toISOString());
    const buckets = buildBuckets(todayKey);
    const index = new Map(buckets.map((b) => [b.key, b]));
    const weekly = range === "w8";
    const bucketOf = (k) => (k ? index.get(weekly ? mondayOf(k) : k) : undefined);
    const rangeStart = buckets[0].from;

    const topMap = new Map();
    const status = { awaiting_pickup: 0, borrowed: 0, overdue: 0, returned: 0, cancelled: 0 };

    bookings.forEach((b) => {
      const c = bucketOf(dayKey(b.created_at));
      if (c) {
        c.created += 1;
        const name = b.equipment_name || "-";
        topMap.set(name, (topMap.get(name) || 0) + 1);
      }
      const p = bucketOf(dayKey(b.picked_up_at));
      if (p) p.picked += 1;
      const r = bucketOf(dayKey(b.returned_at));
      if (r) r.returned += 1;

      if (b.status === "borrowed" || b.status === "overdue") {
        status[b.is_overdue_now ? "overdue" : "borrowed"] += 1;
      } else if (status[b.status] !== undefined) {
        status[b.status] += 1;
      }
    });

    const totals = buckets.reduce(
      (t, b) => ({ created: t.created + b.created, picked: t.picked + b.picked, returned: t.returned + b.returned }),
      { created: 0, picked: 0, returned: 0 },
    );
    const top = [...topMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5);
    return { buckets, totals, top, status, rangeStart, todayKey };
  }

  /* ---------- วาด ---------- */
  function niceScale(max) {
    if (max <= 4) return { top: 4, step: 1 };
    const raw = Math.ceil(max / 4);
    const pow = 10 ** Math.floor(Math.log10(raw));
    const step = [1, 2, 5, 10].map((m) => m * pow).find((s) => s >= raw);
    return { top: step * 4, step };
  }

  function rangeLabel() {
    if (range === "7") return "7 วันล่าสุด";
    if (range === "30") return "30 วันล่าสุด";
    return "8 สัปดาห์ล่าสุด";
  }

  function renderTotals(t) {
    const el = document.getElementById("stats-totals");
    if (!el) return;
    const items = [
      ["จองใหม่", t.created, COLORS.created],
      ["รับของแล้ว", t.picked, COLORS.picked],
      ["คืนของแล้ว", t.returned, COLORS.returned],
    ];
    el.innerHTML = items.map(([label, value, color]) => `
      <div class="stat-chip" style="--c:${color}">
        <span class="stat-chip-num">${value}</span>
        <span class="stat-chip-label">${label}<small>${rangeLabel()}</small></span>
      </div>`).join("");
  }

  function renderChart(buckets, totals) {
    const host = document.getElementById("stats-chart");
    if (!host) return;
    const max = Math.max(0, ...buckets.flatMap((b) => [b.created, b.picked, b.returned]));
    const { top, step } = niceScale(max);
    const ticks = [0, 1, 2, 3, 4].map((i) => i * step);
    const many = buckets.length > 8;
    const everyLabel = buckets.length > 20 ? 5 : 1;
    const empty = totals.created + totals.picked + totals.returned === 0;

    const bar = (cls, value) =>
      `<span class="bar ${cls}" style="height:${(value / top) * 100}%">${value > 0 && !many ? `<b>${value}</b>` : ""}</span>`;

    host.style.setProperty("--n", buckets.length);
    host.classList.toggle("is-many", many);
    host.classList.toggle("is-weekly", range === "w8");
    host.setAttribute(
      "aria-label",
      `กราฟแท่ง ${rangeLabel()}: จอง ${totals.created} ครั้ง รับของ ${totals.picked} ครั้ง คืนของ ${totals.returned} ครั้ง`,
    );

    host.innerHTML = `
      <div class="chart-y" aria-hidden="true">
        ${ticks.map((v) => `<span style="bottom:${(v / top) * 100}%">${v}</span>`).join("")}
      </div>
      <div class="chart-area">
        <div class="chart-grid" aria-hidden="true">
          ${ticks.map((v) => `<i style="bottom:${(v / top) * 100}%"></i>`).join("")}
        </div>
        <div class="chart-cols">
          ${buckets.map((b, i) => `
            <div class="chart-col${b.isNow ? " is-now" : ""}" tabindex="0">
              <div class="chart-bars">${bar("bar-c", b.created)}${bar("bar-p", b.picked)}${bar("bar-r", b.returned)}</div>
              <span class="chart-x${i % everyLabel === 0 || i === buckets.length - 1 ? "" : " is-skip"}">${b.label}</span>
              <div class="chart-tip" role="tooltip">
                <strong>${b.title}${b.isNow ? " (ปัจจุบัน)" : ""}</strong>
                <span><i style="background:${COLORS.created}"></i>จอง <b>${b.created}</b></span>
                <span><i style="background:${COLORS.picked}"></i>รับของ <b>${b.picked}</b></span>
                <span><i style="background:${COLORS.returned}"></i>คืนของ <b>${b.returned}</b></span>
              </div>
            </div>`).join("")}
        </div>
        ${empty ? '<p class="chart-empty">ยังไม่มีการจอง รับ หรือคืนอุปกรณ์ในช่วงนี้</p>' : ""}
      </div>`;
  }

  function hbars(el, rows, emptyText) {
    if (!el) return;
    if (!rows.length) {
      el.innerHTML = `<p class="hbar-empty">${emptyText}</p>`;
      return;
    }
    const max = Math.max(1, ...rows.map((r) => r.value));
    el.innerHTML = rows.map((r) => `
      <div class="hbar" style="--c:${r.color}">
        <div class="hbar-top"><span title="${escapeHtml(r.label)}">${escapeHtml(r.label)}</span><b>${r.value}</b></div>
        <div class="hbar-track"><i style="width:${(r.value / max) * 100}%"></i></div>
      </div>`).join("");
  }

  function render() {
    if (!loaded || !document.getElementById("stats-chart")) return;
    const { buckets, totals, top, status } = compute();
    renderTotals(totals);
    renderChart(buckets, totals);
    hbars(document.getElementById("stats-status"), [
      { label: "รอรับของ", value: status.awaiting_pickup, color: "#f2b04c" },
      { label: "กำลังยืม", value: status.borrowed, color: "#e24a86" },
      { label: "เกินกำหนดคืน", value: status.overdue, color: "#d9434f" },
      { label: "คืนแล้ว (ประวัติ)", value: status.returned, color: "#1f8f6a" },
      { label: "ยกเลิก (ประวัติ)", value: status.cancelled, color: "#a79aa2" },
    ], "ยังไม่มีรายการ");
    hbars(
      document.getElementById("stats-top"),
      top.map(([label, value]) => ({ label, value, color: "#cc2a6c" })),
      "ยังไม่มีการจองในช่วงนี้",
    );
  }

  function setPill(state) {
    const pill = document.getElementById("stats-refresh");
    const text = document.getElementById("stats-updated");
    if (!pill || !text) return;
    pill.classList.toggle("is-error", state === "error");
    pill.classList.toggle("is-busy", state === "busy");
    if (state === "busy") {
      text.textContent = "กำลังอัปเดต…";
    } else if (state === "error") {
      text.textContent = "เชื่อมต่อไม่ได้ · กดเพื่อลองใหม่";
    } else {
      const t = new Date().toLocaleTimeString("th-TH", { timeZone: TZ, hour12: false });
      text.textContent = `สด · อัปเดต ${t}`;
    }
  }

  async function refresh() {
    if (busy) { again = true; return; } // มีคำขอซ้อนระหว่างโหลด: โหลดซ้ำอีกรอบหลังเสร็จ ไม่ทิ้งข้อมูลเก่า
    busy = true;
    setPill("busy");
    try {
      const { ok, data } = await Api.get("/staff/bookings/");
      if (ok && Array.isArray(data)) {
        bookings = data;
        loaded = true;
        render();
        setPill("ok");
      } else {
        setPill("error");
      }
    } catch (e) {
      setPill("error");
    } finally {
      busy = false;
      if (again) { again = false; refresh(); }
    }
  }

  /* ---------- อัปเดตสดอัตโนมัติ ---------- */
  function queueTabVisible() {
    const tab = document.getElementById("tab-queue");
    return !!tab && !tab.classList.contains("hidden");
  }
  function modalOpen() {
    return !!document.querySelector(".modal-backdrop:not(.hidden)");
  }

  function tick(force) {
    if (document.hidden || !queueTabVisible()) return;
    if (!force && modalOpen()) return; // ไม่รีเฟรชทับตอนเจ้าหน้าที่กำลังกรอกหน้าต่างยืนยัน
    if (typeof loadSummary === "function") loadSummary(); // loadSummary จะเรียก loadStats() ต่อให้
    else refresh();
    if (typeof loadQueue === "function") loadQueue();
  }

  function start() {
    const seg = document.getElementById("stats-range");
    if (seg) {
      seg.addEventListener("click", (event) => {
        const btn = event.target.closest("button[data-range]");
        if (!btn) return;
        range = btn.dataset.range;
        seg.querySelectorAll("button").forEach((b) => {
          const on = b === btn;
          b.classList.toggle("is-active", on);
          b.setAttribute("aria-pressed", String(on));
        });
        render();
      });
    }
    const pill = document.getElementById("stats-refresh");
    if (pill) pill.addEventListener("click", () => tick(true));

    if (timer) clearInterval(timer);
    timer = setInterval(() => tick(false), REFRESH_MS);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) tick(false); });
  }

  return { start, refresh, render };
})();

function loadStats() {
  return StaffStats.refresh();
}