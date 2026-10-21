# Deploy on AWS EC2

These instructions copy the application to any directory on a Linux EC2
instance. A Git repository is not required. The server reads the catalog path
from an environment variable, so code and data may live in separate locations.

## Requirements

- An EC2 instance with Python 3.10 or newer.
- SSH or AWS Systems Manager access.
- An EC2 security group controlled by your AWS account.
- An authorized CSV, TSV, or existing Parquet catalog.

Do not place AWS keys in this project. Prefer an EC2 IAM role when the instance
must read an input file from S3.

## 1. Package the local folder

Run this from the parent directory of the application:

```bash
cd /path/to/parent
tar \
  --exclude='agentic_browser_prototype/venv' \
  --exclude='agentic_browser_prototype/.venv' \
  --exclude='agentic_browser_prototype/__pycache__' \
  --exclude='agentic_browser_prototype/tests/__pycache__' \
  -czf /tmp/pet-service-search.tar.gz \
  agentic_browser_prototype
```

Copy the archive to the instance, substituting your key, user, and host:

```bash
scp -i /path/to/ec2-key.pem \
  /tmp/pet-service-search.tar.gz \
  ec2-user@EC2_HOST:/tmp/
```

Systems Manager Session Manager or your organization's approved transfer
method can be used instead of exposing SSH.

## 2. Install the application on EC2

Connect to the instance, then run:

```bash
mkdir -p ~/pet-service-search
tar -xzf /tmp/pet-service-search.tar.gz \
  --strip-components=1 \
  -C ~/pet-service-search
cd ~/pet-service-search

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

If Python is absent, install it using the package manager appropriate for the
instance image before creating the virtual environment.

## 3. Build or supply the catalog

Build from files copied to the instance:

```bash
cd ~/pet-service-search
.venv/bin/python build_catalog.py \
  --input imports/services.csv imports/updates.tsv \
  --output data/pet_services.parquet \
  --mode replace
```

If an IAM role permits the instance to read an S3 object, download it first and
then import it locally:

```bash
mkdir -p imports
aws s3 cp s3://YOUR_BUCKET/YOUR_PREFIX/services.tsv imports/services.tsv

.venv/bin/python build_catalog.py \
  --input imports/services.tsv \
  --output data/pet_services.parquet \
  --mode upsert
```

`build_catalog.py` replaces the Parquet file atomically. A running server sees
the updated catalog on subsequent requests without a restart.

## 4. Start Gunicorn

For private access through an SSH tunnel, bind only to the instance loopback
address:

```bash
cd ~/pet-service-search
PET_SERVICE_PARQUET="$PWD/data/pet_services.parquet" \
SEARCH_RESULT_LIMIT=500 \
.venv/bin/gunicorn \
  --workers 2 \
  --threads 4 \
  --bind 127.0.0.1:5050 \
  app:app
```

Check the service on the instance:

```bash
curl http://127.0.0.1:5050/api/health
```

A successful response contains `"status":"ok"` plus listing and ZIP counts.

## 5. Browse securely

### Recommended: SSH tunnel

Leave port 5050 closed in the EC2 security group. From the local computer:

```bash
ssh -i /path/to/ec2-key.pem \
  -L 5050:127.0.0.1:5050 \
  ec2-user@EC2_HOST
```

Open <http://localhost:5050>. Browser traffic travels through the SSH tunnel.

### Direct test access

For a temporary direct test, bind Gunicorn to `0.0.0.0:5050` and add a security
group inbound rule for TCP port 5050 restricted to your public IP with a `/32`
mask. Do not allow `0.0.0.0/0`. Direct Gunicorn traffic is plain HTTP; use an
Application Load Balancer or reverse proxy with TLS before broader use.

## 6. Keep the service running

For persistent operation, run Gunicorn under your instance's service manager.
A systemd unit can use settings similar to these after paths and the Linux user
are adjusted:

```ini
[Unit]
Description=Pet service search
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/pet-service-search
Environment=PET_SERVICE_PARQUET=/home/ec2-user/pet-service-search/data/pet_services.parquet
Environment=SEARCH_RESULT_LIMIT=500
ExecStart=/home/ec2-user/pet-service-search/.venv/bin/gunicorn --workers 2 --threads 4 --bind 127.0.0.1:5050 app:app
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Installing and enabling a system service requires administrator approval on the
instance. Keep the service bound to loopback when a load balancer, reverse
proxy, or SSH tunnel is the network entry point.

## Environment variables

| Variable | Default | Use |
|---|---:|---|
| `PET_SERVICE_PARQUET` | Application-relative catalog | Absolute or relative Parquet path |
| `SEARCH_RESULT_LIMIT` | `500` | Maximum results per request, from 1 to 1000 |
| `APP_HOST` | `127.0.0.1` | Bind address for `python app.py` only |
| `APP_PORT` | `5050` | Port for `python app.py` only |
| `APP_DEBUG` | `false` | Development debugging; leave false on EC2 |

Gunicorn's bind address is controlled by its `--bind` argument, not `APP_HOST`
or `APP_PORT`.
