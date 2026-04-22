import os
import json
import boto3
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# def lambda_handler(event, context):
#     # TODO implement
#     return {
#         'statusCode': 200,
#         'body': json.dumps('Hello from Lambda!')
#     }


bedrock_agent = boto3.client("bedrock-agent")

KB_ID = os.environ["KB_ID"]
DATA_SOURCE_ID = os.environ["KB_DS_ID"]

def lambda_handler(event, context):
    logger.info(f"Received S3 event: {json.dumps(event)}")

    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]
        logger.info(f"New document uploaded: s3://{bucket}/{key}")

    # Start ingestion job
    response = bedrock_agent.start_ingestion_job(
        knowledgeBaseId=KB_ID,
        dataSourceId=DATA_SOURCE_ID
    )

    job_id = response["ingestionJob"]["ingestionJobId"]
    status = response["ingestionJob"]["status"]

    logger.info(f"Started KB ingestion job {job_id}, status={status}")

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Ingestion triggered successfully",
            "ingestionJobId": job_id,
            "status": status
        }),
    }
