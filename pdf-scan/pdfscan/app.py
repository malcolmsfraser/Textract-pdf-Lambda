"""
Retrieves the file name from SQS and sends it to Textract for processing
Deletes message from the SQS queue
Assigns Textract notification to be sent to an SNS topic
"""

import json
import boto3
import botocore
import logging
from pythonjsonlogger import jsonlogger

# import requests


LOG = logging.getLogger()
LOG.setLevel (logging.INFO)
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter()
logHandler.setFormatter(formatter)
LOG.addHandler(logHandler)

BUCKET = "mea-scans"
OUTPUT_BUCKET = "pdf-results"
REGION = 'us-east-1'

def sqs_queue_resource(queue_name):
	"""
	Returns an SQS queue resource connection
	"""
	
	sqs_resource = boto3.resource('sqs', region_name=REGION)
	log_sqs_resource_msg = "Creating SQS resource conn with qname: [%s] in region: [%s]" % (queue_name, REGION)
	LOG.info(log_sqs_resource_msg)
	queue = sqs_resource.get_queue_by_name(QueueName=queue_name)
	return queue
	
def sqs_connection():
	"""
	Creatd an SQS Connection which defaults to global var REGION
	"""
	
	sqs_client = boto3.client('sqs', region_name = REGION)
	log_sqs_client_msg = "Creating SQS connection in Region: [%s]" % REGION
	LOG.info(log_sqs_client_msg)
	return sqs_client

def delete_sqs_msg(queue_name, receipt_handle):
	"""
	Deletes message from SQS queue.
	Returns a response
	"""
	
	sqs_client = sqs_connection()
	try:
		queue_url = sqs_client.get_queue_url(QueueName=queue_name)['QueueUrl']
		delete_log_msg = "Deleting msg with ReceiptHandle %s" % receipt_handle
		LOG.info(delete_log_msg)
		response = sqs_client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
	except botocore.exceptions.ClientError as error:
		exception_msg = "FAILURE TO DELETE SQS MSG: Queue Name [%s] with error [%s]" % (queue_name, error)
		LOG.exception(exception_msg)
		return None
		
	
	delete_log_msg_resp = 'Response from delete from queue: %s' % response
	LOG.info(delete_log_msg_resp)
	return response

def read_scanned_pdf(file_path,bucket_in=BUCKET,bucket_out=OUTPUT_BUCKET):
    
    LOG.info("Creating Textract Client")
    textract = boto3.client('textract')
    LOG.info(f'Detecting text for {file_path}')
    response = textract.start_document_text_detection(
        DocumentLocation={
            "S3Object": {
                "Bucket" : bucket_in,
                "Name" : file_path,
            }
        },
        NotificationChannel={
        'SNSTopicArn': 'arn:aws:sns:us-east-1:751467894674:AmazonTextractStatus',
        'RoleArn': 'arn:aws:iam::751467894674:role/Textract-callSNS-Role'
    	},
        OutputConfig={
            "S3Bucket" : bucket_out,
            },
    )
    LOG.info(f'Text detection for {file_path} finished. Results sent to {bucket_out} S3Bucket.\nResponse: {response}')
    jobid = response['JobId']
    LOG.info(f'JobID:{jobid}')
    
    return jobid

def lambda_handler(event, context):
	"""
	Lambda Entrypoint
	"""
	LOG.info(f'SURVEYJOB LAMBDA, event {event}, context {context}')
	receipt_handle = event['Records'][0]['receiptHandle']
	event_source_arn = event['Records'][0]['eventSourceARN']
	
	pdf_files = []
	
	# Process Queue
	for record in event['Records']:
		# Generate list of images and Delete queue messages
		pdf = json.loads(record['body'])

		# Capture for processing
		pdf_files.append(pdf)
		
		extra_logging = {"image":pdf}
		LOG.info(f"SQS CONSUMER LAMBDA, splitting sqs arn with value: {event_source_arn}",extra=extra_logging)
		qname = event_source_arn.split(':')[-1]
		extra_logging['qname'] = qname
		LOG.info(f"Attemping Deleting SQS receiptHandle {receipt_handle} with queue_name {qname}", extra=extra_logging)
		response = delete_sqs_msg(queue_name=qname, receipt_handle=receipt_handle)
		LOG.info(f"Deleted SQS receipt_handle {receipt_handle} with response {response}", extra=extra_logging)
	
	LOG.info(f'pdf files to scan: {pdf_files}')
	for pdf in pdf_files:
	    read_scanned_pdf(pdf)