from unittest.mock import MagicMock, patch

from odev.common.errors import OdevError
from odev.common.store.tables.secrets import SecretStore

from tests.fixtures import OdevTestCase


class TestSecretStore(OdevTestCase):
    """Tests for the (de)ciphering of secrets through the ssh-agent."""

    def setUp(self):
        super().setUp()
        self.mock_key = MagicMock()
        self.mock_key.name = "ssh-rsa"
        self.mock_key.fingerprint = "SHA256:test"
        self.mock_key.comment = "test key"
        self.mock_key.sign_ssh_data.side_effect = lambda data: b"signed-" + data

        self.mock_agent = MagicMock()
        self.mock_agent.get_keys.return_value = (self.mock_key,)

        for patcher in (
            patch("odev.common.store.tables.secrets.SSHAgent", return_value=self.mock_agent),
            patch.object(SecretStore, "config", self.odev.config),
            patch.dict("os.environ", {"ODEV_NO_SSH_AGENT": ""}),
        ):
            self.addCleanup(patcher.stop)
            patcher.start()

    def test_encrypt_closes_the_ssh_agent(self):
        SecretStore.encrypt("password")
        self.mock_agent.close.assert_called_once()

    def test_decrypt_closes_the_ssh_agent(self):
        ciphertext = SecretStore.encrypt("password")
        self.mock_agent.close.reset_mock()

        self.assertEqual(SecretStore.decrypt(ciphertext), "password")
        self.mock_agent.close.assert_called_once()

    def test_ssh_agent_closed_on_error(self):
        self.mock_agent.get_keys.return_value = ()

        with self.assertRaises(OdevError):
            SecretStore.encrypt("password")

        self.mock_agent.close.assert_called_once()

    def test_keys_are_usable_while_the_agent_is_open(self):
        calls: list[str] = []
        self.mock_key.sign_ssh_data.side_effect = lambda data: calls.append("sign") or b"signed-" + data
        self.mock_agent.close.side_effect = lambda: calls.append("close")

        SecretStore.encrypt("password")

        self.assertIn("sign", calls)
        self.assertEqual(calls[-1], "close")

    def test_preferred_key_is_tried_first(self):
        other_key = MagicMock()
        other_key.name = "ssh-rsa"
        other_key.fingerprint = "SHA256:other"
        other_key.comment = "other key"
        other_key.sign_ssh_data.side_effect = lambda data: b"other-" + data
        self.mock_agent.get_keys.return_value = (other_key, self.mock_key)
        SecretStore.config.security.encryption_key = self.mock_key.fingerprint

        SecretStore.encrypt("password")

        self.mock_key.sign_ssh_data.assert_called()
        other_key.sign_ssh_data.assert_not_called()
