# GitHub Actions CI/CD

The repository-root `.github/workflows/cicd.yaml` runs on pull requests, pushes to `main`, and manual
runs. Backend and frontend unit tests run in parallel. Once both pass, CI builds
the Docker Compose stack, runs the PostgreSQL integration suite (including app
restart persistence), and runs the two-browser end-to-end suite against port
8100. Cleanup runs even on failure. These tests never use AWS credentials.

Successful `main` runs save the tested image as a short-lived workflow artifact.
The production job publishes that image to GHCR without rebuilding, assumes an
AWS role using OIDC, and uses SSM Run Command to update the existing EC2 host.
It waits for Compose health checks, checks the running image digest, and polls
the current public IP's `/health` for HTTP 200 and exactly `{"status":"ok"}`.
An SSM failure or health timeout fails the job. Production deployments are
serialized and active deployments are not automatically cancelled.

## One-time setup

1. Provision the host using [the AWS guide](README.md). The workflow updates an
   existing deployment; it does not create or replace infrastructure. Create an
   EC2 IAM role trusting `ec2.amazonaws.com`, attach the AWS-managed
   `AmazonSSMManagedInstanceCore` policy, and put that role in an instance profile.
   Supply its name as `InstanceProfileName` when deploying/updating the template.
   This optional parameter creates no IAM resources. The provisioning operator
   needs `iam:PassRole` for this role. On an existing host, attaching the profile
   does not rerun user data or replace the database.
2. Ensure the Amazon Linux SSM agent is running (`sudo systemctl enable --now
   amazon-ssm-agent`) and the instance appears Online in Systems Manager. Allow
   outbound HTTPS to regional SSM services and GHCR; no new inbound port is needed.
   Wait for `/opt/pairroom/bootstrap-complete` before the first workflow deploy.
3. Create/use the IAM OIDC provider `https://token.actions.githubusercontent.com`
   with audience `sts.amazonaws.com`. Create a deployment role using the trust
   policy below, substituting your AWS account and exact GitHub owner/repository.
4. Attach the permissions policy below to the deployment role, substituting
   region, account and the single instance ID. The GitHub role and EC2 role are
   separate. No static AWS keys, SSH keys, `iam:PassRole`, or CloudFormation write
   permissions are needed by the workflow.
5. Create a GitHub environment named `production`. Restrict its deployment
   branches to `main` (the environment-based OIDC subject has no branch claim).
   Add these environment variables:

   | Variable | Value |
   | --- | --- |
   | `AWS_ROLE_ARN` | ARN of the GitHub OIDC deployment role |
   | `AWS_REGION` | `us-east-1` for the supplied infrastructure |
   | `AWS_INSTANCE_ID` | Existing PairRoom EC2 instance ID |

6. Allow GitHub Actions to write packages. The workflow publishes to
   `ghcr.io/OWNER/REPOSITORY`, tagged with the commit SHA. **Make this GHCR package
   public** so EC2 can pull anonymously. New packages default to private: the
   first run may publish then intentionally fail its anonymous manifest check.
   Change package visibility and rerun. An existing package must grant this
   repository Actions write access. Publication exposes packaged source/assets.

OIDC role trust policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": {"Federated": "arn:aws:iam::ACCOUNT:oidc-provider/token.actions.githubusercontent.com"},
    "Action": "sts:AssumeRoleWithWebIdentity",
    "Condition": {"StringEquals": {
      "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
      "token.actions.githubusercontent.com:sub": "repo:OWNER/REPOSITORY:environment:production"
    }}
  }]
}
```

Deployment role permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "ssm:SendCommand",
      "Resource": [
        "arn:aws:ssm:REGION::document/AWS-RunShellScript",
        "arn:aws:ec2:REGION:ACCOUNT:instance/INSTANCE_ID"
      ]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetCommandInvocation", "ec2:DescribeInstances"],
      "Resource": "*"
    }
  ]
}
```

`SendCommand` permits root commands on that one host; protect the environment
and repository accordingly. AWS requires `*` for the two read operations above.
See [GitHub's AWS OIDC setup](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
and [AWS SendCommand](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_SendCommand.html).

## Operation and verification

CI writes `/opt/pairroom/compose.override.yaml` with an immutable image digest.
Compose automatically loads this alongside `compose.yaml`, including at boot.
The database container, `.env`, and volume are preserved. The public endpoint
remains HTTP as described in the AWS guide. Health includes database connectivity;
it does not establish production WebSocket behavior. Application updates briefly
interrupt connections; clients reconnect using their existing links.

Failed health validation does not automatically roll back or delete resources.
Inspect the printed SSM command ID in Systems Manager. To roll back, use the
deployment helper with a previously successful public digest as `DEPLOY_IMAGE`,
plus `AWS_INSTANCE_ID`, `AWS_REGION`, and authorized short-lived AWS credentials:

```powershell
uv run --project backend python deploy/aws/deploy.py
```

Alternatively restore the previous digest in `compose.override.yaml` over SSH
and run `sudo docker compose up -d --no-deps --wait app` from `/opt/pairroom`.
After CI is enabled, changing only the base Compose image will not override the
CI override file. Update `AWS_INSTANCE_ID` after any infrastructure replacement.

Local checks:

```powershell
uv run --project backend pytest backend/tests -q
uv run --project backend python -m unittest discover -s deploy/aws/tests -v
uv run --project backend python deploy/aws/validate.py
npm --prefix frontend test
docker compose up --build -d --wait
npm --prefix frontend run test:integration
npm --prefix frontend run test:e2e:compose
```

Use a disposable Compose project for integration tests. Remove its test volume
with `docker compose down --volumes` when finished. The deployment helper tests
mock AWS and HTTP; a successful production workflow is required to verify actual
OIDC permissions, SSM connectivity, registry access and the public health check.
