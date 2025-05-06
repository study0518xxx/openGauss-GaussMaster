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

import os

from GaussMaster.constants import STOP_WORDS, SENSITIVE_WORD_PATH


class SafeDetectorDFA(object):
    """
    Deterministic Finite Automata for Sensitive Word Detector
    """

    def __init__(self, word_list):
        """
        Initialize a word detector based on a list of words.
        :param word_list:
        """
        self.root = dict()
        self.stop_word = STOP_WORDS
        # add sensitive words
        for word in word_list:
            self.add_word(word)

    def add_word(self, word):
        """
        Add the word to the detector.
        基于输入的敏感词构建前缀树，树中的每一条路径对应一个完整的敏感词
        :param word:
        :return:
        """
        current_node = self.root
        for no, word_char in enumerate(word):
            if word_char in current_node:
                current_node = current_node.get(word_char)
                current_node["is_end"] = False

                if no == len(word) - 1:
                    current_node["is_end"] = True

            else:
                expand_node = dict()
                if no == len(word) - 1:
                    expand_node["is_end"] = True

                else:
                    expand_node["is_end"] = False

                current_node[word_char] = expand_node
                current_node = expand_node

    def match_word(self, text):
        """
        Match the sensitive word.
        基于已构建的前缀树，遍历路径以检索敏感词
        :param text:
        :return:
        """
        is_matched = False
        match_length = 0
        total_length = 0
        current_node = self.root

        for word_char in text:
            if word_char in self.stop_word:
                total_length += 1
                continue

            current_node = current_node.get(word_char)
            if current_node:
                total_length += 1
                match_length += 1
                if current_node.get("is_end"):
                    is_matched = True
                    break
            else:
                break

        if total_length < 1 or not is_matched:
            total_length = 0

        return total_length, match_length, is_matched

    def is_unsafe_text(self, text):
        """
        Check if the text is unsafe or not.
        :param text:
        :return:
        """
        is_unsafe = False
        for i in range(len(text)):
            total_length, _, _ = self.match_word(text[i:])
            if total_length != 0:
                is_unsafe = True
                break

        return is_unsafe

    def get_unsafe_word(self, text):
        """
        Get the sensitive words in the text.
        :param text:
        :return:
        """
        unsafe_word_list = list()
        i = 0
        while i < len(text):
            total_length, _, _ = self.match_word(text[i:])
            if total_length > 1:
                word = text[i:i + total_length]
                unsafe_word_list.append(word)
                i = i + total_length - 1

            if total_length == 1:
                word = text[i]
                unsafe_word_list.append(word)
                i = i + 1

            else:
                i = i + 1

        return unsafe_word_list


def get_detector():
    """
    Build the word detector.
    :return:
    """
    keywords = set()
    for file in os.listdir(SENSITIVE_WORD_PATH):
        with open(os.path.join(SENSITIVE_WORD_PATH, file), "r", encoding="utf-8-sig") as rf:
            lines = rf.readlines()
        keywords = keywords.union([line.strip("\n") for line in lines if line.strip("\n") != ""])

    keywords = sorted(keywords, reverse=True)
    detector = SafeDetectorDFA(word_list=keywords)

    return detector
