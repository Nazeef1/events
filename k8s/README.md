# Running EventSphere on Kubernetes (single machine)

A minimal Kubernetes setup for learning, using **minikube** on one computer.
Docker Compose stays the everyday way to run the project; these manifests
describe the same system the way Kubernetes expects it.

## How Compose concepts map to Kubernetes

| Docker Compose | Kubernetes | Where |
|---|---|---|
| a service with `image:` | **Deployment** (keeps N copies of a pod running) | every `*.yaml` |
| the service name other containers call (`http://booking-service:8000`) | **Service** (stable DNS name and virtual IP in front of pods) | same files |
| `healthcheck:` | **readinessProbe** (send traffic only when ready) and **livenessProbe** (restart if stuck) | `services.yaml`, `edge.yaml` |
| the `*-migrate` one-shot jobs + `depends_on: service_completed_successfully` | an **initContainer** that runs `alembic upgrade head` before the app container starts | `services.yaml` |
| `.env` interpolated into `environment:` | a **Secret** built from `.env`, read with `secretKeyRef` | all files |
| named volume `postgres_data` | **PersistentVolumeClaim** | `postgres.yaml` |
| bind-mounted init script | **ConfigMap** mounted into the container | `postgres.yaml` |
| `ports: "127.0.0.1:3000:3000"` | nothing is exposed by default; use `kubectl port-forward` | below |
| `docker-compose.yml` as a whole | **Namespace** `eventsphere` + `kustomization.yaml` listing the files | `namespace.yaml`, `kustomization.yaml` |

`depends_on` has no direct equivalent: Kubernetes starts everything at once,
and pods that can't reach a dependency yet simply fail their readiness probe
or restart until it's up. That's normal, so expect a few restarts in the
first minute.

## Run it

Needs `minikube` and `kubectl` (both installed in this machine's Ubuntu WSL).
Stop the Compose stack first (`docker compose stop`), because port-forwarding
uses the same ports 3000 and 8080. Run these from the repository root.

```bash
# 1. Start a local cluster (adjust memory to what your machine can spare)
minikube start --cpus=4 --memory=6g

# 2. Build the images straight into minikube's Docker, so no registry is needed.
#    The manifests use imagePullPolicy: Never for the same reason.
eval $(minikube docker-env)
docker compose build

# 3. Create the namespace and turn your .env into a Kubernetes Secret
kubectl create namespace eventsphere
kubectl -n eventsphere create secret generic eventsphere-env --from-env-file=.env

# 4. Apply everything
kubectl apply -k k8s/

# 5. Watch it come up (Ctrl+C when every pod is Running and READY 1/1)
kubectl -n eventsphere get pods -w

# 6. Reach the app from your browser
kubectl -n eventsphere port-forward svc/frontend 3000:3000 &
kubectl -n eventsphere port-forward svc/api-gateway 8080:8080 &
python3 scripts/seed_demo.py        # demo events on a fresh database
```

Then open http://localhost:3000.

## Useful commands

```bash
kubectl -n eventsphere get pods                       # what's running
kubectl -n eventsphere logs deploy/booking-service    # a service's logs
kubectl -n eventsphere logs deploy/booking-service -c migrate   # its migration step
kubectl -n eventsphere describe pod <pod-name>        # why a pod is stuck
kubectl -n eventsphere rollout restart deploy/payment-service   # restart after changing the Secret
kubectl -n eventsphere exec -it deploy/postgres -- psql -U eventsphere -d booking_db
```

After editing `.env`, recreate the Secret and restart the affected deployments:

```bash
kubectl -n eventsphere create secret generic eventsphere-env --from-env-file=.env --dry-run=client -o yaml | kubectl apply -f -
kubectl -n eventsphere rollout restart deploy
```

## Clean up

```bash
kubectl delete namespace eventsphere   # removes everything, including the database volume
minikube stop                          # stops the cluster; minikube delete removes it entirely
eval $(minikube docker-env -u)         # point docker back at your normal engine
```

## What a production setup would add

This is deliberately the simplest working version. A real cluster would also have:

- **Ingress** with a TLS certificate instead of port-forwarding, serving `/` and `/api` on one domain.
- **An image registry** (GHCR, ECR) and real image tags instead of `:local` with `imagePullPolicy: Never`.
- **Managed PostgreSQL, Redis and RabbitMQ** rather than running stateful services in the cluster.
- **NetworkPolicies** so each pod may only reach the services it actually calls. That is network-level zero trust, complementing the service tokens the code already checks.
- **Several replicas**, resource-based autoscaling (HorizontalPodAutoscaler) and PodDisruptionBudgets.
- Secrets from a secret manager instead of a file.
