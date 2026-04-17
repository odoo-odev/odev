from unittest.mock import MagicMock

from odev.common import ssh_crypt

from tests.fixtures import OdevTestCase


class TestSSHCrypt(OdevTestCase):
    def setUp(self):
        super().setUp()
        self.mock_key = MagicMock()
        self.mock_key.name = "ssh-rsa"
        self.mock_key.sign_ssh_data.side_effect = lambda data: b"signed-" + data

    def test_encryption_decryption_string(self):
        plaintext = "my secret password"
        encrypted = ssh_crypt.encrypt(plaintext, self.mock_key)

        # Verify it's bytes and has the nonce:encrypted structure
        self.assertIsInstance(encrypted, bytes)
        self.assertIn(b":", encrypted)

        # Decrypt
        decrypted = str(ssh_crypt.E(encrypted, self.mock_key))
        self.assertEqual(decrypted, plaintext)

    def test_encryption_decryption_bytes(self):
        plaintext = b"binary \x00 data"
        encrypted = ssh_crypt.encrypt(plaintext, self.mock_key, binary=True)

        self.assertIsInstance(encrypted, bytes)

        # Decrypt
        decrypted = bytes(ssh_crypt.E(encrypted, self.mock_key, binary=True))
        self.assertEqual(decrypted, plaintext)

    def test_incompatible_key(self):
        self.mock_key.name = "ssh-dss"
        with self.assertRaises(ValueError):
            ssh_crypt.encrypt("test", self.mock_key)

    def test_multiple_chunks(self):
        # Test the streaming-like interface (Encryptor/Decryptor)
        encryptor = ssh_crypt.Encryptor(self.mock_key)
        chunk1 = encryptor.send(b"hello ")
        chunk2 = encryptor.send(b"world")
        chunk3 = encryptor.send(b"")  # Finalize

        full_encrypted = chunk1 + chunk2 + chunk3

        decryptor = ssh_crypt.Decryptor(self.mock_key)
        # Decrypt in different chunk sizes
        d1 = decryptor.send(full_encrypted[:10])
        d2 = decryptor.send(full_encrypted[10:])
        d3 = decryptor.send(b"")  # Finalize

        self.assertEqual(d1 + d2 + d3, b"hello world")
