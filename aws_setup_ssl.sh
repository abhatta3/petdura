#!/bin/bash
# Script to provision 10-year self-signed SSL cert and Nginx config on a fresh EC2 instance

sudo amazon-linux-extras enable nginx1 && sudo yum install -y nginx
sudo mkdir -p /etc/pki/tls/certs /etc/pki/tls/private

# If certs are stored in repo or generated:
sudo openssl req -x509 -nodes -days 3650 -newkey rsa:2048 \
  -keyout /etc/pki/tls/private/petdura-10yr.key \
  -out /etc/pki/tls/certs/petdura-10yr.crt \
  -subj "/CN=petdura.com/O=Petdura/C=US"

sudo cp nginx.conf.template /etc/nginx/conf.d/petdura.conf
sudo rm -f /etc/nginx/conf.d/default.conf
sudo nginx -t && sudo systemctl enable nginx && sudo systemctl restart nginx
