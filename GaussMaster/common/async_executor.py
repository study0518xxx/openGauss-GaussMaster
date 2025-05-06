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

import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Callable, TypeVar

from typing_extensions import ParamSpec

P = ParamSpec("P")
T = TypeVar("T")


async def run_in_executor(executor, func: Callable[P, T], *args: P.args, **kwargs: P.kwargs) -> T:
    """async executor"""
    return await asyncio.get_running_loop().run_in_executor(executor, partial(func, **kwargs), *args)


async def run_in_thread_pool(func: Callable[P, T], *args: P.args):
    loop = asyncio.get_event_loop()
    executor = ThreadPoolExecutor(max_workers=4)
    result = await loop.run_in_executor(
        executor,
        func,
        *args
    )
    return result


async def async_write_file(path, data):
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, lambda: open(path, "wb").write(data))
