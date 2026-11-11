#!/bin/bash
# Script to start EC2 instance and run Petdura web server

INSTANCE_ID="i-08485a2568f4c0103"
REGION="us-east-1"
KEY_PATH="$HOME/.ssh/petdura-ssh.pem"

echo "==> 1. Starting EC2 instance ($INSTANCE_ID)..."
aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION"

echo "==> 2. Waiting for instance to enter running state and get Public IP..."
while true; do
    STATUS=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --query "Reservations[0].Instances[0].State.Name" --output text)
    if [ "$STATUS" = "running" ]; then
        break
    fi
    echo -n "."
    sleep 3
done
echo ""

PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
echo "==> Instance is running! Public IP: $PUBLIC_IP"

echo "==> 3. Connecting to EC2, updating code from 'dev', and starting Docker container..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no ec2-user@"$PUBLIC_IP" '
if [ ! -d "petdura" ]; then
    git clone https://github.com/abhatta3/petdura.git
fi
cd petdura
git fetch origin
git checkout dev
git pull origin dev
sudo systemctl start docker
sudo docker stop petdura || true
sudo docker rm petdura || true
sudo docker build -t petdura .
sudo docker run -d -p 5000:5000 --restart always --name petdura petdura
'

echo "==> SUCCESS! Petdura web server is running at: http://$PUBLIC_IP:5000"
