"""
NOTE: Some of the functions in this file are not used as I couldnt get SQS to work
Processes the Textract completion confirmation, 
	gets the extracted text (JSON), 
	parses it appropriately and
	saves it as a csv in S3
"""

import json
import boto3
import botocore
import logging
import pandas as pd
from io import StringIO
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
	
def get_extracted_text(jobid):

	LOG.info("Creating Textract Client")
	textract = boto3.client('textract')
	LOG.info(f'Retrieving text for job: {jobid}')
	response = textract.get_document_text_detection(
		JobId= jobid )
	
	documentText = ""
	for item in response['Blocks']:
	    if item['BlockType'] == "LINE":
	        documentText += item['Text'] + "\n" 
	LOG.info(f'Document text: {documentText}')
	return documentText
	
# def extract_entities(text):
	
# 	LOG.info("Creating Comprehend Client")
# 	comprehend = boto3.client('comprehend')
# 	LOG.info("Detecting Entities")
# 	response = comprehend.detect_entities(
# 		Text = text,
# 		LanguageCode = 'en'
# 		)
# 	for output in response['KeyPhrases']:
# 		entities += output['Text'] + '\n'
# 	LOG.info(f'Entities detected: {entities}')
# 	return entities

# def extract_key_phrases(text):
	
# 	LOG.info("Creating Comprehend Client")
# 	comprehend = boto3.client('comprehend')
# 	LOG.info("Detecting Key Phrases")
# 	response = comprehend.detect_key_phrases(
# 		Text = text,
# 		LanguageCode = 'en'
# 		)
# 	for output in response['Entities']:
# 		phrases += output['Text'] + '\n'
# 	LOG.info(f'Key phrases detected: {phrases}')
# 	return phrases


	
def apply_text_analysis(df,columns = 'JobId'):
	
	df['Text'] = df[columns].apply(get_extracted_text)
	#df['Entities'] = df['Text'].apply(extract_entities)
	#df['KeyPhrases'] = df['Text'].apply(extract_key_phrases)
	return df
    
def create_dataframe(job_ids,filenames):
	"""
	Takes a list of job ids and creates a list with a JobId column
	"""
	
	LOG.info('Generating image name column')
	df = pd.DataFrame({'JobId':job_ids,"FileName":filenames})
	return df

def write_s3(df, out_bucket, job_ids, fname):
	"""
	Write S3 Bucket
	"""
	
	csv_buffer = StringIO()
	df.to_csv(csv_buffer)
	s3_resource = boto3.resource('s3')
	filename = f"{fname[:-4]}_text.csv"
	response = s3_resource.Object(out_bucket, f'detected_text/{filename}').put(Body=csv_buffer.getvalue())
	LOG.info(f'Result of write to bucket: {out_bucket} with:\n {response}')	
	
def lambda_handler(event, context):
	"""
	Lambda Entrypoint
	"""
	LOG.info(f'SURVEYJOB LAMBDA, event {event}, context {context}')
	message_id = event['Records'][0]["Sns"]['MessageId']
	sns_topic_arn = event['Records'][0]['Sns']['TopicArn']
	
	job_ids = []
	filenames = []
	
	# Process Queue
	for record in event['Records']:
		# Generate list of images and Delete queue messages
		body = record['Sns']
		LOG.info(f'Sns Event Body: {body}')
		message = json.loads(body['Message'])
		LOG.info(f'Textract Message: {message}')
		jobid = message['JobId']
		status = message['Status']
		fname = message['DocumentLocation']['S3ObjectName']

		# Capture for processing
		job_ids.append(jobid)
		filenames.append(fname)
		
		extra_logging = {"textractJob":jobid,"pdf-file":fname,"textractStatus":status}
		LOG.info(f"SQS CONSUMER LAMBDA, splitting sns arn with value: {sns_topic_arn}",extra=extra_logging)
		topic_name = sns_topic_arn.split(':')[-1]
		extra_logging['topic_name'] = topic_name
		#LOG.info(f"Attemping Deleting SQS receiptHandle {receipt_handle} with queue_name {qname}", extra=extra_logging)
		#response = delete_sqs_msg(queue_name=qname, receipt_handle=receipt_handle)
		#LOG.info(f"Deleted SQS receipt_handle {receipt_handle} with response {response}", extra=extra_logging)
		
		LOG.info(f'Processing message {message_id}.',extra_logging)
		if status == "SUCCEEDED":
			# Make dataframe with jobids
			LOG.info(f'Creating dataframe with JobIds: {job_ids}, FileNames: {filenames}')
			df = create_dataframe(job_ids,filenames)
			
			# Get text
			df = apply_text_analysis(df)
			LOG.info(f'Textract stage complete: {df.to_dict()}')
			
			# Write result to S3
			LOG.info(f'Writing to {OUTPUT_BUCKET}')
			write_s3(df=df, out_bucket=OUTPUT_BUCKET, job_ids=job_ids, fname=fname) #test lambda