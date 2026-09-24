# PairRoom on AWS (course proof of concept)

This directory documents the development and production deployments. Commands
that provision, deploy or delete resources are operator actions, not part of
local validation. Run PowerShell examples from `module-02`.
The existing local `docker-compose.yaml` is unchanged.

## Architecture and exact resource inventory

The existing `pairroom-course` stack is **development** and must remain in place,
including instance `i-0f8241cfdf9d0678b`, its application and database. A separate
`pairroom-production` stack uses this same template for an independent production
host and database. Normal main CI deploys to development; production receives the
exact successfully deployed development image digest through a manual promotion
workflow. See [CI/CD and promotion](cicd.md).

Module 4 production provisioning and the first manual promotion are complete.
See the [verification record](cicd.md#development-and-production) for the source
development run and confirmed production health/frontend results.

Reuse VPC `vpc-0e23edcb51f3c8731`, public subnet `subnet-0af20b3001186f57e`, and
the existing internet gateway. Each stack owns its own security group, instance,
public IP and encrypted 20 GiB root disk. Each host generates its own database
password and has its own Docker network and PostgreSQL volume. No database data
is copied or shared. This adds a second host's EC2, EBS and public IPv4 costs.

Both hosts reuse `PairRoomEC2SSMProfile` (EC2 trust, only
`AmazonSSMManagedInstanceCore`). For a new stack, pass its name. Attaching
the existing profile to another host does not change development's attachment.
The GitHub OIDC provider is shared, but deployment roles are scoped to
one environment and one instance each. Neither workflow provisions infrastructure.

`cloudformation.yaml` declares exactly two resources:

| Logical resource | What it creates |
| --- | --- |
| `WebSecurityGroup` | One security group in an existing VPC: public TCP 80, TCP 22 from your single IPv4 `/32`, outbound IPv4 traffic allowed. |
| `Server` | One Amazon Linux 2023 x86-64 EC2 instance, default `t3.small` (2 vCPU, 2 GiB), with a primary network interface, automatically assigned public IPv4, and one encrypted 20 GiB gp3 root EBS volume. |

There is no new VPC, subnet, Internet Gateway, NAT Gateway, Elastic IP, load
balancer, RDS instance, ECR repository, S3 bucket, DNS record, IAM role, IAM user,
access key, or Secrets Manager secret. The existing EC2 key pair is referenced.
The AWS-managed public SSM parameter supplies the AMI ID; no parameter is created.
By default the instance has no IAM instance profile. CloudFormation can attach an
existing SSM profile through `InstanceProfileName`; see [GitHub Actions setup](cicd.md).
Do not supply static AWS credentials to the instance.

On first boot, user data enables/starts the Amazon Linux SSM agent, installs Docker and checksum-verifies a pinned Compose
plugin, then writes `/opt/pairroom/compose.yaml`, a root-only `.env` with a
random database password, and a boot service.

`StartPairRoomOnBootstrap` defaults to `'true'`, preserving the existing startup
behavior. Set it to `'false'` for infrastructure-only production provisioning.
Bootstrap still enables SSM and Docker, installs Compose, creates configuration
and a fresh database password, but does not enable/start `pairroom.service` or
create/start any application or PostgreSQL containers. The new EBS disk is ready;
the PostgreSQL Docker volume and database are initialized only at first deployment.
`bootstrap-complete` means host preparation finished, not application readiness.
An `initial-deployment-pending` marker identifies this prepared, idle state.
Rebooting this idle host does not start PairRoom.

The first authorized promotion writes the selected digest override before enabling
and starting `pairroom.service`. That service sets the public-IP origin and starts
both containers with health checks. Only successful startup removes the pending
marker; failure retains it for a retry. Later deployments update only the app.
This parameter controls initial user data only; changing it on an existing stack
does not stop/start the existing application. Do not update the development stack.

When started, Compose runs two containers:

- PairRoom publishes host port 80 to container port 8000, serving the frontend,
  API, `/health` and WebSockets with one Uvicorn worker.
- PostgreSQL 16 uses a named Docker volume; port 5432 is not published and is
  reachable only inside the Docker network.

No domain or Caddy is needed. Open `http://PUBLIC_IP`; collaboration uses `ws://`.
HTTP traffic, including private role links and session content, is unencrypted;
use disposable exercise data. Browser clipboard access may be unavailable over
public HTTP; if Copy is blocked, select and copy the displayed invitation link.

Once enabled, `pairroom.service` runs `/opt/pairroom/start.sh` on every boot. It retrieves the
public IPv4 using IMDSv2 from the host, sets `FRONTEND_ORIGINS=http://PUBLIC_IP`
in `.env`, and reconciles Compose. This permits the exact browser origin for
WebSockets, including after a stop/start changes the IP. No wildcard origin or
AWS credentials are used. Metadata remains restricted to IMDSv2 with hop limit 1.

The database volume lives on the root EBS disk and survives container recreation, `compose down` without `--volumes`,
reboots, and EC2 stop/start. **Instance termination/replacement or stack deletion
deletes this disk and the database.** This deliberately leaves no retained storage
charging after cleanup. It is not high availability or an automatic backup system.

The instance is small because builds happen locally. CPU credits use `standard`
mode to avoid surplus-credit charges; sustained load can be throttled. EC2, EBS,
public IPv4, and applicable transfer incur charges; do not assume free-tier coverage.
`t3.medium` is an optional 4 GiB alternative if measured memory usage requires it.

## Information and prerequisites needed before deployment

1. AWS account/profile with short-lived credentials (for example an existing SSO
   profile), authorized for CloudFormation, EC2 and reading the public AMI SSM
   parameter in **us-east-1**. No IAM capability flag or access keys are required.
2. Existing VPC and subnet in us-east-1. The subnet must belong to that VPC and
   have a `0.0.0.0/0` route to an Internet Gateway. Network ACLs must permit
   HTTP, your SSH connection and return traffic. A default VPC is usable
   if present; this template does not assume or create one.
3. Existing regional EC2 key pair, its local private key path, and your current
   public IPv4 address as `/32`. Update the SSH rule if that address changes.
4. A publicly pullable **linux/amd64** image built from this repository including
   `/health`. Supply an immutable digest where possible. Private registries need
   additional authentication and are not supported by this minimal bootstrap.
   Public registry publication exposes the packaged application source/assets.
5. Internet egress to Amazon Linux repositories, GitHub and image registries.
   Registry limits or unavailable downloads can fail boot.

## Local validation (no AWS resources)

```powershell
uv tool run --from cfn-lint cfn-lint deploy/aws/cloudformation.yaml --regions us-east-1
uv run --project backend python deploy/aws/validate.py
uv run --project backend pytest backend/tests -q
npm --prefix frontend test
```

`validate.py` extracts the actual embedded Compose document, resolves template
substitutions with dummy values and runs `docker compose config --quiet` without
starting containers. It requires the Docker CLI/Compose plugin and backend dev
dependencies. cfn-lint may download tooling but makes no deployment request.
These checks cannot establish account permissions, networking, successful EC2
bootstrap or public two-browser behavior.

For local two-browser HTTP verification with the repository Compose stack
(port 8100 must be free):

```powershell
docker compose -p pairroom-http-check up -d --build --wait
Invoke-RestMethod http://127.0.0.1:8100/health
npm --prefix frontend run test:e2e:compose
docker compose -p pairroom-http-check down --volumes
```

The last command removes this disposable test database. If bundled Chromium is
unavailable, set `$env:PLAYWRIGHT_CHANNEL = 'msedge'` to use installed Edge.
Local verification passed: cfn-lint, embedded Compose config, 34 backend tests,
49 frontend tests, `/health`, and the two-browser test in Edge with edits taking
224?236 ms. The browser test used local HTTP Compose, not EC2; cloud-init and
public-IP behavior still require verification after an operator deploys.

## Initial provisioning reference

The Module 4 production stack already exists. Do not rerun provisioning against
either existing stack; use manual promotion for application releases. The example
below documents initial provisioning only.

For the dev/prod split, use a **new** stack name `pairroom-production`, pass
`InstanceProfileName=PairRoomEC2SSMProfile`, and set `AppImage` to the
immutable GHCR digest recorded by a successful development deployment. Do not
rebuild/publish another image for production or use the old bootstrap image stored
in the development stack's parameters. Set `StartPairRoomOnBootstrap=false` to
prepare the new host without deploying the application. The required `AppImage`
value is written to the base configuration but is not pulled or started in this
mode; the first promotion overrides it with the verified digest selected then.
The commands below are initial provisioning examples, not a migration script.

Do not update, rename, delete or recreate `pairroom-course` during this split.
Its live template predates SSM instance-profile support, and its root disk has
`DeleteOnTermination: true`. Keep that stack, its AMI and its data unchanged.
Use separate stack variables for all future production operations and confirm
the target instance ID before deployment. Production retains the same single-host,
HTTP and root-disk persistence limitations described above.

Development CI builds and publishes the image. For initial production provisioning,
use the digest from its verified promotion record as `AppImage`. Authenticate to
AWS with your existing short-lived profile, then replace the example values. Run
these commands from `module-02`. Subsequent releases use the manual promotion
workflow, not CloudFormation updates.

```powershell
$env:AWS_PROFILE = 'your-existing-profile'
$Stack = 'pairroom-production'
$Image = 'ghcr.io/robanc/ai-dev-tools-2026@sha256:VERIFIED_DEVELOPMENT_DIGEST'
aws cloudformation deploy --region us-east-1 --stack-name $Stack --template-file deploy/aws/cloudformation.yaml --parameter-overrides VpcId=vpc-0e23edcb51f3c8731 SubnetId=subnet-0af20b3001186f57e KeyName=pairroom-key SshCidr=YOUR_CURRENT_PUBLIC_IPV4/32 AppImage=$Image InstanceProfileName=PairRoomEC2SSMProfile StartPairRoomOnBootstrap=false
aws cloudformation describe-stacks --region us-east-1 --stack-name $Stack --query 'Stacks[0].Outputs' --output table
$ServerIp = aws cloudformation describe-stacks --region us-east-1 --stack-name $Stack --query "Stacks[0].Outputs[?OutputKey=='PublicIp'].OutputValue | [0]" --output text
```

There is no Elastic IP: stop/start may change `$ServerIp`. Retrieve the current
address from EC2 using the `InstanceId` output and open the new IP URL; the boot service refreshes the allowed origin.
For example, after stop/start:

```powershell
$InstanceId = aws cloudformation describe-stacks --region us-east-1 --stack-name $Stack --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue | [0]" --output text
$ServerIp = aws ec2 describe-instances --region us-east-1 --instance-ids $InstanceId --query 'Reservations[0].Instances[0].PublicIpAddress' --output text
```

Existing session links need their host changed to the new IP. Reboot normally
preserves the address. No DNS configuration or certificate issuance is needed.

**CREATE_COMPLETE reports infrastructure creation, not application readiness.**
For infrastructure-only mode, verify cloud-init completion, EC2 running and SSM
Online, `bootstrap-complete` plus `initial-deployment-pending`, an inactive/disabled
`pairroom.service`, and no app/database containers. The public URL is allocated but
does not serve PairRoom until an authorized promotion. The application checks
below apply after that promotion, or when provisioning with startup enabled.
No CloudFormation signal/CreationPolicy is used. Wait for cloud-init and inspect
the containers separately (replace the private key path):

```powershell
ssh -i C:/path/to/key.pem ec2-user@$ServerIp 'sudo cloud-init status --wait'
ssh -i C:/path/to/key.pem ec2-user@$ServerIp 'sudo test -f /opt/pairroom/bootstrap-complete && cd /opt/pairroom && sudo docker compose ps'
Invoke-RestMethod "http://$ServerIp/health"
curl.exe --fail -o NUL "http://$ServerIp"
```

Expect `/health` to return `{"status":"ok"}`, all app/database health checks to
pass, and the home page to return HTTP 200 without an HTTPS redirect. The health handler performs `SELECT 1` and
returns 503 without database details on failure; it does not verify WebSockets.
Open two browser windows at `http://$ServerIp`, create a session and follow its
candidate link. Check both directions of code edits and interviewer problem edits
within one second, candidate read-only problem permissions, refresh persistence,
disconnect/reconnect, and `ws://` traffic (a 101 upgrade in browser developer tools). Repeat persistence checks after
`sudo docker compose restart` from `/opt/pairroom`.

Troubleshoot over SSH with `sudo tail -n 100 /var/log/cloud-init-output.log` and,
from `/opt/pairroom`, `sudo docker compose logs --tail=100` and
`sudo systemctl restart pairroom`. Inspect boot-origin setup with
`sudo journalctl -u pairroom --no-pager`. Do not print `.env` or full
`docker compose config` into shared logs: they contain credentials. Containers
restart with Docker after reboot; a health failure alone does not restart one.

User data runs only on first boot. **Updating CloudFormation parameters does not
reapply the application configuration.** For an image-only update, use development
CI or the manual production promotion workflow described in [CI/CD](cicd.md).
The helper writes `compose.override.yaml`; editing the base `compose.yaml` image
does not override that selection. Keep the same `.env` and volumes. For
infrastructure changes, review a change set and back up before any replacement.
After stop/start, verify `http://NEW_IP/health` and two-browser collaboration
again. If origin setup fails, correct metadata/network access and restart
`pairroom.service`. The database password and volume are preserved.

## Backup and cleanup

If data matters, first write a PostgreSQL dump on the host and copy it out. The
dump contains private session grants: store it securely outside version control.
These commands use remote redirection to avoid binary corruption in PowerShell:

```powershell
ssh -i C:/path/to/key.pem ec2-user@$ServerIp 'sudo sh -c "umask 077; cd /opt/pairroom; docker compose exec -T postgres pg_dump -U pairroom -d pairroom -Fc > /home/ec2-user/pairroom.dump; chown ec2-user:ec2-user /home/ec2-user/pairroom.dump"'
scp -i C:/path/to/key.pem ec2-user@${ServerIp}:/home/ec2-user/pairroom.dump C:/YOUR_SECURE_BACKUP_DIRECTORY/pairroom.dump
```

The dump can be restored with `pg_restore` into a fresh PostgreSQL 16 database
using the app's database user. Verify the backup before deleting valuable data.
To finish the exercise, delete the stack (this destroys its database):

```powershell
aws cloudformation delete-stack --region us-east-1 --stack-name $Stack
aws cloudformation wait stack-delete-complete --region us-east-1 --stack-name $Stack
```

Stack deletion releases the public IP and deletes the instance, root disk and
security group. Delete the published registry image separately if no longer
needed. Existing VPC/subnet, key pair, registry images and downloaded backups are
outside this stack.
No `docker compose down` is required before stack deletion. If deletion fails,
inspect `aws cloudformation describe-stack-events --region us-east-1 --stack-name $Stack`
and resolve the reported dependency/permission issue before retrying.

## References

- [AWS EC2 CloudFormation properties](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ec2-instance.html)
- [Amazon Linux AMI public parameters](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/finding-an-ami-parameter-store.html)
- [EC2 IMDSv2 metadata access](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html)
- [EC2 user-data lifecycle](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/user-data.html)
- [T3 instance specifications](https://aws.amazon.com/ec2/instance-types/general-purpose/)
- [Docker Compose installation](https://docs.docker.com/compose/install/linux/)
