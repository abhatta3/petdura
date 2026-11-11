# Petdura Production Deployment & Disaster Recovery Guide

This guide details how to spin up a brand new EC2 instance, deploy the Docker container, configure Nginx with SSL and Rate Limiting, and set up automated security (Fail2ban + Certbot).

---

## 1. Prerequisites
- AWS EC2 instance running **Amazon Linux 2 (arm64 or x86_64)**.
- Security Group allowing inbound ports:
  - **Port 22** (SSH)
  - **Port 80** (HTTP - for Let's Encrypt validation & redirection)
  - **Port 443** (HTTPS - secure web traffic)

---

## 2. Clone Repository & Start Docker App
```bash
git clone https://github.com/abhatta3/petdura.git
cd petdura
git checkout dev

# Install Docker & start service
sudo amazon-linux-extras install docker -y || sudo yum install -y docker
sudo systemctl start docker
sudo systemctl enable docker

# Build and run Docker container on port 5000 (proxied by Nginx)
sudo docker build -t petdura .
sudo docker run -d -p 5000:5000 --restart always --name petdura petdura
```

---

## 3. Install Nginx, Certbot & Fail2ban
```bash
# Enable EPEL & Nginx repo
sudo amazon-linux-extras enable nginx1 epel -y || true
sudo yum install -y nginx certbot python2-certbot-nginx fail2ban

# Start Fail2ban
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

---

## 4. Obtain Let's Encrypt SSL Certificate
Ensure your domain (`petdura.com` and `www.petdura.com`) points to your EC2 Elastic IP, then run Certbot:
```bash
sudo certbot --nginx -d petdura.com -d www.petdura.com --non-interactive --agree-tos -m admin@petdura.com --redirect
```

---

## 5. Configure Nginx (SSL, Rate Limiting, Security Headers)
Create `/etc/nginx/conf.d/petdura.conf` with the following production configuration:

```nginx
limit_req_zone $binary_remote_addr zone=petdura_limit:10m rate=15r/s;

server {
    listen 80;
    server_name petdura.com www.petdura.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name petdura.com www.petdura.com;

    ssl_certificate /etc/letsencrypt/live/petdura.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/petdura.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    # Rate limiting (DDoS & scraper protection)
    limit_req zone=petdura_limit burst=30 nodelay;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Test and reload Nginx:
```bash
sudo rm -f /etc/nginx/conf.d/default.conf
sudo nginx -t && sudo systemctl restart nginx
sudo systemctl enable nginx
```

---

## 6. Setup Automated SSL Renewal (Cron)
Add a cron job to renew Let's Encrypt certificates automatically twice daily:
```bash
(sudo crontab -l 2>/dev/null; echo "0 0,12 * * * certbot renew --quiet && systemctl reload nginx") | sudo crontab -
```
