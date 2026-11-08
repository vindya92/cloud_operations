# Cloud Operations: Monitoring, Alerting & Debugging

End-to-end observability lab covering the **Foundation** and **Practitioner** levels of the *Monitoring & Alerting & Debugging* competency.

## Stack

| Tool | Role | URL |
|---|---|---|
| Flask `orders-api` (Python), 3 replicas | Instrumented sample service, JSON logs, fault injection | via load balancer |
| nginx (`lb`) | Load balancer in front of the replicas | http://localhost:8000 |
| Redis | Shared state (orders, chaos settings) so replicas stay stateless | internal |
| Prometheus | Metrics collection and alert rules | http://localhost:9090 |
| Alertmanager | Alert routing, grouping, inhibition | http://localhost:9093 |
| Grafana | Dashboards and log exploration | http://localhost:3000 |
| Loki + Promtail | Centralized log aggregation | http://localhost:3100 |
| node-exporter | Host metrics | internal |
| `webhook` | Alert receiver (stands in for Slack/PagerDuty) | http://localhost:5050 |
| `loadgen` | Continuous synthetic traffic | internal |

## Run

```bash
export JWT_SIGNING_KEY="$(openssl rand -hex 32)"
docker compose up -d --build
```

Open Grafana at http://localhost:3000 (no login), dashboard **Cloud Operations / Orders API**.

## Level mapping

- **Foundation (one toolset):** Prometheus + Grafana - metrics, dashboards, alert rules, debugging from graphs.
- **Practitioner (multiple toolsets):** adds Loki/Promtail (logs), Alertmanager (routing, inhibition), node-exporter (host metrics), and correlating metrics with logs via `request_id` during incidents.

## CI/CD learning path

This repository currently has Docker Compose and service Dockerfiles, but no automated CI/CD workflow. Use the existing `orders-api` as the change you carry through the cycle; start locally before adding a hosted deployment.

| Level | What you own in this project | Evidence of progress |
|---|---|---|
| **Foundation** | Make a small app change; run the app and verify it locally; build the app image; review the change; deploy with Compose; check `/health` and the Grafana dashboard; recover or roll back if it fails. | You can explain your change, the checks you ran, how it was deployed, and how you knew it was healthy. |
| **Practitioner** | Follow a change from commit and pull request through automated tests, image build/tag, security checks, deployment to a test environment, smoke checks, monitoring, and rollback. Investigate failures using Prometheus, Grafana, Loki, Alertmanager, and the runbook. | You can trace a release to its commit/image, interpret pipeline failures, safely deploy and roll back, and explain the operational impact. |

### Practice in small steps

1. Pick one bounded change, such as adding a health-check assertion or adjusting an alert. Write down expected behavior before editing.
2. Run the narrow local check, then `docker compose up -d --build`; verify `curl -f http://localhost:8000/health` and inspect the relevant dashboard or logs.
3. Simulate a failure with `scripts/chaos.sh errors` or `latency`, follow the incident exercise, and finish with `scripts/chaos.sh reset`.
4. For Practitioner practice, add a CI workflow that runs tests and builds the image on a pull request. Only after that is reliable, add image publishing and deployment to a non-production environment, with secrets stored in the platform's secret manager.
5. Record a short release note: commit, checks, image tag, deployment result, alert/metric observed, and rollback method. Repeat with a different change.

Keep the feedback loop small: one change, one relevant automated check, one deployment, then inspect the result. Add pipeline stages when they remove a real manual risk; do not begin with a large multi-environment pipeline. Keep production credentials and TLS private keys out of CI logs and repository files.

### Use AI sparingly

- Ask about one file or one failing check at a time; include only the relevant code, exact error, and expected result.
- Ask for a minimal diff and a focused test, not a broad repository redesign.
- Run commands and inspect logs yourself; share only the relevant output when asking for help.
- Use AI to explain an unfamiliar pipeline step or review a proposed change, then write down the lesson so you do not need to ask it again.

## Security exercise

