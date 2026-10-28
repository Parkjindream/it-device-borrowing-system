/** @type {import('tailwindcss').Config} */
// ตั้งค่า Tailwind สำหรับคอมไพล์ src/styles.css -> static/frontend/css/style.css (รันจากโฟลเดอร์ backend/frontend/)
// content ครอบคลุมทั้ง HTML และ JS เพราะ student/staff dashboard สร้าง markup ด้วย JS
module.exports = {
  content: ["./templates/**/*.html", "./static/frontend/js/*.js"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Anuphan", "Sarabun", "Noto Sans Thai", "Tahoma", "system-ui", "sans-serif"],
        display: ["Anuphan", "Sarabun", "Noto Sans Thai", "Tahoma", "system-ui", "sans-serif"],
      },
      colors: {
        rose: {
          50: "#fff6f9",
          100: "#ffe8f0",
          200: "#ffcfe0",
          300: "#f9a8c6",
          400: "#f06fa0",
          500: "#e24a86",
          600: "#cc2a6c",
          700: "#a81d58",
          800: "#7e1642",
          900: "#4a0d27",
        },
        ink: "#2b1420",
      },
    },
  },
  plugins: [],
};
