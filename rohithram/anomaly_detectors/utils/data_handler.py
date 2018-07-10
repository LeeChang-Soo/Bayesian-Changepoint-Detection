

import numpy as np
import pandas as pd
import psycopg2
import json
from pandas.io.json import json_normalize

#importing reader and checker for reading data
from anomaly_detectors.reader_writer import reader_new as reader
from anomaly_detectors.reader_writer import checker as checker
import datetime as dt
# error code is python file which contains dictionary of mapped error codes and messages for different errors
from anomaly_detectors.utils.error_codes import error_codes

import warnings
warnings.filterwarnings('ignore')

    
class Postgres_Writer():
    
    
    def __init__(self,anomaly_detectors,db_credentials,sql_query_args,table_name,window_size=10):
        
        '''
        Used for mapping the outputs of anomaly detector to corresponding Asset timeline logging and bulk writes the 
        queries to local db at one shot.It is instantiated after anomaly detected for all metrics in 
        an asset likewise for all such assets from master python file.
        Arguments need while instantiating this class are :
        anomaly_detectors : List of anomaly detector objects (Its object of bayesian changept detector class)
        db_credentials : dictionary of credentials for connecting to db
        sql_query_args : dictionary of args or values used to form the columns in the table for each row
        table_name : string - table name
        window_size : (int) no of points either side of around anomaly to write into db
        '''
        
        self.anomaly_detectors = anomaly_detectors
        self.db_credentials = db_credentials
        self.sql_query_args = sql_query_args
        self.table_name = table_name
        self.window_size = window_size
        
        print("Postgres writer initialised \n")

        
    def write_to_db(self,col_names,col_vals):
        
        '''
        connects to db and executes the query for bulk insert.
        Arguments:
        col_names : column names (comma separated)
        col_vals  : list of column values for each row
        '''
        error_codes1 = error_codes()
        
        col_vals1 = [[str(val) if(type(val)!=str) else "'{}'".format(val) for val in row] for row in col_vals]
        joined_col_vals = ["({})".format(','.join(map(str,val))) for val in col_vals1]
        fmt_col_vals = (','.join(joined_col_vals))
        insert_query = """ INSERT INTO {} ({}) VALUES{};""".format(self.table_name,col_names,fmt_col_vals)
        
        status = 0
        conn = None
        cur = None
        try:
            conn = psycopg2.connect(**self.db_credentials)
            cur = conn.cursor()
            cur.execute(insert_query)
            conn.commit()
            cur.close()
            conn.close()
            print('\n Successfully written into database\n')
            return error_codes1['success']
        except psycopg2.DatabaseError as error:
            status = 1
            print("Database error : {}".format(error))
            error_codes1['db']['message']=str(error)
            return error_codes1['db']
        finally:
                if cur is not None:
                    cur.close()
                if conn is not None:
                    conn.close()
        
        
    def ts_to_unix(self,t):
        return int((t - dt.datetime(1970, 1, 1)).total_seconds()*1000)
    
    def map_outputs_and_write(self):
        
        '''
        maps the values to corresponding columns of the table
        Checks whether the algo is univariate or multivariate and proceeds accordingly
        '''
        
        sql_query_args = self.sql_query_args
        col_names_list = list(sql_query_args.keys())
        col_names = ','.join(col_names_list)
        col_vals = []
        table_name = self.table_name
        
        if(self.anomaly_detectors[0].algo_type=='univariate'):
            '''
            # looping through the list of anomaly detectors which are instances for different metrics and assets
            # They have info like anomaly indexes and data , etc
            # appends the mapped column values to list for bulk inserting
            '''
            for anomaly_detector in self.anomaly_detectors:
                
                queries = self.make_query_args_univariate(anomaly_detector,sql_query_args)
                [col_vals.append(list(query.values())) for query in queries]

        else:
            '''
            in construction - will be updated shortly for multivariate case
            '''
            
            print("\nMultivariate writer initialised")
            
            for anomaly_detector in self.anomaly_detectors:
                assetno = anomaly_detector.assetno
                sql_query_args = self.sql_query_args
                queries = self.make_query_args_multivariate(anomaly_detector,sql_query_args)
                
                [col_vals.append(list(query.values())) for query in queries]
        
        # if there are nothing to write don't connect to db
        if(len(col_vals)!=0):
            return self.write_to_db(col_names,col_vals)
        else:
            print("\nNo anomaly detected to write\n")
            error_codes1 = error_codes()
            return error_codes1['success']
        
        
    def make_query_args_univariate(self,anomaly_detector,sql_query_args):
        
        '''
        Function to map the details about an anomaly to columns present in log asset timeline table
        Arguments :
        Takes in single anomaly detector and loops over the anomalies and also sql query arguments.
        Returns sql queries -> list of all mapped sql column values for each anomaly
        '''
        
        sql_queries = []
        
        #Proceed only if no of anomalies detected are not zero
        
        if(anomaly_detector.anom_indexes is not None and len(anomaly_detector.anom_indexes)!=0):
                
                anom_indexes = anomaly_detector.anom_indexes
                original_data = anomaly_detector.data
                col_index = anomaly_detector.data_col_index
                metric_name = original_data.columns[anomaly_detector.data_col_index]
                assetno = anomaly_detector.assetno
                window = self.window_size
                
                sql_query_args['event_name'] = '{}_'.format(original_data.columns[col_index])+anomaly_detector.algo_code+'_anomaly'
                sql_query_args['event_source'] = anomaly_detector.algo_name
                sql_query_args['operating_unit_serial_number'] = str(assetno)
                sql_query_args['parameter_list'] = '[{}]'.format(original_data.columns[anomaly_detector.data_col_index])
                
                for i in anom_indexes:
                    event_ctxt_info =  {"body":[]}
                    data_per_asset = {"asset": '',"readings":[]}
                    data_per_metric = {"name":'',"datapoints":''}

                    time_series = (original_data.index[i-window:i+window])
                    sql_query_args['event_timestamp'] =  str(pd.to_datetime(original_data.index[i],unit='ms',utc=True))
                    sql_query_args['event_timestamp_epoch'] = str(int(original_data.index[i]))
                    sql_query_args['created_date'] = str(pd.to_datetime(dt.datetime.now(),utc=True))
                    time_around_anoms = ["''{}''".format((t)) for t in time_series]                    

                    data_per_metric['name']=metric_name
                    datapoints = (list(zip(time_around_anoms,list(original_data.iloc[i-window:i+window,col_index].values))))
                    data_per_metric['datapoints'] = datapoints
                    data_per_asset['asset'] = assetno
                    data_per_asset['readings'].append(data_per_metric)
                    event_ctxt_info['body'].append(data_per_asset)

                    sql_query_args['event_context_info'] = json.dumps(event_ctxt_info)
                    sql_queries.append(sql_query_args)

        return (sql_queries)

    def make_query_args_multivariate(self,anomaly_detector,sql_query_args):

            '''
            Function to map the details about an anomaly to columns present in log asset timeline table
            Arguments :
            Takes in single anomaly detector and loops over the anomalies and also sql query arguments.
            Returns sql queries -> list of all mapped sql column values for each anomaly
            '''

            sql_queries = []

            #Proceed only if no of anomalies detected are not zero

            if(anomaly_detector.anom_indexes is not None and len(anomaly_detector.anom_indexes)!=0):

                    anom_indexes = anomaly_detector.anom_indexes
                    try:
                        original_data = pd.DataFrame(anomaly_detector.data.numpy())
                    except:
                        original_data = anomaly_detector.data

                    metric_names = anomaly_detector.metric_name
                    assetno = anomaly_detector.assetno
                    window = self.window_size

                    sql_query_args['event_name'] = '{}_'.format('_'.join(metric_names))+anomaly_detector.algo_code+'_anomaly'
                    sql_query_args['event_source'] = anomaly_detector.algo_name
                    sql_query_args['operating_unit_serial_number'] = str(assetno)
                    sql_query_args['parameter_list'] = '[{}]'.format(','.join(metric_names))

                    for i in anom_indexes:

                        time_series = (original_data.index[i-window:i+window])
                        sql_query_args['event_timestamp'] =  str(pd.to_datetime(original_data.index[i],unit='ms',utc=True))
                        sql_query_args['event_timestamp_epoch'] = str(int(original_data.index[i]))
                        sql_query_args['created_date'] = str(pd.to_datetime(dt.datetime.now(),utc=True))
                        time_around_anoms = ["''{}''".format((t)) for t in time_series]    

                        event_ctxt_info =  {"body":[]}
                        data_per_asset = {"asset": '',"readings":[]}
                        data_per_asset['asset'] = assetno

                        for k,metric_name in enumerate(metric_names):
                            datapoints = (list(zip(time_around_anoms,
                                                   list(original_data.iloc[i-window:i+window,1+k].values))))
                            
                            data_per_metric = {"name":metric_name,"datapoints":datapoints}

                            data_per_asset['readings'].append(data_per_metric)
                            
                        event_ctxt_info['body'].append(data_per_asset)
                        sql_query_args['event_context_info'] = json.dumps(event_ctxt_info)
                        sql_queries.append(sql_query_args)

            return (sql_queries)