- **Foundation:** identify the trust boundaries (nginx is public; Redis and app replicas are internal), limit exposed ports, and distinguish authentication, authorization, encryption in transit, and secret storage.
- **Practitioner:** `POST /api/orders` and `POST /chaos` require a signed JWT bearer token. Tokens include issuer, audience, subject, issued-at, and 10-minute expiry claims. The API validates the signature and claims; invalid or expired tokens receive `401`. The load generator and chaos script create tokens using the signing key.
- The app also limits request bodies and adds basic response security headers. Never commit or log the signing key. Rotate it by changing the key in the configured source and recreating the app/loadgen containers; existing tokens stop validating against the new key.
- This local lab serves plain HTTP on port 8000, so credentials are not encrypted in transit. Use TLS at the public ingress/reverse proxy in any real deployment, and use a managed secret store rather than a shell environment variable for production credentials. Grafana and other demo service ports are intentionally unauthenticated and must not be exposed publicly.

## TLS and managed credentials (AWS deployment)

The production overlay terminates TLS in nginx and redirects HTTP to HTTPS. Provide a trusted certificate and private key as `fullchain.pem` and `privkey.pem` in a host directory; keep the private key out of source control. Set `TLS_CERT_DIR` to that directory. The certificate must be valid for the hostname clients use.

The app and load generator can read the JWT signing key from AWS Systems Manager Parameter Store using `JWT_SIGNING_KEY_PARAMETER` and `AWS_REGION`. Use a Standard-tier `SecureString` parameter and grant the workload IAM role `ssm:GetParameter` on that exact parameter ARN (plus `kms:Decrypt` only when using a customer-managed KMS key). No AWS access keys should be placed in Compose; use the cloud workload's IAM role. Parameter Store Standard has no additional parameter storage charge, though AWS account, networking, certificate, and other service costs may still apply.

Create the parameter with a securely generated token, configure the three variables, then start with the TLS overlay:

```bash
aws ssm put-parameter --name /cloud-operations/orders-api/jwt-signing-key --type SecureString --tier Standard --value "$(openssl rand -hex 32)"
export AWS_REGION=us-east-1
export JWT_SIGNING_KEY_PARAMETER=/cloud-operations/orders-api/jwt-signing-key
export TLS_CERT_DIR=/secure/path/to/certificate-files
docker compose -f docker-compose.yml -f docker-compose.tls.yml up -d --build
```

Ensure the AWS identity running the app and load generator has the scoped IAM permission, and the host directory contains the certificate files before starting. The original `docker compose up` path remains for local practice; set `JWT_SIGNING_KEY` to a random value before launching it.

When using the TLS overlay, set `APP_URL=https://<your-hostname>` before running `scripts/chaos.sh`; this sends the control request directly over HTTPS instead of relying on the HTTP redirect.

## Incident exercises

Use `scripts/chaos.sh {errors|latency|down|up|reset}`.

| Command | Expected alert | Debug path |
|---|---|---|
| `errors` | `HighErrorRate` | Dashboard error ratio, then Loki error logs, then root cause `db_pool_exhausted` |
| `latency` | `HighLatencyP95` | Latency percentiles, then find slow endpoint, then Loki `duration_ms` |
| `down` | `AppDown` (suppresses the other two) | `docker compose ps`, then logs |

Always finish with `scripts/chaos.sh reset` (or `up`).

Alerts appear in Prometheus (Alerts tab), Alertmanager, and `docker compose logs -f webhook` (or http://localhost:5050).
Response steps are in [docs/runbook.md](docs/runbook.md).

## Horizontal scaling

The app is stateless (state in Redis) and runs as 3 replicas behind nginx. Prometheus discovers replicas through DNS, and the dashboard has per-replica panels.

```bash
scripts/scale.sh 5               # change replica count
scripts/scale.sh load 60 0       # heavy load: 60 workers, no think time
scripts/scale.sh load 4 300      # back to normal load
for i in $(seq 10); do curl -si localhost:8000/health | grep -i x-served-by; done   # see balancing
```

Experiment: with heavy load, 1 replica gave about 59 req/s and about 0.96s average end-to-end latency; 3 replicas gave about 159 req/s and about 0.26s. The `ScaleOutNeeded` alert fires when average in-flight requests per replica stay above 5 (of 8 threads).

Issues found while scaling: in-memory state diverged between replicas (fixed with Redis), chaos settings were per-replica (moved to Redis), and concurrent log writers (fixed with one log file per replica).

## Stop

```bash
docker compose down -v
```
