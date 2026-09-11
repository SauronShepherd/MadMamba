from __future__ import annotations

import unittest

from madmamba.sanitizer import DiagnosticPayloadRejectedError, sanitize_diagnostic_payload


class SanitizerAdversarialTest(unittest.TestCase):
    def test_sensitive_key_variants_are_redacted(self) -> None:
        sanitized = sanitize_diagnostic_payload(
            {
                "API-KEY": "super-secret-value",
                " private key ": "pem-material",
                "Authorization": "Basic abc123",
                "safe": "visible",
            }
        )
        self.assertEqual(sanitized["API-KEY"], "***REDACTED***")
        self.assertEqual(sanitized[" private key "], "***REDACTED***")
        self.assertEqual(sanitized["Authorization"], "***REDACTED***")
        self.assertEqual(sanitized["safe"], "visible")

    def test_denied_keys_fail_closed_recursively_and_case_insensitively(self) -> None:
        for denied in ("locals", "LOCALS", "return-value", "Arguments"):
            with self.subTest(denied=denied):
                with self.assertRaises(DiagnosticPayloadRejectedError):
                    sanitize_diagnostic_payload({"nested": {denied: {"password": "leak"}}})

    def test_unicode_and_embedded_credentials_are_redacted_without_losing_text(self) -> None:
        sanitized = sanitize_diagnostic_payload(
            {
                "message": "用户 token=秘密-123; bearer eyJabc.def.ghi café",
                "already": "***REDACTED***",
            }
        )
        message = sanitized["message"]
        self.assertIn("用户", message)
        self.assertIn("café", message)
        self.assertNotIn("秘密-123", message)
        self.assertNotIn("eyJabc.def.ghi", message)
        self.assertEqual(sanitized["already"], "***REDACTED***")

    def test_deep_payload_is_bounded_without_recursion_failure(self) -> None:
        payload: dict[str, object] = {"leaf": "ok"}
        for index in range(40):
            payload = {f"level_{index}": payload}
        sanitized = sanitize_diagnostic_payload(payload)
        cursor: object = sanitized
        for _ in range(13):
            self.assertIsInstance(cursor, dict)
            cursor = next(iter(cursor.values()))  # type: ignore[union-attr]
        self.assertEqual(cursor, "<depth-limit>")

    def test_long_bearer_value_is_redacted_without_echoing_secret(self) -> None:
        secret = "A" * 100_000
        sanitized = sanitize_diagnostic_payload({"message": f"Bearer {secret}"})
        self.assertEqual(sanitized["message"], "Bearer ***REDACTED***")
        self.assertNotIn(secret[:64], sanitized["message"])


if __name__ == "__main__":
    unittest.main()
