from backend.reliability_graph.secrets import KeyVault
from backend.reliability_graph.storage import Storage


def test_key_vault_encrypts_and_fingerprints_without_plaintext(tmp_path):
    vault = KeyVault(tmp_path, "test-master-secret")
    plaintext = "tk-test-secret-value"

    token = vault.encrypt(plaintext)

    assert plaintext not in token
    assert vault.decrypt(token) == plaintext
    assert vault.fingerprint(plaintext) == "tk-t...alue"


def test_provider_keys_are_scoped_by_user(tmp_path):
    storage = Storage(tmp_path / "rg.sqlite")
    storage.init_db()

    storage.save_provider_key("user_a", "tinker", "ciphertext", "tk-...alue")

    assert storage.get_provider_key_ciphertext("user_a", "tinker") == "ciphertext"
    assert storage.get_provider_key_ciphertext("user_b", "tinker") is None
