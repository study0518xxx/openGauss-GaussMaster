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

from abc import abstractmethod
from typing import List


class BaseReranker:
    @abstractmethod
    def compute_score(self, pairs: List[List[str]]) -> List[float]:
        """
        Compute relevance score for List[List[str]] type data using customized model.
        Args:
            pairs: The list of pair(query, answer) to reranker.
        Returns:
            The results field in the list contains of relevance score, one for each pair.
        """
