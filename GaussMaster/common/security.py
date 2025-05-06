# Copyright (c) 2025 Huawei Technologies Co.,Ltd.
#
# openGauss is licensed under Mulan PSL v2.
# You can use this software according to the terms and conditions of the Mulan PSL v2.
# You may obtain a copy of Mulan PSL v2 at:
#
#          http://license.coscl.org.cn/MulanPSL2
#
# THIS SOFTWARE IS PROVIDED ON AN "AS IS" BASIS, WITHOUT WARRANTIES OF ANY KIND,
# EITHER EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO NON-INFRINGEMENT,
# MERCHANTABILITY OR FIT FOR A PARTICULAR PURPOSE.
# See the Mulan PSL v2 for more details.

"""Avoid leaking plain-text passwords."""
import base64
import hmac
import os
import random
import re
import secrets
import string
from hashlib import pbkdf2_hmac

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from GaussMaster import global_vars
from GaussMaster.common.metadatabase.dao.dynamic_config import dynamic_config_set, dynamic_config_get
from GaussMaster.constants import ENCRYPTION_PART_B

SALT_LENGTH = 16
HASH_ITERATIONS = 10000
IV_LENGTH = 16
ENCRYPTION_PART_LENGTH = 32
WORKKEY_LENGTH = 16
LOWERCASE_PATTERN = re.compile(r'[a-z]')
UPPERCASE_PATTERN = re.compile(r'[A-Z]')
DIGIT_PATTERN = re.compile(r'\d')
SPECIAL_CHAR = '[~`!@#$%^&*()-_+\\|{};:,<.>/?]'


def calculate_cipher_length(data_length: int) -> int:
    if data_length == 16:
        return 44