class Data_reader():
    
    
    '''
    Data_reader is a class which contains methods which are used to fetch data using reader api from opentsdb as 
    well as csv file.Which converts json response into list of dataframes per asset with multiple 
    metric being columns from index 1 onwards with timestamp in epoch being index 
    of dataframe and assetno being the first column i.e column index 0.
    '''
    
    def __init__(self,json_data):
        
        #takes json data
        self.json_data = json_data
        print("Data reader initialised \n")

    def read(self):
        
        try:
            response_dict = json.loads(self.json_data)
            
        except Exception as e:
            error_codes1 = error_codes()
            error_codes1['param']['message'] = '{},{}'.format(str(e),str(self.json_data))
            return error_codes1['param']
        

        print("Getting the dataset from the reader....\n")
        entire_data = self.parse_dict_to_dataframe(response_dict)
        
        return entire_data
    
    def parse_dict_to_dataframe(self,response_dict):
        
        '''
        parses the json response from reader api to list of dataframes per asset and metrics being columns of
        each of the dataframe with timestamps being the index and first column is assetno
        Arguments: response json
        Returns -> List of dataframes
        '''
        
        entire_data_set = []
        
        if(len(response_dict['body'])!=0):
            df = json_normalize(data=response_dict, record_path=['body', 'readings', 'datapoints'],
                                meta=[['body', 'assetno'],
               ['body', 'readings', 'name']])
            df.columns = ['timestamp', 'values', 'assetno', 'parameters']
            df = pd.pivot_table(df, values='values', index=['assetno','timestamp'], columns=['parameters'], aggfunc=np.mean)
            data = df.reset_index(drop=False).rename_axis(None,axis=1)
            
            #making the index of the dataframe to be index and deleting the timestamp column
            data.index = data['timestamp']
            del data['timestamp']
            
            #separating the dataframe into groups of distinct assets
            data_per_assets = data.groupby('assetno')
            
            #creating list of dataframes of different assetno and with all metrics being columns in each dataframe
            for name,group in data_per_assets:
                entire_data_set.append(group)
                 
        return entire_data_set