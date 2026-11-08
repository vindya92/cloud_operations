## Runbook

### Security checks
1. Generate `JWT_SIGNING_KEY` with `openssl rand -hex 32` and export it before starting local Compose; never commit or log the value. In AWS deployment, use `JWT_SIGNING_KEY_PARAMETER` to read the key from Parameter Store.
2. Verify `curl -i -X POST http://localhost:8000/chaos -H 'Content-Type: application/json' -d '{}'` returns `401` without authorization.
3. Use `scripts/chaos.sh reset` to verify an authorized change; it obtains a short-lived JWT from the app container.
4. Treat the local HTTP endpoint as trusted-lab-only. For deployment, terminate TLS at ingress and restrict access to Grafana, Prometheus, Alertmanager, Loki, and the webhook.
5. For AWS deployment, confirm the app and load generator use the workload IAM role and can read only the configured SSM parameter; do not inject AWS access keys into Compose.
6. Start with `docker-compose.tls.yml`, confirm HTTP redirects to HTTPS, and verify the certificate hostname and trust chain with a browser or `curl -I https://<your-hostname>/health`.

### Secret or certificate failure
1. If the app fails during startup, verify `AWS_REGION`, `JWT_SIGNING_KEY_PARAMETER`, workload IAM permission for `ssm:GetParameter`, and KMS decrypt permission when using a customer-managed key.
2. If nginx fails to start, confirm `TLS_CERT_DIR` contains readable `fullchain.pem` and `privkey.pem` files matching each other and the deployed hostname.
3. Rotate the SSM parameter value, then recreate the app and load generator so both fetch the new signing key at startup. Existing JWTs signed with the old key will be rejected.

### AppDown
1. `docker compose ps` - is the `app` container running?
2. `docker compose logs app --tail 50` - look for crash or startup errors.
3. Restart: `scripts/chaos.sh up` (or `docker compose restart app`).
4. Confirm `up{job="app"}` returns 1 in Prometheus and the alert resolves.

### HighErrorRate
1. Grafana dashboard: which status codes are rising, and since when?
2. Loki (Explore): `{job="orders-api", level="ERROR"} | json` - read the `msg` / `exception` fields for the root cause.
3. Pick one `request_id`, then `{job="orders-api"} | json | request_id="<id>"` to see the full request.
4. Fix the cause (here: simulated `db_pool_exhausted`), then `scripts/chaos.sh reset`.

### ScaleOutNeeded
1. Dashboard: check "In-flight requests per replica" and "Requests / sec per replica" for saturation or uneven balancing.
2. Add capacity: `scripts/scale.sh 5`.
3. Confirm in-flight per replica and p95 latency drop and the alert resolves.

### HighLatencyP95
1. Dashboard: which percentile moved? Compare with Host CPU to rule out resource saturation.
2. Prometheus: `histogram_quantile(0.95, sum by (le, endpoint) (rate(http_request_duration_seconds_bucket[1m])))` to find the slow endpoint.
3. Loki: `{job="orders-api"} | json | duration_ms > 1000`.
4. Mitigate, then `scripts/chaos.sh reset`.
