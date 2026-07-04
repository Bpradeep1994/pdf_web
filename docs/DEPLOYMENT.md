# Deployment Guide (AWS / Kubernetes)

Production topology: managed AWS data services + the app running on **EKS**, deployed with
the Helm chart in `deploy/helm/pdf-editor`. CI/CD via GitHub Actions
(`.github/workflows/{ci,cd}.yml`).

```
Route53 ─► CloudFront ─► ALB (Ingress) ─► gateway ─► auth/pdf/ai/ocr/conversion
                                       └► frontend
                         EKS pods ─► RDS(Postgres)  ElastiCache(Redis)
                                     AmazonMQ(RabbitMQ)  S3  Qdrant(StatefulSet)
```

## 1. Provision managed services

| Concern | AWS service | Notes |
|---|---|---|
| Postgres | **RDS for PostgreSQL** (15+) | enable `uuid-ossp`, `pg_trgm`; multi-AZ for prod |
| Cache / rate-limit | **ElastiCache for Redis** | auth token + gateway rate limiting |
| Queue | **Amazon MQ (RabbitMQ)** | background jobs |
| Object storage | **S3** | bucket `pdf-documents`; block public access; SSE-S3/KMS |
| Vector DB | **Qdrant** | in-cluster StatefulSet or Qdrant Cloud |
| CDN | **CloudFront** | in front of the frontend + static assets |
| DNS / TLS | **Route53** + **ACM** | `app.example.com`, `api.example.com` |
| Cluster | **EKS** | + AWS Load Balancer Controller for ALB Ingress |

IAM: give the pods an IRSA role scoped to the S3 bucket (preferred over static keys).

## 2. Bootstrap the database schema

The baseline schema is `database/migrations/001_init.sql` (enums, tables, triggers).
Apply it **once** to the RDS instance, then stamp Alembic:

```bash
psql "$DATABASE_URL_PSQL" -f database/migrations/001_init.sql
DATABASE_URL=postgresql+asyncpg://... alembic -c backend/alembic.ini stamp 0001_baseline
```

After this, all schema changes ship as Alembic revisions and run automatically via the
Helm `pre-upgrade` migrate Job (`alembic upgrade head`).

## 3. Create the secret

```bash
kubectl create namespace pdf-editor
kubectl -n pdf-editor create secret generic pdf-editor-secrets \
  --from-literal=SECRET_KEY="$(openssl rand -base64 48)" \
  --from-literal=DATABASE_URL="postgresql+asyncpg://USER:PASS@<rds>:5432/pdfeditor" \
  --from-literal=REDIS_URL="redis://:PASS@<elasticache>:6379/0" \
  --from-literal=RABBITMQ_URL="amqps://USER:PASS@<amazonmq>:5671/" \
  --from-literal=S3_ACCESS_KEY=... --from-literal=S3_SECRET_KEY=... \
  --from-literal=OPENAI_API_KEY=... --from-literal=ANTHROPIC_API_KEY=... --from-literal=GEMINI_API_KEY=... \
  --from-literal=STRIPE_SECRET_KEY=... --from-literal=STRIPE_WEBHOOK_SECRET=... \
  --from-literal=GOOGLE_CLIENT_ID=... --from-literal=GOOGLE_CLIENT_SECRET=... \
  --from-literal=GITHUB_CLIENT_ID=... --from-literal=GITHUB_CLIENT_SECRET=...
```

For production, prefer the **External Secrets Operator** (pulls from AWS Secrets Manager)
or **SealedSecrets** instead of `kubectl create secret`.

## 4. Deploy with Helm

```bash
aws eks update-kubeconfig --name <cluster> --region <region>

helm upgrade --install pdf-editor deploy/helm/pdf-editor \
  --namespace pdf-editor \
  --set image.registry=ghcr.io/<owner>/<repo> \
  --set image.tag=v1.0.0 \
  --set ingress.apiHost=api.example.com \
  --set ingress.appHost=app.example.com \
  --set config.ALLOWED_ORIGINS=https://app.example.com \
  --wait --timeout 10m
```

The chart creates Deployments + Services + HPAs for all 7 services, a ConfigMap, the
ALB Ingress, and runs the Alembic migrate Job as a pre-upgrade hook.

## 5. DNS / CDN

- ACM certs for `app.` and `api.` in the ALB region.
- Point Route53 `api.example.com` → ALB; `app.example.com` → CloudFront (origin = ALB/frontend).
- Set `NEXT_PUBLIC_API_URL=https://api.example.com` at frontend build time.

## 6. CI/CD

- **CI** (`ci.yml`): frontend type-check/lint/build, backend static tests, and a full
  docker-compose integration run (e2e + increment suites) on every PR.
- **CD** (`cd.yml`): on a `v*` tag, builds & pushes all 7 images to GHCR, then
  `helm upgrade --install` to EKS. Requires repo secrets:
  `AWS_DEPLOY_ROLE_ARN`, `AWS_REGION`, `EKS_CLUSTER_NAME`.

## 7. Operations

- **Scaling**: HPAs scale on CPU (see `values.yaml`); tune `maxReplicas` per service.
- **Rolling updates**: default Deployment strategy; the migrate Job runs before pods roll.
- **Observability**: add the CloudWatch/Prometheus agent; app `/health` endpoints back
  readiness/liveness probes.
- **Backups**: RDS automated snapshots; S3 versioning + lifecycle to Glacier for old versions.
