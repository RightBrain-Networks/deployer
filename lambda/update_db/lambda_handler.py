import logging
import json
import urllib
import botocore.session
import boto3
import pymysql.cursors
from cfnresponse import send, SUCCESS,FAILED

logger = logging.getLogger()
logger.setLevel(logging.ERROR)

def lambda_handler(event, context):
    try:
        if(event['RequestType'] == 'Create'):
            #connect to mysql
            conn = mysql_connect(event['ResourceProperties']['DB_HOST'], \
            event['ResourceProperties']['DB_USER'], \
            event['ResourceProperties']['DB_PASSWORD'] )
            
            #create user database
            create_database(conn, event['ResourceProperties']['USER_DB_NAME'], \
            event['ResourceProperties']['USER_DB_USER'], \
            event['ResourceProperties']['USER_DB_PASSWORD'])
            
            #create analysis database
            create_database(conn, event['ResourceProperties']['ANALYSIS_DB_NAME'], \
            event['ResourceProperties']['ANALYSIS_DB_USER'], \
            event['ResourceProperties']['ANALYSIS_DB_PASSWORD'])
            
            #create report database
            create_database(conn, event['ResourceProperties']['REPORT_DB_NAME'], \
            event['ResourceProperties']['REPORT_DB_USER'], \
            event['ResourceProperties']['REPORT_DB_PASSWORD'])
            
            conn.close()
            send(event, context, SUCCESS)
        else:
            logger.debug("No action on delete or update")
            send(event, context, SUCCESS)
    except Exception as e:
        logger.error(e)
        send(event, context, FAILED, str(e))
        raise
    return

def mysql_connect(host, user, password):
    conn = pymysql.connect(host=host,
                             user=user,
                             password=password,
                             cursorclass=pymysql.cursors.DictCursor)
    return conn

def create_database(conn, DB, USER, PASS):
    try:
        cursor = conn.cursor()
        # Create a new database
        print "creating database"
        sql = "create database "+DB
        cursor.execute(sql)
            
        print "creating user"
        #create user
        sql = "CREATE USER '"+USER+"'@'%' IDENTIFIED BY '"+PASS+"'"
        cursor.execute(sql)
            
        print "granting user"
        #grant priv
        sql = "GRANT ALL ON "+DB+".* TO '"+USER+"'@'%';"
        cursor.execute(sql)
    finally:
        conn.commit()
