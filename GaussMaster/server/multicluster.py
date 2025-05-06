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

"""cluster manager"""

import threading

from GaussMaster.multiagents.tools.dbmind_interface import get_cluster_list, update_cluster_list


class ClusterAddressError(ValueError):
    """cluster error"""
    pass


class ClusterProxy:
    """cluster proxy"""

    def __init__(self):
        self._clusters = {}
        self._finalized = False
        self._thread_context = threading.local()
        self._lock = threading.Lock()

    def autodiscover(self):
        """auto discover clusters"""
        update_cluster_list()
        self._clusters = get_cluster_list()

    def switch_context(self, instance, username=None, pwd=None, database=None):
        """switch context"""
        if not instance:
            self._thread_context.instance = None
            self._thread_context.cluster = None
            self._thread_context.username = None
            self._thread_context.pwd = None
            return True
        if instance not in self._clusters:
            return False
        self._thread_context.pwd = pwd
        self._thread_context.username = username
        self._thread_context.database = database
        self._thread_context.instance = instance
        self._thread_context.cluster = self._clusters.get(instance)
        return True

    def current_cluster_instances(self):
        """get current cluster instances"""
        if hasattr(self._thread_context, 'cluster'):
            return self._thread_context.cluster
        if len(self._clusters) == 0:
            return []
        # set first instance as default and return it directly.
        instance = next(iter(self._clusters.keys()))
        return self._clusters.get(instance)

    def current_instance(self):
        """get current instance"""
        if hasattr(self._thread_context, 'instance'):
            return self._thread_context.instance
        if len(self._clusters) == 0:
            return None
        # set first instance as default and return it directly.
        instance = next(iter(self._clusters.keys()))
        return instance

    def cluster_get_all(self):
        """get all clusters"""
        return self._clusters

    def get_current_instance_details(self):
        """get current instance details"""
        return {'user': self._thread_context.username if hasattr(self._thread_context, 'username') else None,
                'password': self._thread_context.pwd if hasattr(self._thread_context, 'pwd') else None,
                'host': self.current_instance().split(':')[0] if self.current_instance() else None,
                'port': self.current_instance().split(':')[-1] if self.current_instance() else None,
                'database': self._thread_context.database if hasattr(self._thread_context, 'database') else None}

    def context(self, instance, username=None, pwd=None, database=None):
        """context manager"""
        outer = self
        old = outer.current_instance()
        old_instance_details = outer.get_current_instance_details()

        class Inner:
            def __init__(self, addr):
                self.addr = addr

            def __enter__(self):
                if not outer.switch_context(self.addr, username, pwd, database):
                    raise ClusterAddressError('Cannot switch to this RPC address %s' % instance)

            def __exit__(self, exc_type, exc_val, exc_tb):
                outer.switch_context(instance=old,
                                     username=old_instance_details.get('user'),
                                     pwd=old_instance_details.get('password'),
                                     database=old_instance_details.get('database'))

        return Inner(instance)

    def has(self, instance_address):
        """return instance_address in self._clusters"""
        return instance_address in self._clusters

    def get(self, instance_address):
        """get current instance"""
        return self._clusters.get(instance_address, None)
