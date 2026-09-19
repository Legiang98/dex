import json
import os
import boto3
from pydantic import ValidationError
from models.webhook import WebhookPayload
from constants.http import HTTP

sqs = boto3.client('sqs', region_name=os.environ.get("AWS_REGION", "us-east-1"))

def handler(event, context):
    try:
        body_str = event.get('body')
        if not body_str:
            return {
                "statusCode": HTTP.BAD_REQUEST,
                "body": json.dumps({"message": "No body provided"})
            }
            
        body = json.loads(body_str)
        
        # Step 1: Validate schema (Fast Pydantic validation)
        raw_payload = WebhookPayload(**body)
        
        # Step 2: Push to Queue for background processing
        queue_url = os.environ.get("SQS_QUEUE_URL")
        if not queue_url:
            raise ValueError("SQS_QUEUE_URL not configured")
            
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=raw_payload.model_dump_json()
        )
        
        # Step 3: Return success to TradingView
        return {
            "statusCode": HTTP.OK,
            "body": json.dumps({"message": "Signal received and queued successfully."})
        }
        
    except json.JSONDecodeError as e:
        print("Gatekeeper JSON Error:", e)
        return {
            "statusCode": HTTP.BAD_REQUEST,
            "body": json.dumps({"error": "Request body must be valid JSON"})
        }
    except ValidationError as e:
        print("Gatekeeper Validation Error:", e)
        return {
            "statusCode": HTTP.BAD_REQUEST,
            "body": json.dumps({"error": e.errors()})
        }
    except Exception as e:
        print("Gatekeeper Error:", e)
        return {
            "statusCode": HTTP.INTERNAL_SERVER_ERROR,
            "body": json.dumps({"error": str(e) or "Internal Server Error"})
        }
