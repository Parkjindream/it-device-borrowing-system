/**
 * ตัวช่วยกลางสำหรับเรียก Django REST API ทุกจุดในระบบ
 * เก็บ token ไว้ใน localStorage (คีย์ "auth_token") และแปะ header
 * "Authorization: Token <token>" ให้อัตโนมัติทุกครั้งที่มี token อยู่
 */
const Api = {
  getToken() {
    return localStorage.getItem("auth_token");
  },

  setSession(token, user) {
    localStorage.setItem("auth_token", token);
    localStorage.setItem("auth_user", JSON.stringify(user));
  },

  getUser() {
    const raw = localStorage.getItem("auth_user");
    return raw ? JSON.parse(raw) : null;
  },

  clearSession() {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user");
  },

  isLoggedIn() {
    return Boolean(this.getToken());
  },

  /**
   * เรียก API กลาง — คืนค่า { ok, status, data } เสมอ ไม่ throw
   * ทำให้ทุกหน้าเขียนโค้ดจัดการ error แบบเดียวกันได้หมด
   */
  async request(path, { method = "GET", body = null, auth = true } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (auth && this.getToken()) {
      headers["Authorization"] = `Token ${this.getToken()}`;
    }

    let response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, {
        method,
        headers,
        body: body ? JSON.stringify(body) : null,
      });
    } catch (networkError) {
      return {
        ok: false,
        status: 0,
        data: { detail: "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้ กรุณาตรวจสอบว่า backend เปิดอยู่หรือไม่" },
      };
    }

    // 204 No Content ไม่มี body ให้ parse
    let data = null;
    if (response.status !== 204) {
      try {
        data = await response.json();
      } catch (_e) {
        data = null;
      }
    }

    if (response.status === 401) {
      // token หมดอายุ/ไม่ถูกต้อง → เคลียร์ session แล้วเด้งไปหน้า login
      this.clearSession();
      if (!location.pathname.endsWith("login.html")) {
        const redirect = encodeURIComponent(location.pathname);
        location.href = `/login.html?next=${redirect}`;
      }
    }

    return { ok: response.ok, status: response.status, data };
  },

  get(path) {
    return this.request(path, { method: "GET" });
  },
  post(path, body, opts = {}) {
    return this.request(path, { method: "POST", body, ...opts });
  },
  patch(path, body) {
    return this.request(path, { method: "PATCH", body });
  },

  /** ใช้ตอนต้องอัปโหลดไฟล์ (เช่นรูปอุปกรณ์) — ส่งเป็น multipart/form-data */
  async postFormData(path, formData, { method = "POST" } = {}) {
    const headers = {};
    if (this.getToken()) headers["Authorization"] = `Token ${this.getToken()}`;
    let response;
    try {
      response = await fetch(`${API_BASE_URL}${path}`, { method, headers, body: formData });
    } catch (networkError) {
      return { ok: false, status: 0, data: { detail: "เชื่อมต่อเซิร์ฟเวอร์ไม่ได้" } };
    }
    let data = null;
    if (response.status !== 204) {
      try { data = await response.json(); } catch (_e) { data = null; }
    }
    return { ok: response.ok, status: response.status, data };
  },

  delete(path) {
    return this.request(path, { method: "DELETE" });
  },
};

/**
 * รวมข้อความ error จาก DRF (ซึ่งมาได้หลายรูปแบบ: {detail: "..."} หรือ
 * {field: ["error1","error2"]}) ให้เป็นข้อความเดียวอ่านง่าย แสดงให้ผู้ใช้เห็น
 */
function extractErrorMessage(data, fallback = "เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง") {
  if (!data) return fallback;
  if (typeof data.detail === "string") {
    // DRF ส่ง throttle message เป็นภาษาอังกฤษ ("Request was throttled...") แปลให้อ่านง่าย
    if (data.detail.toLowerCase().includes("throttled")) {
      const match = data.detail.match(/available in (\d+) second/);
      const seconds = match ? Number(match[1]) : null;
      const waitText = seconds ? `ประมาณ ${Math.ceil(seconds / 60)} นาที` : "สักครู่";
      return `ทำรายการนี้บ่อยเกินไป กรุณารอ${waitText}แล้วลองใหม่`;
    }
    return data.detail;
  }
  if (Array.isArray(data.non_field_errors)) return data.non_field_errors.join(" ");
  const firstKey = Object.keys(data)[0];
  if (firstKey && Array.isArray(data[firstKey])) return data[firstKey].join(" ");
  return fallback;
}

