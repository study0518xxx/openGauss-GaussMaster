from typing import Optional
import math
from typing import List

# Definition for singly-linked list.
class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next

class Solution:
    def mergeTwoLists(self, list1: Optional[ListNode], list2: Optional[ListNode]) -> Optional[ListNode]:
        
        dummy = ListNode()
        cur = dummy
        while list1 and list2:
            if(list1.val < list2.val):
                cur.next=list1
                list1=list1.next
            else:
                cur.next=list2
                list2=list2.next
            cur=cur.next
        cur.next=list1 or list2
        return dummy.next
        

def build_list(arr):
    dummy = ListNode()
    p = dummy
    for num in arr:
        p.next = ListNode(num)
        p = p.next
    return dummy.next

# 打印链表辅助函数
def print_list(head):
    vals = []
    while head:
        vals.append(str(head.val))
        head = head.next
    print("->".join(vals))

sol = Solution()
c1=build_list([1,2,2,8])
c2=build_list([0,2,3,4])
# a="   fly me   to   the AAmoon  "
# c1="2"
# c2="3"
# c1=2
# c2=3
b = sol.mergeTwoLists(c1,c2)
print_list(b)
# print(sol.repeatedSubstringPattern("123123"))
# print(sol.isAnagram("a", "a"))