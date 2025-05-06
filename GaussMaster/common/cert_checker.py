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

"""cert checker"""
import os
import re
import subprocess

from GaussMaster.common import utils
from GaussMaster.common.exceptions import CertCheckException


class CertVerifier(object):

    def __init__(self, file_name, text, is_ca=False) -> None:
        """
        init cert checker
        """
        self.file_name = file_name
        self.text = text
        self.is_ca = is_ca

    def verify_basic_constraints(self):
        if self.is_ca:
            ans = re.findall('Basic Constraints:[\s\S]*CA:TRUE',
                             self.text,
                             flags=re.IGNORECASE)
            return bool(ans)
        else:
            return True

    def verify_algorithm(self):
        """
        Get openssl output and verify the public key algorithm and key length.
        """
        ALGORITHM_DETAILS = {
            'id-ecpublickey': {'min_length': 224, 'recommended_length': 256},
            'rsaencryption': {'min_length': 2048, 'recommended_length': 3072},
            'dsaencryption': {'min_length': 2048, 'recommended_length': 3072},
        }

        ans = re.findall(
            r'Public Key Algorithm:[ ]*(.+)[\s\S]*Public\-Key:[ ]\([ ]*(\d+)[ ]*bit[ ]*\)',
            self.text,
            flags=re.IGNORECASE
        )
        if not (ans and len(ans[-1]) == 2):
            raise ValueError('Failed to get valid detail of public key algorithm.')

        algor, length = ans[-1]
        algor = algor.lower().strip()
        length = int(length)

        if algor not in ALGORITHM_DETAILS:
            raise ValueError(f"Unsupported algorithm: '{algor}'. "
                             f"Please use one of the following: ECIES, RSA, or DSA.")

        details = ALGORITHM_DETAILS[algor]
        if length < details['min_length']:
            raise ValueError(
                f'The encrypted length of the {algor.upper()} certificate {self.file_name} '
                f'must be greater than or equal {details["min_length"]} bits.'
            )
        if length < details['recommended_length']:
            utils.cli.write_to_terminal(
                f"{self.file_name}: Current key length is {length} bits. "
                f"Use {details['recommended_length']} bits for better security.",
                color="yellow"
            )

        return True

    def verify_digest(self):
        """
        hash checker
        """
        ans = re.findall(r'Signature Algorithm:[ ]*([^\n ]*)[ ]*',
                         self.text,
                         flags=re.IGNORECASE)
        if not ans:
            return False
        hash_rule = {
            'sha0': r'(?!\d)',
            'md2': r'(?!\d)',
            'md4': r'(?!\d)',
            'md5': r'(?!\d)',
            'sha1': r'(?!\d)',
            'ripemd': r''
        }
        for key, value in hash_rule.items():
            illegal_ = re.findall(rf'{key}{value}',
                                  ans[-1],
                                  flags=re.IGNORECASE)
            if illegal_:
                raise ValueError(f'Failed to verify digest of {self.file_name}')
        return True


class CertCheckerHandler():

    @staticmethod
    def openssl_out(cert_path):
        """
        openssl output
        """
        process = subprocess.Popen(
            ['openssl', 'x509', '-noout', '-text', '-in', cert_path],
            shell=False,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            raise CertCheckException("Time out")
        except Exception:
            raise CertCheckException("Failed to execute openssl command")

        status = process.returncode
        output = output.decode('utf-8').strip()
        if status != 0:
            raise CertCheckException(output.strip())
        return output

    @staticmethod
    def is_valid_time_cert(ca_name):
        """
        cert time verifier
        """
        cert_path = os.path.realpath(ca_name)
        process = subprocess.Popen(
            ['openssl', 'x509', '-in', cert_path, '-checkend', '1'],
            shell=False,
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE
        )

        try:
            output, _ = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            raise CertCheckException("Time out")
        except Exception:
            raise CertCheckException("Failed to execute openssl command")

        status = process.returncode
        output = output.decode('utf-8').strip()
        if status == 0 and output.lower().find('not expire') > -1:
            return True
        else:
            raise ValueError(f'Failed to check cert time: {cert_path}.')

    @staticmethod
    def verify_cert_format(cert_name, is_ca=False):
        """
        cert format verifier
        """
        result = CertCheckerHandler.openssl_out(os.path.realpath(cert_name))
        cv = CertVerifier(cert_name, result, is_ca=is_ca)
        if (cv.verify_algorithm()
                and cv.verify_digest()
                and CertCheckerHandler.is_valid_time_cert(cert_name)):
            return True
        return False

    @staticmethod
    def is_valid_cert(ca_name=None, crt_name=None):
        """
        cert checker sub function
        """
        if ca_name and not CertCheckerHandler.verify_cert_format(ca_name, is_ca=True):
            return False
        if crt_name and not CertCheckerHandler.verify_cert_format(crt_name, is_ca=False):
            return False
        return True
