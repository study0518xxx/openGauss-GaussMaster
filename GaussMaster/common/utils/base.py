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

import datetime
import functools
import inspect
import logging
import multiprocessing
import os
import re
import sys
import threading
import time
import traceback
import types
from collections import OrderedDict
from logging.handlers import RotatingFileHandler
from queue import Empty

from GaussMaster.common.exceptions import CustomToolException
from GaussMaster.utils.ui_output_util import formatter_str

RED_FMT = "\033[31;1m{}\033[0m"
GREEN_FMT = "\033[32;1m{}\033[0m"
YELLOW_FMT = "\033[33;1m{}\033[0m"
WHITE_FMT = "\033[37;1m{}\033[0m"
SENSITIVE_WORD = ('PASSWORD', 'PWD', 'AUTH', 'USERNAME', 'USER', 'CERTIFICATE', 'SSL')


class CachedProperty:
    """A decorator for caching a property."""

    def __init__(self, func):
        self.func = func

    def __get__(self, instance, owner):
        if instance is None:
            return self

        value = self.func(instance)
        setattr(instance, self.func.__name__, value)
        return value


def ttl_cache(seconds, maxsize=32):
    """Time aware caching to LRU cache."""

    def decorator(func):
        @functools.lru_cache(maxsize)
        def _new(*args, __time_salt, **kwargs):
            return func(*args, **kwargs)

        @functools.wraps(func)
        def _wrapped(*args, **kwargs):
            return _new(*args, __time_salt=round(time.monotonic() / seconds), **kwargs)

        return _wrapped

    return decorator


class TTLOrderedDict(OrderedDict):
    def __init__(self, ttl_seconds=600, *args, **kwargs):
        self.ttl = ttl_seconds
        self._lock = threading.RLock()
        super().__init__()
        self.update(*args, **kwargs)

    def __setitem__(self, key, value):
        with self._lock:
            expired_time = time.monotonic() + self.ttl
            super().__setitem__(key, (expired_time, value))

    def __getitem__(self, key):
        with self._lock:
            expired_time, value = super().__getitem__(key)
            if expired_time < time.monotonic():
                super().__delitem__(key)
                raise KeyError(key)
            return value

    def __delitem__(self, key):
        with self._lock:
            super().__delitem__(key)

    def __len__(self):
        with self._lock:
            self._purge()
            return super().__len__()

    def __iter__(self):
        with self._lock:
            self._purge()
            return self.__iter__()

    def __contains__(self, key):
        with self._lock:
            self._purge()
            return super().__contains__(key)

    def __repr__(self):
        with self._lock:
            self._purge()
            return super().__repr__()

    def refresh_ttl(self, key):
        """Refresh the lifetime of a key value pair"""
        with self._lock:
            self.__setitem__(key, self.__getitem__(key))

    def keys(self):
        with self._lock:
            self._purge()
            return super().keys()

    def values(self):
        with self._lock:
            self._purge()
            return super().values()

    def get(self, k, default=None):
        with self._lock:
            try:
                return self.__getitem__(k)
            except KeyError:
                return default

    def _purge(self):
        to_delete = []
        for key, item in super().items():
            expired_time, value = item
            logging.info(value)
            if expired_time < time.monotonic():
                to_delete.append(key)
        for key in to_delete:
            super().__delitem__(key)


class FixedDict(OrderedDict):
    def __init__(self, max_len=16):
        super().__init__()
        self.max_len = max_len

    def __setitem__(self, key, value):
        super().__setitem__(key, value)
        if len(self) > self.max_len:
            # FIFO
            self.popitem(last=False)


class NaiveQueue:
    def __init__(self, maxsize=10):
        """Unlike the Queue that Python builds in,
        if the length exceeds the max size, the first inserted element
        will be popped and will not be blocked. """
        self.q = list()
        dbmind_assert(maxsize > 0)
        self.maxsize = maxsize
        self.mutex = threading.Lock()

    def __iter__(self):
        with self.mutex:
            return self.q.__iter__()

    def __len__(self):
        with self.mutex:
            return len(self.q)

    def get(self, default=None):
        """Extract elements"""
        with self.mutex:
            if len(self.q) > 0:
                return self.q.pop(0)
            return default

    def put(self, e):
        """Add elements"""
        with self.mutex:
            self.q.append(e)
            while len(self.q) > self.maxsize:
                self.q.pop(0)


