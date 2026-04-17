"""Symmetric encryption using SSH agent.

This module replicates the logic of the 'ssh-crypt' package to avoid a strict
dependency on vulnerable versions of paramiko and cryptography.
"""

import base64
import random
from collections import deque
from hashlib import sha3_256

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from paramiko.agent import AgentKey


VALID_SSH_NAME = ["ssh-rsa", "ssh-ed25519"]
NONCE_LENGTH = 64


class EncryptingCipher:
    """AES-CBC encryptor with PKCS7 padding."""

    def __init__(self, key: bytes):
        """Initialize the encryptor.

        :param key: The encryption key.
        """
        self.buf = deque()
        self.algorithm = algorithms.AES
        self.block_size = int(self.algorithm.block_size / 8)

        iv = random.getrandbits(self.block_size * 8).to_bytes(self.block_size, "big")
        self.cipher = Cipher(self.algorithm(key), modes.CBC(iv), backend=default_backend()).encryptor()
        self.padder = padding.PKCS7(self.block_size * 8).padder()
        self.buf.extend(iv)

    def encode(self, data: bytes) -> bytes:
        """Encrypt the given data.

        :param data: The data to encrypt.
        :return: The encrypted data (including IV if it's the first block).
        """
        if not data:
            padded_data = self.padder.finalize()
            self.buf.extend(self.cipher.update(padded_data) + self.cipher.finalize())
        else:
            padded_data = self.padder.update(data)
            self.buf.extend(self.cipher.update(padded_data))

        result = bytes(self.buf)
        self.buf.clear()

        return result


class DecryptingCipher:
    """AES-CBC decryptor with PKCS7 unpadding."""

    def __init__(self, key: bytes):
        """Initialize the decryptor.

        :param key: The encryption key.
        """
        self.buf = deque()
        self.key = key
        self.algorithm = algorithms.AES
        self.block_size = int(self.algorithm.block_size / 8)
        self.unpadder = padding.PKCS7(self.block_size * 8).unpadder()
        self.cipher = None

    def _configure_cipher(self, iv: bytes):
        """Configure the cipher with the extracted IV.

        :param iv: The initialization vector.
        """
        self.cipher = Cipher(self.algorithm(self.key), modes.CBC(iv), backend=default_backend()).decryptor()

    def decode(self, data: bytes) -> bytes:
        """Decrypt the given data.

        :param data: The data to decrypt.
        :return: The decrypted data.
        """
        self.buf.extend(data)

        if self.cipher is None and len(self.buf) >= self.block_size:
            iv = bytes([self.buf.popleft() for _ in range(self.block_size)])
            self._configure_cipher(iv)

        if not data:
            remaining_data = bytes(self.buf)
            self.buf.clear()

            decrypted = self.cipher.update(remaining_data) + self.cipher.finalize()
            return self.unpadder.update(decrypted) + self.unpadder.finalize()

        decrypted = self.cipher.update(bytes(self.buf))
        self.buf.clear()

        return self.unpadder.update(decrypted)


class Encryptor:
    """High-level encryptor using SSH agent."""

    def __init__(self, ssh_key: AgentKey, binary: bool = False):
        """Initialize the encryptor.

        :param ssh_key: The SSH key to use for signing.
        :param binary: Whether to return raw bytes or base85 encoded string.
        """
        if ssh_key.name not in VALID_SSH_NAME:
            raise ValueError(f"Incompatible key type: {ssh_key.name}. Only RSA or ED25519 are supported.")

        self.binary = binary
        self.nonce = base64.b85encode(random.getrandbits(NONCE_LENGTH).to_bytes(int(NONCE_LENGTH / 8), "big"))

        key = sha3_256(ssh_key.sign_ssh_data(self.nonce)).digest()
        self.encoder = EncryptingCipher(key)
        self.header_sent = False

    def send(self, data: bytes) -> bytes:
        """Encrypt and return data.

        :param data: The data to encrypt.
        :return: The encrypted data.
        """
        encrypted = self.encoder.encode(data)

        if not self.binary:
            encrypted = base64.b85encode(encrypted)

        if not self.header_sent:
            result = self.nonce + b":" + encrypted
            self.header_sent = True
            return result

        return encrypted


class Decryptor:
    """High-level decryptor using SSH agent."""

    def __init__(self, ssh_key: AgentKey, binary: bool = False):
        """Initialize the decryptor.

        :param ssh_key: The SSH key to use for signing.
        :param binary: Whether the input is raw bytes or base85 encoded string.
        """
        if ssh_key.name not in VALID_SSH_NAME:
            raise ValueError(f"Incompatible key type: {ssh_key.name}. Only RSA or ED25519 are supported.")

        self.ssh_key = ssh_key
        self.binary = binary
        self.decoder = None
        self.buf = deque()

    def _init_decoder(self, nonce: bytes):
        """Initialize the decoder with the extracted nonce.

        :param nonce: The nonce extracted from the header.
        """
        key = sha3_256(self.ssh_key.sign_ssh_data(nonce)).digest()
        self.decoder = DecryptingCipher(key)

    def send(self, data: bytes) -> bytes:
        """Decrypt and return data.

        :param data: The data to decrypt.
        :return: The decrypted data.
        """
        self.buf.extend(data)

        if self.decoder is None:
            combined = bytes(self.buf)

            if b":" in combined:
                nonce, rest = combined.split(b":", 1)
                self.buf = deque(rest)
                self._init_decoder(nonce)
            else:
                return b""

        if not self.binary:
            # Base85 needs to be decoded in blocks
            available = len(self.buf)
            to_decode = available - (available % 5)

            if to_decode == 0 and data:
                return b""

            block = bytes([self.buf.popleft() for _ in range(to_decode)])
            raw_data = base64.b85decode(block)
        else:
            raw_data = bytes(self.buf)
            self.buf.clear()

        return self.decoder.decode(raw_data)


def encrypt(data: str | bytes, ssh_key: AgentKey, binary: bool = False) -> bytes:
    """Encrypt data using an SSH key.

    :param data: The data to encrypt.
    :param ssh_key: The SSH key to use for signing.
    :param binary: Whether to return raw bytes or base85 encoded string.
    :return: The encrypted data.
    """
    if isinstance(data, str):
        data = data.encode("utf-8")

    encryptor = Encryptor(ssh_key, binary=binary)
    return encryptor.send(data) + encryptor.send(b"")


class E:
    """A wrapper for decrypting data lazily or as a string."""

    def __init__(self, data: str | bytes, ssh_key: AgentKey, binary: bool = False):
        """Initialize the decryptor wrapper.

        :param data: The encrypted data.
        :param ssh_key: The SSH key to use for signing.
        :param binary: Whether the input is raw bytes or base85 encoded string.
        """
        self.binary = binary
        self.ssh_key = ssh_key

        if isinstance(data, str):
            data = data.encode("utf-8")

        self.data = data

    def __bytes__(self) -> bytes:
        """Return the decrypted data as bytes."""
        decryptor = Decryptor(self.ssh_key, binary=self.binary)
        return decryptor.send(self.data) + decryptor.send(b"")

    def __str__(self) -> str:
        """Return the decrypted data as a string."""
        return self.__bytes__().decode("utf-8")
