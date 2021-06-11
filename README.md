# Textract-pdf-Lambda

Contains three lambda functions

1 - pdf-producer: Listens to an S3 bucket for an object create event. Upon such an event it scans the bucket and sends the names of any uploaded files to an SQS queue

2 - pdf-scan: Listens to the SQS queue. Retrieves the filename from SQS and sends it to Amazon Textract for asynch text extraction. Tells Textract to send completion notification to an SNS Topic

3 - get-text: Listens to the SNS topic. Parses the completion confirmation and gets/parses extracted text. Saves text to S3 as a csv.