/**
 * ui.js — ลูกเล่นด้านหน้าตาเท่านั้น (ไม่แตะ logic ของระบบ ไม่เรียก API)
 *  1) ริปเปิลตอนกดปุ่ม: บอกตำแหน่งจุดกดให้ CSS (.btn::after) ผ่านตัวแปร --rx/--ry
 *  2) เงาใต้ header เมื่อเลื่อนหน้าลงมา
 * ถ้าไฟล์นี้โหลดไม่ขึ้น หน้าเว็บยังใช้งานได้ปกติทุกอย่าง
 */
(function () {
  "use strict";

  document.addEventListener(
    "pointerdown",
    function (e) {
      var btn = e.target.closest && e.target.closest(".btn");
      if (!btn || btn.disabled) return;
      var r = btn.getBoundingClientRect();
      btn.style.setProperty("--rx", ((e.clientX - r.left) / r.width) * 100 + "%");
      btn.style.setProperty("--ry", ((e.clientY - r.top) / r.height) * 100 + "%");
    },
    { passive: true }
  );

  // แท็บที่กดแล้วเลื่อนเข้ากลางแถบ (กรณีแท็บเยอะจนต้องปัดแนวนอนบนมือถือ)
  document.addEventListener("click", function (e) {
    var tab = e.target.closest && e.target.closest(".tab-btn");
    if (tab && tab.scrollIntoView) {
      tab.scrollIntoView({ inline: "center", block: "nearest", behavior: "smooth" });
    }
  });

  var header = document.querySelector(".site-header");
  if (header) {
    var ticking = false;
    var update = function () {
      header.classList.toggle("is-scrolled", window.scrollY > 6);
      ticking = false;
    };
    window.addEventListener(
      "scroll",
      function () {
        if (!ticking) {
          ticking = true;
          requestAnimationFrame(update);
        }
      },
      { passive: true }
    );
    update();
  }
})();
