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

from sqlalchemy import text

from GaussMaster.common.metadatabase.result_db_session import get_session
from GaussMaster.common.metadatabase.schema.clusters import ManagedCluster
from GaussMaster.common.security import Encryption
from GaussMaster.common.utils.checking import split_ip_port


class ClusterNameConflict(Exception):
    pass


def update_managed_CN_DN(cluster_name, host, port, username, password, force=True):
    """to insert new cluster into managed_cluster table"""
    exists_record = query_cluster_record(cluster_name=cluster_name)
    if exists_record and not force:
        is_same_cluster = False
        for record in exists_record:
            if record.host == host and int(record.port) == int(port):
                is_same_cluster = True
                break
        if not is_same_cluster:
            raise ClusterNameConflict('集群名冲突')
    with get_session() as session:
        # The syntax of gaussdb conflict is different from that of pg,
        # and the on_conflict_do_update function cannot be used.
        stmt = text("""
                    INSERT INTO tb_managed_cluster (cluster_name, host, port, username, password)
                    VALUES (:cluster_name, :host, :port, :username, :password) 
                    ON DUPLICATE KEY UPDATE cluster_name = :cluster_name, username = :username, password = :password
                    """)
        session.execute(stmt, {'cluster_name': cluster_name, 'host': host, 'port': port, 'username': username,
                               'password': password})


def select_managed_cluster(host, port):
    """to select managed_cluster records"""
    with get_session() as session:
        query_result = session.query(ManagedCluster). \
            filter(ManagedCluster.host == host, ManagedCluster.port == int(port)).first()
        if query_result:
            return {'cluster_name': query_result.cluster_name, 'host': query_result.host, 'port': query_result.port,
                    'username': query_result.username, 'password': query_result.password}


def query_cluster_record(cluster_name=None, host=None, port=None, username=None):
    """filter all cluster records by given columns"""
    with get_session() as session:
        result = session.query(ManagedCluster.cluster_name, ManagedCluster.host, ManagedCluster.port,
                               ManagedCluster.username, ManagedCluster.password)
        if cluster_name:
            result = result.filter(ManagedCluster.cluster_name == cluster_name)
        if host:
            result = result.filter(ManagedCluster.host == host)
        if port:
            result = result.filter(ManagedCluster.port == port)
        if username:
            result = result.filter(ManagedCluster.username == username)
        return result


def update_managed_cluster(cluster_name, clusters_dict, instance, password, username):
    cluster_records = query_cluster_record(cluster_name)
    force = True
    for _ in cluster_records:
        force = False
    for _instance in clusters_dict.get(instance):
        _ip, _port = split_ip_port(_instance)
        update_managed_CN_DN(cluster_name, _ip, int(_port), username,
                             Encryption.encrypt(password), force=force)
