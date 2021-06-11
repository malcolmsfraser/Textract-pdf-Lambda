"""
Scans S3 Bucket for pdf files and sends the file names to SQS queue for future processing
"""

import json
import boto3

# import requests

S3 = boto3.resource('s3')
BUCKET = 'mea-scans'
QUEUE = 'mea-scans'
SQS = boto3.client('sqs')

# SETUP LOGGING
import logging
from pythonjsonlogger import jsonlogger

LOG = logging.getLogger()
LOG.setLevel (logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
LOG.addHandler(logHandler)

def s3_client_connection():
	
	LOG.info('Generating S3 client')
	client = boto3.client('s3')
	return client

def scan_bucket(bucket):
	"""
	Scans table and returns results
	"""
	
	s3_client = s3_client_connection()
	LOG.info(f'Scanning Bucket {bucket}')
	contents = s3_client.list_objects(Bucket=bucket)['Contents']
	LOG.info(f'Found {len(contents)} Items')
	return contents
	
def send_sqs_msg(msg , queue_name, delay=0):
	"""
	Send SQS Message
	
	Expects an SQS queue_name and msg in a dictionary format.
	Returns a response dictionary.
	"""
	
	queue_url = SQS.get_queue_url(QueueName=queue_name)["QueueUrl"]
	queue_send_log_msg = "Send message to queue url: %s, with body: %s" % (queue_url, msg)
	LOG.info(queue_send_log_msg)
	json_msg = json.dumps(msg)
	response = SQS.send_message(
		QueueUrl = queue_url,
		MessageBody = json_msg,
		DelaySeconds = delay)
	queue_send_log_msg_resp = "Message Response: %s for queue url: %s" % (response, queue_url)
	LOG.info(queue_send_log_msg_resp)
	return response
	
def send_emissions(bucket, queue_name):
	"""
	Send Emissions
	"""
	
	contents = scan_bucket(bucket)
	
	for image in contents:
		image_name = image['Key']
		if 'processed' in image_name:
			continue
		LOG.info(f"Sending item {image_name} to queue: {queue_name}")
		response = send_sqs_msg(image_name, queue_name)
		LOG.debug(response)

def lambda_handler(event, context):
	"""
	Lambda Entrypoint
	"""
	
	extra_logging = {'bucket':BUCKET, 'queue': QUEUE}
	LOG.info(f'event{event}, context {context}', extra = extra_logging)
	send_emissions(bucket=BUCKET, queue_name=QUEUE) # test comment