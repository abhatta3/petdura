#!/bin/bash
# Script to stop EC2 instance for cost saving

INSTANCE_ID="i-08485a2568f4c0103"
REGION="us-east-1"

echo "==> Stopping EC2 instance ($INSTANCE_ID)..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION"
echo "==> Stop command sent successfully."
