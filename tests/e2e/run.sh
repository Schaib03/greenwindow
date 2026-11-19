#!/usr/bin/env bash
# End-to-end check on a real cluster (kind in CI).
#
# The operator runs with a static forecast in one-minute steps: dirty for the
# first four minutes, clean for two, then dirty again. A job that may wait up to
# ten minutes must be held, started in the clean window, and finish.
set -euo pipefail

IMAGE=${IMAGE:-greenwindow:e2e}
NAMESPACE=greenwindow-e2e
FORECAST="step=1m;600,600,600,600,150,150,600,600,600,600,600,600,600,600,600"

dump() {
  echo "--- operator logs"
  kubectl -n greenwindow logs deploy/greenwindow --tail=200 || true
  echo "--- carbonawarejob"
  kubectl -n "$NAMESPACE" get cajob demo -o yaml || true
  echo "--- events"
  kubectl -n "$NAMESPACE" get events --sort-by=.lastTimestamp || true
}
trap 'dump' ERR

helm upgrade --install greenwindow deploy/chart/greenwindow \
  --namespace greenwindow --create-namespace \
  --set image.repository="${IMAGE%:*}" --set image.tag="${IMAGE##*:}" \
  --set image.pullPolicy=Never \
  --set provider=static --set-string staticForecast="$FORECAST" \
  --set reconcileSeconds=5 --wait --timeout 3m

kubectl create namespace "$NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl -n "$NAMESPACE" apply -f - <<'EOF'
apiVersion: greenwindow.io/v1alpha1
kind: CarbonAwareJob
metadata:
  name: demo
spec:
  duration: 1m
  deadline: 10m
  powerWatts: 500
  jobTemplate:
    spec:
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: work
              image: busybox:1.37
              command: ["sh", "-c", "echo running in the green window; sleep 5"]
EOF

kubectl -n "$NAMESPACE" wait cajob/demo --for=jsonpath='{.status.phase}'=Scheduled --timeout=60s
reason=$(kubectl -n "$NAMESPACE" get cajob demo -o jsonpath='{.status.reason}')
scheduled=$(kubectl -n "$NAMESPACE" get cajob demo -o jsonpath='{.status.scheduledFor}')
echo "reason=$reason scheduledFor=$scheduled"
[ "$reason" = "greener-window" ] || { echo "expected the job to be held"; false; }

if kubectl -n "$NAMESPACE" get job demo-run >/dev/null 2>&1; then
  echo "job started before its window"
  false
fi

kubectl -n "$NAMESPACE" wait cajob/demo --for=jsonpath='{.status.phase}'=Succeeded --timeout=8m

started=$(kubectl -n "$NAMESPACE" get cajob demo -o jsonpath='{.status.startedAt}')
owner=$(kubectl -n "$NAMESPACE" get job demo-run -o jsonpath='{.metadata.ownerReferences[0].kind}')
echo "started=$started owner=$owner"
[ "$owner" = "CarbonAwareJob" ]
[[ "$started" > "$scheduled" || "$started" == "$scheduled" ]]

kubectl -n "$NAMESPACE" get cajob demo -o wide
echo "e2e passed"
