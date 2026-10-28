import os
import unittest


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


class RepositoryLayoutTests(unittest.TestCase):
    def test_frontend_assets_live_under_frontend_directory(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "frontend", "index.html")))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "frontend", "static", "style.css")))

    def test_backend_source_lives_under_backend_directory(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "backend", "app.py")))
        self.assertTrue(os.path.isfile(os.path.join(ROOT, "backend", "competition_agents.py")))

    def test_flask_serves_moved_frontend_assets(self):
        try:
            import app
        except ModuleNotFoundError as exc:
            self.skipTest(f"runtime dependency unavailable: {exc.name}")

        client = app.app.test_client()
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/static/style.css").status_code, 200)


if __name__ == "__main__":
    unittest.main()
