# GitHub Actions CI/CD

The repository-root `.github/workflows/cicd.yaml` runs on pull requests, pushes to `main`, and manual
runs. Backend and frontend unit tests run in parallel. Once both pass, CI builds
the Docker Compose stack, runs the PostgreSQL integration suite (including app
restart persistence), and runs the two-browser end-to-end suite against port
8100. Cleanup runs even on failure. These tests never use AWS credentials.

Successful `main` runs save the tested image as a short-lived workflow artifact.
The development job publishes that image to GHCR without rebuilding, assumes an
AWS role using OIDC, and uses SSM Run Command to update the existing EC2 host.
It waits for Compose health checks, checks the running image digest, and polls
the current public IP's `/health` for HTTP 200 and exactly `{"status":"ok"}`.
An SSM failure or health timeout fails the job. Development and production use
separate concurrency groups; active deployments are not automatically cancelled.

## Development and production

Module 4 verification is complete: development CI/CD is working and
`pairroom-production` reached `CREATE_COMPLETE` with instance
`i-0fa130640f25f0056`. The operator verified the first successful **Promote
development to production** workflow using development CI run
[36023467839](https://github.com/robanc/AI-Dev-Tools-2026/actions/runs/36023467839).
Production `/health` returned HTTP 200 with `{"status":"ok"}`, and `/` returned
HTTP 200 serving the PairRoom frontend. These are recorded verification results,
not a live availability check. Retrieve the current public IP using the
[AWS guide](README.md); it can change after stop/start.

The existing `pairroom-course` stack and instance `i-0f8241cfdf9d0678b` are
development. Keep their application, `.env`, database and disk intact. Production
uses a separate `pairroom-production` stack, EC2 host, security group, credentials
and PostgreSQL volume in the existing VPC/subnet. Production starts with an empty
database; promotion copies the application version, never development data.

Provision production with `StartPairRoomOnBootstrap=false` and the existing
`PairRoomEC2SSMProfile`. The default is `true`, preserving development behavior.
Disabled startup prepares an idle host with SSM, Docker and configuration but no
application/database containers. `bootstrap-complete` then denotes host readiness.
On first promotion, the deployment helper writes the verified digest override,
enables/starts `pairroom.service` to initialize the origin and both containers,
and removes `initial-deployment-pending` only after service success. Subsequent
promotions retain app-only updates. No workflow or extra IAM permissions are needed
for this distinction; both use the existing SSM deployment helper.

Normal successful `main` CI (and manual main CI runs) targets the GitHub environment
`development`. Only after `deploy.py` verifies SSM completion, the running image
and public health does CI write `promotion.json`. The artifact is named
`development-promotion-RUN_ATTEMPT` and retained for 90 days, subject to repository
limits. It records schema version, repository, environment, workflow path, run ID,
attempt, commit SHA and immutable GHCR digest. Upload failure fails the CI run.
The large tested-image artifact still expires after one day; promotion does not
need it because the image is already in GHCR.

`.github/workflows/promote-production.yaml` has only `workflow_dispatch`. From
Actions, select **Promote development to production**, choose **main**, and supply
the successful development CI run ID. Runs dispatched from another branch skip
the promotion job. The production environment must also allow only `main`.

`promote.py resolve` uses the runner's GitHub token with `actions: read` to check:

- The source is this repository's `cicd.yaml`, on main, triggered by push or manual
  dispatch, completed successfully, with a successful `deploy` job in its latest attempt.
- Exactly one unexpired promotion artifact exists for that attempt, with a matching
  SHA-256 archive checksum and matching run/attempt/commit metadata.
- The image is an immutable `ghcr.io/robanc/ai-dev-tools-2026@sha256:...` reference.
- The source run has not changed attempts during validation.

The workflow checks anonymous image availability before obtaining AWS credentials,
then uses the existing deployment helper with the production instance ID. It never
builds, retags or publishes an image. Missing/expired artifacts, deleted registry
images, failed/skipped deployments and old attempts fail closed. Keep candidate
GHCR images available for the promotion/rollback period. The selected version is
a version successfully deployed to development, not necessarily what is currently
running there after newer deployments. Old Module 3 runs have no promotion record
and cannot be selected. Rerun development CI to create a new eligible record.

## One-time setup reference (completed for Module 4)

1. Provision the host using [the AWS guide](README.md). The workflow updates an
   existing host; it does not create or replace infrastructure. Both hosts reuse
   `PairRoomEC2SSMProfile`, whose EC2 role trusts `ec2.amazonaws.com` and has the
   AWS-managed `AmazonSSMManagedInstanceCore` policy.
   Supply that profile as `InstanceProfileName` when creating a new stack.
   Do not update or replace the existing development stack for this split.
   This optional parameter creates no IAM resources. The provisioning operator
   needs `iam:PassRole` for this role. On an existing host, attaching the profile
   does not rerun user data or replace the database.
2. Ensure the Amazon Linux SSM agent is running (`sudo systemctl enable --now
   amazon-ssm-agent`) and the instance appears Online in Systems Manager. Allow
   outbound HTTPS to regional SSM services and GHCR; no new inbound port is needed.
   Wait for `/opt/pairroom/bootstrap-complete` before the first workflow deploy.
3. Reuse the IAM OIDC provider `https://token.actions.githubusercontent.com`
   with audience `sts.amazonaws.com`. Use separate deployment roles: existing
   `PairRoomGitHubDeployRole` for development and
   `PairRoomGitHubProductionDeployRole` for production. Use the exact trust subject
   below with `ENVIRONMENT` replaced by `development` or `production`.
4. Attach the permissions policy below to the deployment role, substituting
   region, account and that environment's single instance ID. The GitHub role and EC2 role are
   separate. No static AWS keys, SSH keys, `iam:PassRole`, or CloudFormation write
   permissions are needed by the workflow.
5. Use separate `development` and `production` GitHub environments.
   Restrict both environments' deployment
   branches to `main` (the environment-based OIDC subject has no branch claim).
   Add these environment variables:

   | Variable | Value |
   | --- | --- |
   | `AWS_ROLE_ARN` | ARN of that environment's GitHub OIDC deployment role |
   | `AWS_REGION` | `us-east-1` for the supplied infrastructure |
   | `AWS_INSTANCE_ID` | That environment's EC2 instance ID |

   Development uses `arn:aws:iam::857953323489:role/PairRoomGitHubDeployRole` and
   `i-0f8241cfdf9d0678b`. Production uses
   `arn:aws:iam::857953323489:role/PairRoomGitHubProductionDeployRole` and
   `i-0fa130640f25f0056`. Both use `us-east-1`. These are environment variables,
   not secrets. OIDC provides temporary AWS credentials; no long-lived AWS access
   keys are used.

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
      "token.actions.githubusercontent.com:sub": "repo:robanc@254978292/AI-Dev-Tools-2026@1353640900:environment:ENVIRONMENT"
    }}
  }]
}
```

This repository's actual OIDC subjects include owner and repository numeric IDs,
as verified in CloudTrail. A subject without these IDs fails authentication. Keep
`StringEquals`, the audience and environment restriction; do not use wildcards.
`ACCOUNT` is `857953323489` and `REGION` is `us-east-1`.

Deployment role permissions (one copy per environment):

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
The production inline policy is `PairRoomProductionSingleInstanceDeploy`; both
of its statements also include
`"Condition": {"StringEquals": {"aws:RequestedRegion": "us-east-1"}}`.
Its only command target is `i-0fa130640f25f0056`, so it grants no deployment access
to development. The two read permissions are regional, not instance-scoped.
Production has no attached managed policies or other inline policies. Development
retains its existing `PairRoomSingleInstanceDeploy` policy unchanged.
See [GitHub's AWS OIDC setup](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
and [AWS SendCommand](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_SendCommand.html).

## Operation and verification

### Safe transition from Module 3 (historical procedure)

This transition is complete for Module 4. The sequence below is retained as a
reference, not an instruction to recreate or reconfigure the current deployment.

Do not repoint the existing production environment while the old main workflow
still automatically targets it. First ensure no old deployment is running or
queued, configure development and change the existing role's trust to development,
then publish the updated workflows in a coordinated change. Verify development
CI before enabling production promotion. Provision production separately using a
verified development digest and `StartPairRoomOnBootstrap=false`; provisioning
prepares the host without starting the application. Reuse `PairRoomEC2SSMProfile`.
Create the production-only GitHub deployment role and set production variables
only when its new instance is ready. The first manual promotion starts the database
and application; later promotions update only the application.
Do not dispatch the promotion workflow until the environment points to that host.

The existing live stack predates the optional profile parameter in this template.
Its SSM profile was attached separately. Do not apply the new template to that
stack merely to rename it or adopt these workflows.

CI writes `/opt/pairroom/compose.override.yaml` with an immutable image digest.
Compose automatically loads this alongside `compose.yaml`, including at boot.
The database container, `.env`, and volume are preserved. The public endpoint
remains HTTP as described in the AWS guide. Health includes database connectivity;
it does not establish production WebSocket behavior. Application updates briefly
interrupt connections; clients reconnect using their existing links.

Failed health validation does not automatically roll back or delete resources.
To roll production back, manually promote an earlier successful development run
whose record and image are still available. This changes only the application;
it does not roll back database schema/data. Confirm compatibility first.
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

Local checks (from `module-02`):

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
