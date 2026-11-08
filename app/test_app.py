import os
import unittest
from unittest.mock import patch


with patch.dict(os.environ, {"JWT_SIGNING_KEY": "test-signing-key-that-is-at-least-32-bytes"}):
    with patch("redis.Redis") as redis_client:
        redis_client.return_value.set.return_value = False
        from app import app


class HealthEndpointTest(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_health_returns_ok(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "deliberate-ci-failure"})
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()