def where_am_i(fvars):
    """Return the module which current function runs on.

    :param fvars: the return value of function ``globals()``.
    """
    file, name = fvars.get('__file__'), fvars.get('__name__')
    if None in (file, name):
        return None
    return name


class MultiProcessingRFHandler(RotatingFileHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._queue = multiprocessing.Queue(-1)
        self._sensitive_words = []
        self._should_exit = False
        self._receiv_thr = threading.Thread(target=self._receive, name='LoggingReceiverThread')
        self._receiv_thr.daemon = True
        self._receiv_thr.start()

    def add_sensitive_word(self, word):
        """Prevent sensitive information from leaking in plaintext through logs, such as passwords."""
        if isinstance(word, (list, tuple)):
            self._sensitive_words.extend(word)
        elif isinstance(word, str):
            self._sensitive_words.append(word)

    def emit(self, record):
        try:
            if record.args:
                record.msg = record.msg % record.args
                record.args = None
            if record.exc_info:
                self.format(record)
                record.exc_info = None
            if not os.path.exists(self.baseFilename):
                os.makedirs(os.path.dirname(self.baseFilename), mode=0o700, exist_ok=True)
                self.stream = open(self.baseFilename, 'a', encoding=self.encoding)
                os.chmod(self.baseFilename, 0o600)
            self._send(record)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            pass

    def format(self, record):
        s = super().format(record)
        for word in self._sensitive_words + list(SENSITIVE_WORD):
            if word.upper() in s.upper():
                s = "Involves sensitive information, details are ignored."
                break
        return s

    def close(self):
        if not self._should_exit:
            self._should_exit = True
            self._receiv_thr.join(5)
            super().close()

    def _send(self, s):
        self._queue.put_nowait(s)

    def _receive(self):
        while True:
            try:
                if self._should_exit and self._queue.empty():
                    break
                record = self._queue.get(timeout=.2)
                super().emit(record)
            except (KeyboardInterrupt, SystemExit):
                raise
            except (OSError, EOFError):
                break
            except Empty:
                pass
            except Exception as e:
                dbmind_assert(e)  # ignore
                traceback.print_exc(file=sys.stderr)
        self._queue.close()
        self._queue.join_thread()


def validate_return_format(func):
    """
    本文件中所有函数应遵循以下输出格式规范：
    1.输出为列表
    2.列表由1个或多个ui_output_util文件中定义的结构体组成
    3.最后一项可选填充下一步骤的字符串
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            error_info = traceback.format_exc()
            logging.error(error_info)
            raise CustomToolException(f'工具执行异常{func}:{str(e)}') from e
        if not isinstance(result, list):
            raise ValueError(f'Expected return type list, but got {type(result)}')

        for i, value in enumerate(result):
            if not isinstance(value, dict) and i != len(result) - 1:
                raise ValueError(f'Expected return type list consist of one or more '
                                 f'structures defined in the ui_output_util file')

        return result

    return wrapper


def validate_return_format2(func):
    """
    本文件中所有函数应遵循以下输出格式规范：
    1.输出为列表
    2.列表由1个或多个ui_output_util文件中定义的结构体组成
    3.最后一项可选填充下一步骤的字符串
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            error_info = traceback.format_exc()
            logging.error(error_info)
            raise CustomToolException(f'工具执行异常{func}:{str(e)}')

        if isinstance(result, tuple):
            if len(result) != 2:
                raise ValueError(f"Expected return tuple's length is 2, "
                                 f"but got {len(result)} unexpectedly.")

            flag, res = result
            if not isinstance(flag, bool):
                raise ValueError(f"Expected flag's type to be bool, "
                                 f"but got {type(flag)} unexpectedly.")

            if not isinstance(res, list):
                raise ValueError(f"Expected result's type to be list, "
                                 f"but got {type(res)} unexpectedly.")

        else:
            raise ValueError(f"Expected return's type to be tuple, "
                             f"but got {type(result)} unexpectedly.")

        for i, value in enumerate(res):
            if not isinstance(value, dict) and i != len(res) - 1:
                raise ValueError(f'Expected return type list consist of one or more '
                                 f'structures defined in the ui_output_util file')

        return result

    return wrapper


def exception_catcher(func):
    """
    Capture exceptions in decorated functions
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
        except CustomToolException:
            error_info = traceback.format_exc()
            logging.error(error_info)
            return [formatter_str('工具执行异常')]
        except Exception as e:
            error_info = traceback.format_exc()
            logging.error(error_info)
            return [formatter_str(str(e))]
        return result

    return wrapper


def stream_exception_catcher(func):
    """Streaming exception catching"""

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            async for output in func(*args, **kwargs):
                yield output
        except CustomToolException:
            error_info = traceback.format_exc()
            logging.error(error_info)
            yield [formatter_str('工具执行异常')]
        except Exception as e:
            error_info = traceback.format_exc()
            logging.error(error_info)
            yield [formatter_str(str(e))]

    return wrapper


class ExceptionCatcher:
    """Class for catching object exception"""

    class DontIgnoreThisError(Exception):
        pass

    def __init__(self, strategy='warn', name='UNKNOWN'):
        """
        :param strategy: Exception handling strategy
        :param name: The object from which the exception came
        """
        self.strategy = strategy
        self.name = name

    def __get__(self, instance, cls):
        if instance is None:
            return self
        return types.MethodType(self, instance)

    def __call__(self, func):
        functools.wraps(func)(self)

        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if self.strategy == 'warn':
                    logging.warning("[%s] %s occurred exception: %s",
                                    self.name, func.__name__, str(e), exc_info=True)
                elif self.strategy == 'raise':
                    raise e
                elif self.strategy == 'ignore':
                    pass
                elif self.strategy == 'sensitive':
                    error = str(e).upper()
                    for word in SENSITIVE_WORD:
                        if word in error and not isinstance(e, self.DontIgnoreThisError):
                            raise AssertionError(
                                "Involves sensitive information, details are ignored, "
                                "please check the call stack."
                            ).with_traceback(sys.exc_info()[2]) from None
                    raise e
                elif self.strategy == 'exit':
                    from .cli import raise_fatal_and_exit
                    raise_fatal_and_exit('An exception raised: %s' % e)
                else:
                    raise ValueError('Not supported strategy %s' % self.strategy)

        return wrapper


ignore_exc = ExceptionCatcher(strategy='ignore', name='common utils')


def retry(times_limit=2):
    """A decorator which helps to retry while an exception occurs."""

    def decorator(func):
        def wrap(*args, **kwargs):
            try_times = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    try_times += 1
                    if try_times < times_limit:
                        logging.warning('Caught an exception while %s running, and try to run again.',
                                        func.__name__)
                        continue
                    raise e

        return wrap

    return decorator


def is_integer_string(s):
    """
    Determine whether the parameter is an integer
    """
    if s.isdigit():
        return True
    try:
        int(s)
        return True
    except ValueError:
        pass
    return False


def cast_to_int_or_float(value, precision=-1):
    """
    cast value to int or float
    """
    # notes: precision only works when converting to float
    if isinstance(value, (int, float)):
        return value
    try:
        if isinstance(value, str) and is_integer_string(value):
            return int(value)
        if precision <= 0:
            return float(value)
        return round(float(value), precision)
    except (ValueError, TypeError):
        logging.warning('The value: %s cannot be converted to int or float.', value, exc_info=True)
        return float('nan')


def dbmind_assert(condition, comment=None):
    """
    Perform assertion check on the incoming parameters
    """
    if not condition:
        if comment is None:
            raise AssertionError("Please check the value of this variable. "
                                 "The value of condition is %s." % condition)
        raise ValueError(comment)


def chmod_r(path, directory_mode=0o700, file_mode=0o600):
    """
    Change the permissions of all files and directories in the specified path
    """
    if not os.path.exists(path):
        return
    for root, dirs, files in os.walk(path):
        for d in dirs:
            os.chmod(os.path.join(root, d), directory_mode)
        for f in files:
            os.chmod(os.path.join(root, f), file_mode)
    os.chmod(path, directory_mode)


def split(s, delimiter=','):
    """
    Split string
    """
    if not s:
        return []
    rv = []
    for t in s.split(delimiter):
        stripped = t.strip()
        if stripped:
            rv.append(stripped)
    return rv


def string_to_dict(key_value_str, delimiter=','):
    """
    transfer string to dict
    """
    d = dict()
    if not delimiter:
        return d

    if not isinstance(key_value_str, str):
        return d

    for pair in key_value_str.split(delimiter):
        if "=" not in pair:
            continue

        name, value = pair.split('=', 1)
        name, value = name.strip(), value.strip()
        try:
            dbmind_assert(name and value)
        except (AssertionError, ValueError):
            logging.error("error occured when transfer %s to dict", key_value_str)
            continue

        d[name] = value

    return d


def try_to_get_an_element(element, idx):
    """
    Retrieve the elements of the specified index from the given list
    """
    if len(element) == 0:
        return None
    if len(element) <= idx:
        return element[0]  # default to return the first one
    return element[idx]


class SecurityChecker(object):
    """check security conditions"""
    INJECTION_CHAR_LIST = ["|", ";", "&", "$", "<", ">", "`", "\\", "'", "\"", "{", "}", "(", ")",
                           "[", "]", "~", "*", "?", " ", "!", "\n"]

    @staticmethod
    def check_injection_char(check_value):
        """
        function: check suspicious injection value
        input : check_value
        output: NA
        """
        if not check_value.strip():
            return
        if any(rac in check_value for rac in SecurityChecker.INJECTION_CHAR_LIST):
            raise Exception(" There are illegal characters.")


def get_env(env_param, default_value=None):
    """
    function: get the filter environment variable
    input:envparam: String
          default_value: String
    output:envValue
    """
    env_value = os.getenv(env_param)

    if env_value is None:
        if default_value:
            return default_value
        return env_value

    env_value = env_value.replace("\\", "\\\\").replace('"', '\\"\\"')
    SecurityChecker.check_injection_char(env_value)
    return env_value


def adjust_timezone(tz):
    """Convert time zone string to timezone type notes: only supports UTC, example: UTC-8, UTC+8, UTC-8:35"""
    if tz is None:
        return None
    try:
        unit, hour, minute = re.match(r"UTC([-+])(\d{1,2})(:\d{1,2})?$", tz).groups()
        hour = int(hour)
        minute = int(minute[1:]) if minute is not None else 0
        unit = -1 if unit == '-' else 1
        tz = datetime.timezone(datetime.timedelta(hours=unit * hour, minutes=unit * minute))
        return tz
    except Exception:
        logging.warning("There is a problem with the time zone '%s', please refer to: UTC+8,UTC+8:35", tz)
        return None


def parse_accept_language(accept_language):
    """
    将浏览器的Accept-language转换成统一的语言标识

    :param accept_language: str，浏览器的Accept-language
    :return: str，统一的语言标识
    """
    languages = accept_language.split(",")
    languages = [language.split(";")[0].strip() for language in languages]

    # 可以根据需要添加更多的语言映射关系
    language_map = {
        "zh-CN": "zh",
        "zh-TW": "zh",
        "en-US": "en",
        "en-GB": "en",
    }

    for language in languages:
        if language in language_map:
            return language_map[language]

    return accept_language


def timer_decorator(func):
    """Calculate how long it takes to complete the function"""

    @functools.wraps(func)
    async def async_wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()
        result = await func(*args, **kwargs)
        end_time = time.perf_counter()
        run_time = end_time - start_time
        logging.info(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return result

    @functools.wraps(func)
    def wrapper_timer(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        run_time = end_time - start_time
        logging.info(f"Finished {func.__name__!r} in {run_time:.4f} secs")
        return result

    if inspect.iscoroutinefunction(func):
        return async_wrapper_timer
    return wrapper_timer


def validate_filename(filename):
    # 提取纯文件名
    basename = os.path.basename(filename)
    # 过滤非法字符
    safe_name = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", basename)
    safe_name = safe_name.strip()
    # 检查非空
    if not safe_name:
        raise ValueError(f'filename cannot be empty.')
    # 检查长度
    if len(safe_name) > 255:
        raise ValueError(f'The filename contains more than 255 characters.')
    return safe_name
