# EduMentor Voice Observability Stack

This directory contains configuration files to deploy a local, self-hosted Prometheus, Alertmanager, and Grafana stack to scrape backend metrics and monitor rules.

## Starting the Stack

From this directory (`infra/observability`), run:

```bash
docker-compose up -d
```

This will pull and run the official images:
- **Prometheus** on port `9090`
- **Alertmanager** on port `9093`
- **Grafana** on port `3000`

---

## Verifying Targets (Scraping)

After launching the stack, open your browser and check if the backend scraper is successfully pulling metrics:

- Go to: **[http://localhost:9090/targets](http://localhost:9090/targets)**
- You should see the target `edumentor-backend` scraping `host.docker.internal:8000/metrics`.
- The state should show as **"UP"**.

---

## Verifying Alert Rules

To verify that the custom alert rules have loaded correctly:

- Go to: **[http://localhost:9090/alerts](http://localhost:9090/alerts)**
- Verify that the following alert rules are visible and loaded:
  1. `QueueReclaimingDuringHealthyOperation` (Severity: `critical`)
  2. `QueueDepthSustainedHigh` (Severity: `warning`)
  3. `HighRejectionRate` (Severity: `warning`)
  4. `TTFTLatencyRegression` (Severity: `warning`)

---

## Grafana Dashboard

To access the Grafana dashboard:

1. Open your browser and navigate to: **[http://localhost:3000](http://localhost:3000)**
2. Log in with the default credentials:
   - **Username**: `admin`
   - **Password**: `admin`
   - *Note: For any production or public deployments, these default credentials MUST be changed immediately.*
3. Navigate to **Dashboards** and select the **EduMentor Overview** dashboard.
4. The dashboard is automatically provisioned and displays panels tracking:
   - **Time to first token (p50/p95/p99)**
   - **Total turn latency (p50/p95/p99)**
   - **Queue depth over time**
   - **Enqueue vs rejected vs acked (rate)**
   - **Stale job reclaims** (green if 0, red if > 0)
   - **Endpointing decisions by reason**
   - **Celebrations triggered by emotion type**
   - **Memory recall hit rate**

