# Setting up petdura.com and www.petdura.com for EC2

To point `petdura.com` and `www.petdura.com` to your EC2 instance (`54.156.44.33`), configure the following DNS records with your domain registrar (or Route 53 / Cloudflare):

## DNS Records
| Type | Name / Host | Value / Target | TTL |
|------|-------------|----------------|-----|
| **A** | `@` (root `petdura.com`) | `54.156.44.33` | 300 seconds (or auto) |
| **CNAME** | `www` (`www.petdura.com`) | `petdura.com` (or `54.156.44.33`) | 300 seconds (or auto) |

---

## Optional: Nginx Reverse Proxy (Port 80/443 to Port 5000)
If you want users to visit `http://petdura.com` without typing `:5000`, you can install Nginx on EC2 or run Docker on port 80.

To run Docker on port 80 directly:
```bash
sudo docker run -d -p 80:5000 --restart always --name petdura petdura
```
*(Note: Requires root privileges for binding to port 80).*
