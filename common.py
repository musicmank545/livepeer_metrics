# -*- coding: utf-8 -*-
"""
Created on Fri Jun 11 19:19:22 2021

TO DO:
1. this does not yet consider instance profiles defined in roles
2. attached or inline policies also grant users the ability to assume roles... need to capture this in the roles results tab

saved a working version on 11.6.2021 before changing the way this handles '*' characters

@author: jkuhnsman
"""
import logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

file = logging.FileHandler('app.log')
file.setLevel(logging.DEBUG)
fileformat = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s",datefmt="%H:%M:%S")
file.setFormatter(fileformat)

stream = logging.StreamHandler()
stream.setLevel(logging.DEBUG)
streamformat = logging.Formatter("%(asctime)s:%(levelname)s:%(message)s")
stream.setFormatter(streamformat)

log.addHandler(file)
log.addHandler(stream)
log.info('Application has started')

import json
import pandas as pd
import re
import sqlite3
from sqlite3 import Error
import requests
import functools
import hashlib

print = functools.partial(print, flush=True)
#from datetime import datetime
#from pypika import Query, Table, Field

class Database:
    def __init__(self,_db_identifier):
        self.conn = None
        
        self.db_identifier = _db_identifier
            
        self.conn = self.create_connection(self.db_identifier)
        
    def create_connection(self,name):
        conn = None
        try:
            conn = sqlite3.connect(name, check_same_thread=False)
            
        except Error as e:
            print(e)
        return conn
    
    def execute_sql(self,_sql_statement):
        if self.conn is not None:
            try:
                c = self.conn.cursor()
                c.execute(_sql_statement)
                self.conn.commit()
                return c.fetchall()
            except Error as e:
                print(e)
                print(_sql_statement)
            
    def sql_to_json(self,_sql_statement):
        if self.conn is not None:
            try:
                c = self.create_connection(self.db_identifier)
                c.row_factory = sqlite3.Row
                rows = c.execute(_sql_statement).fetchall()
                c.commit()
                c.close()
                data=[dict(ix) for ix in rows]
                return data
            except Error as e:
                print(e)
                print(_sql_statement)

    def execmany_sql(self,_sql_statement,_data):
        if self.conn is not None:
            try:
                c = self.conn.cursor()
                c.executemany(_sql_statement,_data)
                self.conn.commit()
                return c.fetchall()
            except Error as e:
                print(e)
                print(_sql_statement)                
    
            
    def make_list(self,_l):
        if not isinstance(_l, list):
            return [_l]
        return _l

    def sql_to_df(self, _sql_statement):
        if self.conn is not None:
            try:
                return pd.read_sql(_sql_statement, con=self.conn)
            except Error as e:
                print(e)
                
    def get_tables(self):
        tables = self.execute_sql("SELECT name FROM sqlite_master WHERE type='table';")
        tlist = [x[0] for x in tables]
        return tlist