def unsafe_random_string(length):
    """Used to generate a fixed-length random
    string which is not used in the sensitive scenarios."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(random.choice(alphabet) for _ in range(length))


def safe_random_string(length):
    """Used to generate a fixed-length random
    string which is used in the security and cryptography."""
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def generate_an_iv() -> str:
    """Generate and return an initialization vector for AES."""
    return safe_random_string(16)


def encrypt(s1: str, s2: str, iv: str, pt: str) -> str:
    """Encrypt a series of plain text with two strings.
    :param s1: string #1
    :param s2: string #2
    :param iv: initialization vector, used by AES256-CBC
    :param pt: plain text
    :return: cipher text
    """
    if pt == '':
        return ''
    nb = 16  # the number of block including cipher and plain text
    h = hmac.new(s1.encode(), s2.encode(), digestmod='sha256')
    master_key = h.hexdigest()[:32].encode()  # 32 bytes means AES256
    cipher = AES.new(master_key, AES.MODE_CBC, iv.encode())
    pt = pt.encode()
    ct = cipher.encrypt(pad(pt, nb))
    return base64.b64encode(ct).decode()


def decrypt(s1: str, s2: str, iv: str, ct: str) -> str:
    """Decrypt a series of cipher text with two strings.
    :param s1: string #1
    :param s2: string #2
    :param iv: initialization vector, used by AES256-CBC
    :param ct: cipher text
    :return: plain text
    """
    if ct == '':
        return ''
    nb = 16  # the number of block including cipher and plain text
    h = hmac.new(s1.encode(), s2.encode(), digestmod='sha256')
    master_key = h.hexdigest()[:32].encode()  # 32 bytes means AES256
    cipher = AES.new(master_key, AES.MODE_CBC, iv.encode())
    ct = base64.b64decode(ct)
    pt = unpad(cipher.decrypt(ct), nb)
    return pt.decode()


class EncryptedText:
    def __init__(self, plain_text):
        self.iv = generate_an_iv()
        self.s1 = safe_random_string(16)
        self.s2 = safe_random_string(16)
        self.cipher_text = encrypt(self.s1, self.s2, self.iv, plain_text)

    def get(self):
        return decrypt(self.s1, self.s2, self.iv, self.cipher_text)

    def __repr__(self):
        return self.get()

    def __eq__(self, other):
        if isinstance(other, str):
            return self.get() == other
        elif isinstance(other, EncryptedText):
            return self.get() == other.get()
        else:
            return False


class Encryption:

    @classmethod
    def encrypt(cls, text: str) -> str:
        encryption_components = EncryptionComponents()
        part_a = encryption_components.get_part_a()
        part_b = encryption_components.get_part_b()
        salt = encryption_components.generate_salt()
        iv = encryption_components.generate_iv()
        workkey = secrets.token_bytes(WORKKEY_LENGTH)
        root_key = generate_root_key(part_a, part_b, salt)
        workkey_cipher = aes_encrypt(workkey, root_key, iv)
        cipher = aes_encrypt(text.encode(), workkey, iv)
        combined_cipher = encryption_components.combine_salt_iv_workkey_cipher_cipher(
            salt, iv, workkey_cipher, cipher)
        return base64.b64encode(combined_cipher).decode('utf-8')

    @classmethod
    def decrypt(cls, combined_cipher: str) -> str:
        encryption_components = EncryptionComponents()
        part_a = encryption_components.get_part_a()
        part_b = encryption_components.get_part_b()
        salt, iv, workkey_cipher, cipher = encryption_components.parse_combined_cipher(
            base64.b64decode(combined_cipher.encode('utf-8')))
        root_key = generate_root_key(part_a, part_b, salt)
        workkey = aes_decrypt(workkey_cipher, root_key, iv)
        plain_bytes = aes_decrypt(cipher, workkey, iv)
        return plain_bytes.decode()


class EncryptionComponents:
    # This variable depends on the initialization of the global variable.
    ENCRYPTION_PART_B_PATH = os.path.join(global_vars.confpath, ENCRYPTION_PART_B)

    def __init__(self):
        self.__part_a = secrets.token_bytes(ENCRYPTION_PART_LENGTH)
        self.__part_b = secrets.token_bytes(ENCRYPTION_PART_LENGTH)

        if not (self.get_part_a() and self.get_part_b()):
            self.initialize_part_b()
            self.initialize_part_a()

    def initialize_part_a(self):
        dynamic_config_set('encryption_components', 'part_a', base64.b64encode(self.__part_a).decode())

    def initialize_part_b(self):
        with open(EncryptionComponents.ENCRYPTION_PART_B_PATH, 'bw') as file_h:
            file_h.write(self.__part_b)

    @classmethod
    def get_part_a(cls) -> bytes:
        str_part_a = dynamic_config_get('encryption_components', 'part_a')
        if str_part_a:
            return base64.b64decode(str_part_a)

    @classmethod
    def get_part_b(cls) -> bytes:
        with open(EncryptionComponents.ENCRYPTION_PART_B_PATH, 'rb') as file_h:
            return file_h.read()

    @classmethod
    def generate_iv(cls) -> bytes:
        return secrets.token_bytes(IV_LENGTH)

    @classmethod
    def generate_salt(cls) -> bytes:
        return secrets.token_bytes(SALT_LENGTH)

    @classmethod
    def parse_combined_cipher(cls, combined_cipher):
        """
        This function parses the combined cipher into salt, initialization vector, work key cipher and cipher.

        Parameters:
        combined_cipher -- The combined cipher

        Returns:
        salt -- The salt value
        iv -- The initialization vector
        workkey_cipher -- The cipher of the work key
        cipher -- The cipher

        """
        salt = combined_cipher[:SALT_LENGTH]
        iv = combined_cipher[SALT_LENGTH:SALT_LENGTH + IV_LENGTH]
        workkey_cipher_len = calculate_cipher_length(WORKKEY_LENGTH)
        workkey_cipher = combined_cipher[SALT_LENGTH + IV_LENGTH:SALT_LENGTH + IV_LENGTH + workkey_cipher_len]
        cipher = combined_cipher[SALT_LENGTH + IV_LENGTH + workkey_cipher_len:]
        return salt, iv, workkey_cipher, cipher

    @classmethod
    def combine_salt_iv_workkey_cipher_cipher(cls, salt, iv, workkey_cipher, cipher):
        return salt + iv + workkey_cipher + cipher


def aes_encrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """
    To encrypt work key and token based on AES256.
    :param key: The private key.
    :param data: The raw data in bytes.
    :param iv: The initial vector.
    :return: The encrypted data.
    """
    data = pad(data, AES.block_size)
    aes = AES.new(key, AES.MODE_CBC, iv)
    return base64.b64encode(aes.encrypt(data))


def aes_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
    """
    To decrypt work key and token based on AES256.
    :param key: The private key.
    :param data: The encrypted data in bytes.
    :param iv: The initial vector.
    :return: The decrypted data.
    """
    aes = AES.new(key, AES.MODE_CBC, iv)
    return unpad(aes.decrypt(base64.b64decode(data)), AES.block_size)


def xor_bytes(bytes1: bytes, bytes2: bytes) -> bytes:
    """Perform bitwise XOR operation on two byte sequences.

    Args:
        bytes1 (bytes): The first byte sequence.
        bytes2 (bytes): The second byte sequence.

    Returns:
        bytes: The result of the XOR operation between the two byte sequences.

    Raises:
        ValueError: If the lengths of the two byte sequences are not equal.
    """
    if len(bytes1) != len(bytes2):
        raise ValueError("The two byte sequences must have the same length")

    return bytes(b1 ^ b2 for b1, b2 in zip(bytes1, bytes2))


def generate_root_key(root_key_part_a: bytes, root_key_part_b: bytes,
                      salt: bytes, hash_iterations=HASH_ITERATIONS) -> bytes:
    """
    Root key is generated when needed instead of being stored locally.
    :return: The root key in bytes.
    """
    # To collect different key parts from different paths

    combined = xor_bytes(root_key_part_a, root_key_part_b)
    return pbkdf2_hmac('sha256', combined, salt, hash_iterations)


def check_password_strength(password: str, username: str = None):
    """
    testify the strength of password
    1. must contain at least 8 characters
    2. must contain a combination of at least two types of characters: [lowercase, uppercase, digit, special_char]
    3. must not be same with username
    """
    if len(password) < 8:
        return False

    if username and username == password:
        return False

    password_strength = 0
    password_strength += int(bool(LOWERCASE_PATTERN.search(password)))
    password_strength += int(bool(UPPERCASE_PATTERN.search(password)))
    password_strength += int(bool(DIGIT_PATTERN.search(password)))
    password_strength += int(any(x in SPECIAL_CHAR for x in password))
    return 2 <= password_strength <= 4
