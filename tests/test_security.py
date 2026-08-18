from douyin_archive.security import CookieCipher, PasswordHasher, redact_secrets


def test_cookie_cipher_round_trip_without_plaintext(master_key: str) -> None:
    cipher = CookieCipher(master_key)
    encrypted = cipher.encrypt(
        [{"domain": ".douyin.com", "name": "sessionid", "value": "secret-value"}]
    )
    assert b"secret-value" not in encrypted
    assert cipher.decrypt(encrypted)[0]["value"] == "secret-value"


def test_password_hash_is_not_plaintext() -> None:
    password = "correct horse battery staple"
    hasher = PasswordHasher()
    encoded = hasher.hash(password)
    assert password not in encoded
    assert hasher.verify(encoded, password)
    assert not hasher.verify(encoded, "wrong password")


def test_redaction_removes_cookie_and_signed_url_values() -> None:
    message = "Cookie: sessionid=abc X-Bogus=xyz https://cdn.test/v.mp4?token=raw"
    redacted = redact_secrets(message)
    assert "abc" not in redacted
    assert "xyz" not in redacted
    assert "raw" not in redacted