class LpMetricsDb(Database):
    
    def __init__(self,_db_identifier=None,_configs=None):
        Database.__init__(self, _db_identifier)
        self.static_statements = self.get_static_statements()
        self.configs = _configs
        
        self.initialize_db()
        log.debug('LPMetricsDB instance init function complete')
        
        
    def initialize_db(self):
        tables = self.get_tables()
        if not 'active_orchs' in tables:
            log.info('active_orchs table does not exist... creating table')
            self.init_active_orchs()
        elif self.execute_sql('SELECT * FROM active_orchs') == []:
            log.info('active_orchs table is empty... populating table')
            self.init_active_orchs()
        
        self.init_metrics_tables()


    def init_active_orchs(self):
        self.execute_sql("DROP TABLE IF EXISTS active_orchs")
        self.execute_sql(self.static_statements['create_active_orchs_table'])
        orchs = self.get_active_orchs_from_cli()
        
        for o in orchs:
            sql_insert = """INSERT INTO active_orchs VALUES (null,'{address}','{delegated_stake}','{fee_share}','{reward_cut}')""".format(
                address=o['Address'],
                delegated_stake=o['DelegatedStake'],
                fee_share=o['FeeShare'],
                reward_cut=o['RewardCut'])
            #insert records
            self.execute_sql(sql_insert)
        log.info('active_orchs table created')
    
    def init_metrics_tables(self):
        self.execute_sql('DROP TABLE IF EXISTS metrics')
        self.execute_sql(self.static_statements['create_metrics_table'])
        log.debug('metrics table reset')
        self.execute_sql('DROP TABLE IF EXISTS metrics_staging')
        self.execute_sql(self.static_statements['create_metrics_staging_table'])
        log.debug('metrics_staging table reset')
        self.execute_sql('DROP TABLE IF EXISTS local_metrics')
        self.execute_sql(self.static_statements['create_local_metrics_table'])
        log.debug('local_metrics table reset')
        self.execute_sql('DROP TABLE IF EXISTS local_metrics_staging')
        self.execute_sql(self.static_statements['create_local_metrics_staging_table'])
        log.debug('local_metrics_staging table reset')
        
    def get_active_orchs_from_cli(self):
        log.debug('retrieving active orchs from cli')
        r = requests.get('http://localhost:7935/registeredOrchestrators')
        return r.json()
    
    @property
    def orch_addresses(self):
        orchs = self.sql_to_df('SELECT * FROM active_orchs')
        orch_list = orchs['address'].tolist()
        return orch_list
        
    def get_static_statements(self):
        statements = {}
        
        #active orchs table
        __sql_create_active_orch_table = """CREATE TABLE active_orchs (
                                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                                        address text NOT NULL,
                                        delegated_stake integer NOT NULL,
                                        fee_share integer NOT NULL,
                                        reward_cut integer NOT NULL
                                    );"""
        statements['create_active_orchs_table'] = __sql_create_active_orch_table

        #metrics table
        __sql_create_metrics_table = """CREATE TABLE IF NOT EXISTS metrics (
                                        id text NOT NULL PRIMARY KEY,
                                        metric text NOT NULL,
                                        tags text NOT NULL,
                                        value text NOT NULL
                                    );"""
        statements['create_metrics_table'] = __sql_create_metrics_table
        
        #metrics staging table
        __sql_create_metrics_staging_table = """CREATE TABLE IF NOT EXISTS metrics_staging (
                                        id text NOT NULL PRIMARY KEY,
                                        metric text NOT NULL,
                                        tags text NOT NULL,
                                        value text NOT NULL
                                    );"""
        statements['create_metrics_staging_table'] = __sql_create_metrics_staging_table
        
        #local_metrics table
        __sql_create_local_metrics_table = """CREATE TABLE IF NOT EXISTS local_metrics (
                                        id text NOT NULL PRIMARY KEY,
                                        metric text NOT NULL,
                                        tags text NOT NULL,
                                        value text NOT NULL
                                    );"""
        statements['create_local_metrics_table'] = __sql_create_local_metrics_table
        
        #local metrics staging table
        __sql_create_local_metrics_staging_table = """CREATE TABLE IF NOT EXISTS local_metrics_staging (
                                        id text NOT NULL PRIMARY KEY,
                                        metric text NOT NULL,
                                        tags text NOT NULL,
                                        value text NOT NULL
                                    );"""
        statements['create_local_metrics_staging_table'] = __sql_create_local_metrics_staging_table
        
        return statements

    def getMetrics(self, ip, port, eth, message=None, signature=None):
        metrics_parsed = []
        try:
            log.debug('getMetrics function has been called')
            url = 'http://'+ip+':'+port+'/metrics'
            log.debug('getMetrics: url = %s',url)
            if message == None or signature == None:
                log.debug('getMetrics: requesting metrics without authentication')
                r = requests.get(url, verify=False)
                log.debug('getMetrics: response status code %s',r.status_code)
                
            else:
                log.debug('getMetrics: requesting metrics with authentication')
                r = requests.post(url, json={'message':message,'signature':signature}, verify=False)
                log.debug('getMetrics: response status code %s',r.status_code)
                #print(r.content)
                
            raw = r.text
            raw_split = raw.split('\n')
    
            metrics = []
            
            for m in raw_split:
                if (not '#' in m) & ('livepeer' in m):
                    metrics.append(m)
            
            
            
            for m in metrics:
                l = re.split('{|}',m)
                metric = str(l[0])
                tags = str(l[1])
                value = str(l[-1]).strip()
                
                tags_dict = self.split_with_quotes(tags)
                #print(tags_dict)
                tags_dict['ip'] = ip
                tags_dict['eth'] = eth
                
                ID = hashlib.md5(str.encode(metric+tags)).hexdigest()
                
                metrics_parsed.append({'id':ID,'metric':metric,'tags':json.dumps(tags_dict),'value':value})
        except Exception as e:
            log.error('getMetrics function failed: %s', e)
            
        return metrics_parsed

    def split_with_quotes(self, infile):
    
        split = 0
        quote = False
        tag_list = []
        tag_dict = {}
        for i in range(0,len(infile)):
            if infile[i] == '"':
                quote = ~quote
                
            if ((infile[i] == ',') or (i == len(infile)-1)) and (quote == False):
                tag_list.append(infile[split:i])
                split = i + 1
                
        for i in tag_list:
            x = i.replace('"','')
            tag = x.split('=')
            tag_dict[tag[0]] = tag[1]
        
        return tag_dict
    
    def update_local_metrics_staging_in_db(self):
        log.debug('update local metrics staging table')
        self.execute_sql('DROP TABLE IF EXISTS local_metrics_staging')
        self.execute_sql(self.static_statements['create_local_metrics_staging_table'])
        
        try:
            metrics = self.getMetrics(self.configs['local_orchestrator']['ip'],self.configs['local_orchestrator']['port'],self.configs['local_orchestrator']['eth'])
            
    
            
            _sql = """INSERT INTO local_metrics_staging (id,metric,tags,value)
                        VALUES(?,?,?,?)"""
            
            _data = [tuple(dic.values()) for dic in metrics]
            self.execmany_sql(_sql,_data)
        except:
            log.error('failed local metrics staging update')
        
    def update_remote_metrics_staging_in_db(self):
        log.debug('update remote metrics staging table')
        self.execute_sql('DROP TABLE IF EXISTS metrics_staging')
        self.execute_sql(self.static_statements['create_metrics_staging_table'])
        
        metric_list = []
        for orch in self.configs['participating_orchestrators']:
            try:
                metrics = self.getMetrics(orch['ip'],orch['port'],orch['eth'],message=self.configs['message'],signature=self.configs['signature'])
                metric_list.append(metrics)
            except:
                log.error('failed retrieving metrics from %s',orch['ip'])
        
        
        try:
            metrics = sum(metric_list, [])
                
            _sql = """INSERT INTO metrics_staging (id,metric,tags,value)
                        VALUES(?,?,?,?)"""
            
            _data = [tuple(dic.values()) for dic in metrics]
            self.execmany_sql(_sql,_data)
        except:
            log.error('failed writing data to remote metrics staging')
        
    def update_local_metrics_in_db(self):
        log.debug('syncing local metrics staging to local metrics table')
        try:
            _sql1 = """INSERT INTO local_metrics
                        SELECT * FROM local_metrics_staging
                        WHERE id NOT IN (SELECT id from local_metrics);"""
            _sql2 = """UPDATE local_metrics
                        SET value = (SELECT value FROM local_metrics_staging WHERE id = local_metrics.id)
                        WHERE value <> (SELECT value FROM local_metrics_staging WHERE id = local_metrics.id);"""
            _sql3 = """DELETE FROM local_metrics WHERE id NOT IN (SELECT id from local_metrics_staging);"""
            
            self.execute_sql(_sql1)
            self.execute_sql(_sql2)
            self.execute_sql(_sql3)
        except Exception as e:
            log.error('failed syncing local metrics from staging: %s',e)
        
    def update_remote_metrics_in_db(self):
        log.debug('syncing all staging to metrics table')
        try:
            _sql1l = """INSERT INTO metrics
                        SELECT * FROM local_metrics_staging
                        WHERE id NOT IN (SELECT id from metrics);"""
            _sql1r = """INSERT INTO metrics
                        SELECT * FROM metrics_staging
                        WHERE id NOT IN (SELECT id from metrics);"""
            _sql2l = """UPDATE metrics
                        SET value = (SELECT value FROM local_metrics_staging WHERE id = metrics.id)
                        WHERE value <> (SELECT value FROM local_metrics_staging WHERE id = metrics.id);"""
            _sql2r = """UPDATE metrics
                        SET value = (SELECT value FROM metrics_staging WHERE id = metrics.id)
                        WHERE value <> (SELECT value FROM metrics_staging WHERE id = metrics.id);"""
            _sql3 = """DELETE FROM metrics WHERE id NOT IN (SELECT id from local_metrics_staging) AND id NOT IN (SELECT id from metrics_staging);"""
            
            #print('1l')
            self.execute_sql(_sql1l)
            #print('1r')
            self.execute_sql(_sql1r)
            #print('2l')
            self.execute_sql(_sql2l)
            #print('2r')
            self.execute_sql(_sql2r)
            #print('3')
            self.execute_sql(_sql3)
        except Exception as e:
            log.error('failed syncing all staging metrics to metrics table: %s',e)
        
    def serve_local_metrics(self):
        metrics = self.sql_to_json('SELECT * FROM local_metrics')
        rows = []
        
        for m in metrics:
            if m['metric'] in self.configs['exclude_metrics']:
                continue
            
            tag = json.loads(m['tags'])
            tag_str = '{'
            for key, val in tag.items():
                tag_str += (key+'='+'"'+val+'",')
            tag_str = tag_str[:-1]
            tag_str += '}'
            
            row = m['metric']+tag_str+' '+m['value']
            rows.append(row)
        
        data = '\n'.join(rows)
        
        return data

    def serve_all_metrics(self):
        metrics = self.sql_to_json('SELECT * FROM metrics')
        rows = []
        
        for m in metrics:
            if m['metric'] in self.configs['exclude_metrics']:
                continue
            
            tag = json.loads(m['tags'])
            tag_str = '{'
            for key, val in tag.items():
                tag_str += (key+'='+'"'+val+'",')
            tag_str = tag_str[:-1]
            tag_str += '}'
            
            row = m['metric']+tag_str+' '+m['value']
            rows.append(row)
        
        data = '\n'.join(rows)
        
        return data
        
if __name__ == '__main__':

    db = LpMetricsDb('lpmetrics.db')  