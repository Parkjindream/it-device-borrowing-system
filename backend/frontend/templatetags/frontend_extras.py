from django import template
from django.templatetags.static import static

register = template.Library()

# กติกาเดียวกับ fallbackEquipmentImage() ใน static/frontend/js/api.js — แก้ต้องแก้คู่กัน
# (คู่คำค้นในชื่อรุ่น, ไฟล์ภาพ) เรียงตามลำดับความสำคัญ เจออันแรกใช้อันนั้น
_FALLBACK_IMAGES = [
    (("ipad",), "ipad.png"),
    (("esp32",), "esp32.svg"),
    (("esp8266",), "esp8266.svg"),
    (("raspberry", "pi 4", "pi4"), "raspberrypi.svg"),
    (("arduino",), "arduino.svg"),
    (("กล้อง", "camera", "canon"), "camera.png"),
    (("เครื่องพิมพ์", "printer", "laserjet"), "generic.png"),
    (("dell", "latitude"), "dell.png"),
    (("lenovo", "thinkpad"), "lenovo.png"),
    (("โน้ตบุ๊ก", "notebook", "laptop"), "lenovo.png"),
]


def fallback_equipment_image(name: str) -> str:
    n = (name or "").lower()
    for keywords, filename in _FALLBACK_IMAGES:
        if any(k in n for k in keywords):
            return static(f"frontend/img/products/{filename}")
    return static("frontend/img/products/generic.png")


@register.simple_tag
def equipment_image_src(equipment) -> str:
    """รูปจริงที่เจ้าหน้าที่อัปโหลด ถ้ายังไม่มีใช้ภาพประกอบที่เดาจากชื่อรุ่น"""
    if equipment.image:
        return equipment.image.url
    return fallback_equipment_image(equipment.name)
