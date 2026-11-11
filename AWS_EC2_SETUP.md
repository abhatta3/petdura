# AWS EC2 Setup — Petdura Webserver Deployment

**Date:** 2026-11-07  
**AWS Account:** `734763904658`  
**User:** `anindya`  
**Region:** `us-east-1`  

---

## Instance Details

| Field | Value |
|-------|--------|
| **Instance ID** | `i-08485a2568f4c0103` |
| **Instance Type** | `t4g.medium` (ARM Graviton, 2 vCPU, 1 GiB RAM) |
| **Image** | Amazon Linux 2 (arm64) |
| **Public IP** | `35.168.23.39` |
| **Availability Zone** | `us-east-1a` |
| **State** | Running |
| **Security Group** | `petdura-webserver` (`sg-0049e924b70fbd58f`) |
| **Subnet** | `subnet-0d89a55fb8dac9246` |

## Access Credentials

### SSH Key Pair
- **Key Name:** `petdura-ssh`
- **File:** `~/.ssh/petdura-ssh.pem` (copy-paste in ~/.ssh/authorized_keys)
- **SSH command:**
```bash
ssh -i ~/.ssh/petdura-ssh.pem ec2-user@35.168.23.39
```

### AWS CLI Verified
```bash
aws sts get-caller-identity
# Output: arn:aws:iam::734763904658:user/anindya
```

### Application Test
```bash
curl http://35.168.23.39:5050
```
Expected: HTTP 200

---

## What Was Set Up

### 1. IAM Policy — `PedduraEC2Deploy`
Attached to user `anindya`. Allows:
- `ec2:RunInstances`, `DescribeInstances`, `TerminateInstances`, `DescribeSecurityGroups`, `AuthorizeSecurityGroups`
- `ec2:CreateSecurityGroup`, `DeleteSecurityGroup`, `AuthorizeSecurityGroupIngress`, `AuthorizeSecurityGroupEgress`
- `s3:GetObject`, `s3:ListBucket` on `petdura-data/*`
- `ec2:CreateKeyPair`, `DescribeKeyPairs`

### 2. Security Group — `petdura-webserver`
Allows SSH (port 22) and HTTP (port 5050) from anywhere.

### 3. User Data Script — Auto-deploys Petdura on boot
Clones repo, installs Flask + deps, starts app on port 5050.

### 4. EKS / Orchestration Notes (for future sessions)
To re-launch or manage from new session:
- Create instance with same AMI/user-data or use `terraform`
- Or attach additional policies needed
- Or use EC2 RunInstances directly (same credentials)

---

## Cleanup Commands

```bash
# Stop instance (preserves data, no charges)
aws ec2 stop-instances --instance-ids i-08485a2568f4c0103

# Terminate instance (delete + data)
aws ec2 terminate-instances --instance-ids i-08485a2568f4c0103

# Delete security group (after instance terminated)
aws ec2 delete-security-group --group-id sg-0049e924b70fbd58f

# Delete SSH key pair (optional)
aws ec2 delete-key-pair --key-name petdura-ssh
rm ~/.ssh/petdura-ssh.pem
```

---

## Next Steps / Common Tasks

| Task | Command |
|------|---------|
| Re-launch EC2 | `aws ec2 run-instances --image-id ami-00877e028964afdfa --instance-type t4g.medium --key-name petdura-ssh ...` |
| Attach new policy | `aws iam attach-user-policy --user-name anindya --policy-arn arn:aws:iam::734763904658:policy/PedduraEC2Deploy` |
| Enable MFA | IAM → Users → anindya → Security credentials → Activate MFA |
| Use aws-vault (encrypted) | `brew install aws-vault; aws-vault configure petdura` |

---

*This file is local only — NOT pushed to GitHub. For new OpenRouter sessions with SSO login, use these credentials.*
