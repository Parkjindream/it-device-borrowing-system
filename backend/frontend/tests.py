"""ทดสอบหน้าเว็บ (Django templates): สิทธิ์เข้าหน้า, redirect ลิงก์เก่า, หน้าแรก render จากฐานข้อมูล"""
from django.test import TestCase, override_settings
from django.urls import clear_url_caches, reverse

from rental.models import Equipment, EquipmentCategory, EquipmentUnit, User


class PageTests(TestCase):
    def setUp(self):
        category = EquipmentCategory.objects.create(name="บอร์ดไมโครคอนโทรลเลอร์")
        self.equipment = Equipment.objects.create(category=category, name="ESP32 DevKit")
        EquipmentUnit.objects.create(equipment=self.equipment, serial_number="ESP-001")
        self.student = User.objects.create_user(
            username="s1", email="s1@example.ac.th", password="Pass!word123", role=User.Role.STUDENT,
        )
        self.staff = User.objects.create_user(
            username="staff", email="staff@example.ac.th", password="Pass!word123", role=User.Role.STAFF,
        )

    def test_home_renders_equipment_from_database(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ESP32 DevKit")
        self.assertContains(resp, "ว่าง 1/1")
        self.assertContains(resp, "/static/frontend/img/products/esp32.svg")
        self.assertContains(resp, 'href="/login/"')

    def test_home_links_to_own_dashboard_when_logged_in(self):
        self.client.force_login(self.staff)
        resp = self.client.get("/")
        self.assertContains(resp, 'href="/staff/"')
        self.assertNotContains(resp, 'href="/login/"')

    def test_dashboard_requires_login(self):
        for url in ["/staff/", "/student/"]:
            resp = self.client.get(url)
            self.assertRedirects(resp, f"/login/?next={url}", fetch_redirect_response=False)

    def test_dashboard_redirects_to_own_role(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get("/staff/"), "/student/")
        self.assertEqual(self.client.get("/student/").status_code, 200)

        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get("/student/"), "/staff/")
        self.assertEqual(self.client.get("/staff/").status_code, 200)

    def test_login_page_redirects_when_already_logged_in(self):
        self.assertEqual(self.client.get("/login/").status_code, 200)
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get("/login/"), "/student/")

    def test_logout_page_clears_session(self):
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get("/logout/"), "/login/")
        self.assertRedirects(self.client.get("/student/"), "/login/?next=/student/", fetch_redirect_response=False)

    def test_old_html_links_redirect_and_keep_query(self):
        resp = self.client.get("/reset-password.html?uid=abc&token=xyz")
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(resp["Location"], "/reset-password/?uid=abc&token=xyz")
        self.assertEqual(self.client.get("/staff/dashboard.html")["Location"], "/staff/")

    def test_public_pages_render(self):
        for name in ["forgot-password", "reset-password", "set-password"]:
            self.assertEqual(self.client.get(reverse(f"frontend:{name}")).status_code, 200)


class AdminToggleTests(TestCase):
    def _reload_urls(self):
        import importlib

        from config import urls

        importlib.reload(urls)
        clear_url_caches()

    def tearDown(self):
        self._reload_urls()

    @override_settings(ENABLE_DJANGO_ADMIN=False)
    def test_admin_hidden_when_disabled(self):
        self._reload_urls()
        self.assertEqual(self.client.get("/api/admin/").status_code, 404)

    @override_settings(ENABLE_DJANGO_ADMIN=True)
    def test_admin_available_when_enabled(self):
        self._reload_urls()
        self.assertEqual(self.client.get("/api/admin/").status_code, 302)  # เด้งไปหน้า login ของ admin
