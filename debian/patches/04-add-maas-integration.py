--- /dev/null
+++ b/tests/maas-integration.py
@@ -0,0 +1,72 @@
+# TODO
+#  - send ipmi commands to turn on/off nodes
+#  - run import pxe files
+#  - check node states once they're on/off
+#  - check node state changes (declared -> commissionig -> ready)
+import os
+from subprocess import check_output
+import sys
+from unittest import TestCase
+
+from pyvirtualdisplay import Display
+from sst.actions import (
+    assert_url, assert_text_contains, assert_title_contains, click_button,
+    get_element, go_to, write_textfield)
+
+
+sys.path.insert(0, "/usr/share/maas")
+os.environ['DJANGO_SETTINGS_MODULE'] = 'maas.settings'
+from maasserver.models import User
+
+MAAS_URL = "http://10.98.0.13/MAAS"
+ADMIN_USER = "admin"
+PASSWORD = "test"
+
+
+class TestMAASIntegration(TestCase):
+
+    def setUp(self):
+        self.display = Display(visible=0, size=(1280, 1024))
+        self.display.start()
+
+    def tearDown(self):
+        self.display.stop()
+
+    def createadmin(self):
+        """Run sudo maas createsuperuser."""
+        cmd_output = check_output(
+            ["sudo", "maas", "createsuperuser", "--username=%s" % ADMIN_USER,
+            "--email=example@canonical.com", "--noinput"])
+        ## Set password for admin user.
+        try:
+            admin = User.objects.get(username=ADMIN_USER)
+        except User.DoesNotExist:
+            admin = User(username=ADMIN_USER)
+        admin.set_password(PASSWORD)
+        admin.save()
+        return cmd_output
+
+    def installation(self):
+        # Check the installation worked.
+        go_to(MAAS_URL)
+        assert_text_contains(
+            get_element(tag="body"), "No admin user has been created yet")
+
+    def createadmin_and_login(self):
+        ## Creates the admin user.
+        output = self.createadmin()
+        self.assertEqual(output, 'Superuser created successfully.')
+        ## Login with the newly created admin user
+        go_to(MAAS_URL)
+        assert_text_contains(
+            get_element(tag="body"), "Login to lenovo-RD230-01 MAAS")
+        write_textfield("id_username", ADMIN_USER)
+        write_textfield("id_password", PASSWORD)
+        click_button("Login")
+        assert_url("MAAS/")
+        assert_title_contains("Dashboard")
+
+    def test_integration(self):
+        # Run the integration tests in order.
+        self.installation()
+        self.createadmin_and_login()
