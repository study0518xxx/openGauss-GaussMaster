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


class BaseEmbedding:
    @abstractmethod
    def doc_embedding(self, texts: List[str]) -> List[List[float]]:
        """
        Compute document embeddings for List[str] type data using customized model.
        Args:
            texts: The list of texts to embedding.
        Returns:
            The results field in the list contains List of embeddings, one for each text.
        """

    @abstractmethod
    def query_embedding(self, text: str) -> List[float]:
        """
        Compute query embeddings for str type data using customized model.
        Args:
            text: The str to embedding.
        Returns:
            The results field is a List of embedding.
        """

    def get_embedding_dimensions(self) -> int:
        """
        Obtains the embedding dimension of the current model.
        """