/** แปลงชื่อสถานะ booking (ภาษาอังกฤษจาก backend) เป็น label ไทย + สี badge */
const BOOKING_STATUS_LABEL = {
  awaiting_pickup: { text: "รอรับของ", css: "badge-awaiting" },
  borrowed: { text: "กำลังยืม", css: "badge-borrowed" },
  overdue: { text: "เกินกำหนด", css: "badge-overdue" },
  returned: { text: "คืนแล้ว", css: "badge-returned" },
  cancelled: { text: "ยกเลิก", css: "badge-cancelled" },
};

/**
 * ใช้ข้อมูลนี้แสดงป้ายสถานะเสมอ แทนที่จะอ่าน booking.status ตรง ๆ
 *
 * เหตุผล: booking.status ในฐานข้อมูลจะเปลี่ยนเป็น "overdue" ก็ต่อเมื่อ scheduled job
 * (run_daily_due_date_checks) รันไปแล้วเท่านั้น ซึ่งรันวันละครั้ง ไม่ใช่เรียลไทม์
 * แต่ backend คำนวณ "is_overdue_now" สดทุกครั้งที่เรียก API จึงต้องเช็คค่านี้ก่อน
 * เพื่อให้หน้าจอถูกต้องตรงความจริงเสมอ แม้ job รายวันจะยังไม่ทันรัน
 */
function getBookingStatusDisplay(booking) {
  if (booking.is_overdue_now && (booking.status === "borrowed" || booking.status === "overdue")) {
    return BOOKING_STATUS_LABEL.overdue;
  }
  return BOOKING_STATUS_LABEL[booking.status] || { text: booking.status, css: "badge-cancelled" };
}

function formatDate(isoStringOrDate) {
  if (!isoStringOrDate) return "-";
  const d = new Date(isoStringOrDate);
  return d.toLocaleDateString("th-TH", { year: "numeric", month: "short", day: "numeric" });
}

/**
 * ภาพประกอบอุปกรณ์: ถ้าเจ้าหน้าที่อัปโหลดรูปจริงไว้ (eq.image) ใช้รูปนั้นเลย
 * ถ้ายังไม่มี ใช้ภาพประกอบสำเร็จรูปที่เดาจากชื่อรุ่น (อยู่ที่ assets/img/products/)
 * เพื่อให้นักศึกษาเห็นว่าอุปกรณ์หน้าตาประมาณไหน แม้เจ้าหน้าที่ยังไม่ได้ถ่ายรูปจริงอัปโหลด
 */
function fallbackEquipmentImage(name) {
  const n = (name || "").toLowerCase();
  const isNested = location.pathname.includes("/student/") || location.pathname.includes("/staff/");
  const base = `${isNested ? "../" : ""}assets/img/products/`;
  if (n.includes("ipad")) return base + "ipad.png";
  if (n.includes("esp32")) return base + "esp32.svg";
  if (n.includes("esp8266")) return base + "esp8266.svg";
  if (n.includes("raspberry") || n.includes("pi 4") || n.includes("pi4")) return base + "raspberrypi.svg";
  if (n.includes("arduino")) return base + "arduino.svg";
  if (n.includes("กล้อง") || n.includes("camera") || n.includes("canon")) return base + "camera.png";
  if (n.includes("เครื่องพิมพ์") || n.includes("printer") || n.includes("laserjet")) return base + "generic.png";
  if (n.includes("dell") || n.includes("latitude")) return base + "dell.png";
  if (n.includes("lenovo") || n.includes("thinkpad")) return base + "lenovo.png";
  if (n.includes("โน้ตบุ๊ก") || n.includes("notebook") || n.includes("laptop")) 
  return base + "lenovo.png";
}

function equipmentImageSrc(eq) {
  return eq && eq.image ? eq.image : fallbackEquipmentImage(eq ? eq.name : "");
}

function formatDateTime(isoString) {
  if (!isoString) return "-";
  const d = new Date(isoString);
  return d.toLocaleString("th-TH", { dateStyle: "medium", timeStyle: "short" });
}

/** หน่วงการเรียกฟังก์ชันจนกว่าจะหยุดพิมพ์ครบ `delay` มิลลิวินาที — ใช้กับช่องค้นหา */
function debounce(fn, delay) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}