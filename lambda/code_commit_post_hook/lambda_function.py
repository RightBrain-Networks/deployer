#!/usr/bin/env python2.7
import re
import json
import urllib2
import logging
from optparse import OptionParser
from jenkins import Jenkins


logger = logging.getLogger()
logger.setLevel(logging.ERROR)
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

def lambda_handler(event, context):
    print("Received: %s" % event)
    jenkins_info = json.loads(event['Records'][0]['customData'])
    if 'Parameters' in jenkins_info and jenkins_info['Parameters']:
        jenkins_info['Parameters'] = json.loads(jenkins_info['Parameters'])
    else:
        jenkins_info['Parameters'] = {}
    reference = event['Records'][0]['codecommit']['references'][0]['ref']
    jenkins_info['Parameters']['BRANCH'] = re.sub('^refs/heads/','',reference)
    server = Jenkins(jenkins_info['URL'], 
                     username=jenkins_info['Username'], 
                     password=jenkins_info['Password'])
    server.build_job(jenkins_info['Build'], 
                     parameters=jenkins_info['Parameters'])
    

if __name__ == "__main__":
    usage = "usage: %prog [options]"
    parser = OptionParser(usage=usage)
    parser.add_option("-j","--jenkins_url", help="Jenkins URL to use.")
    parser.add_option("-u","--username", help="Jenkins user to use.")
    parser.add_option("-p","--password", help="Jenkins password to use.")
    parser.add_option("-b","--build", help="Job name to build.")
    parser.add_option("-e","--parameters", help="Json of parameters.", default=None)
   
   
    (opts, args) = parser.parse_args()

    options_broken = False
    if not opts.jenkins_url:
        logger.error("Must Specify Jenkins URL")
        options_broken = True
    if not opts.build:
        logger.error("Must Specify job to build")
        options_broken = True
    if not opts.username:
        logger.error("Must Specify Username")
        options_broken = True
    if not opts.password:
        logger.error("Must Specify Password")
        options_broken = True
    if options_broken:
        parser.print_help()
        exit(1) 

    event = { 
        "Records": [
            {
                "customData": { 
                    "URL": opts.jenkins_url, 
                    "Build": opts.build, 
                    "Username": opts.username, 
                    "Password": opts.password, 
                    "Parameters": opts.parameters 
                }
            }
        ]
    }
    lambda_handler(event, None)
