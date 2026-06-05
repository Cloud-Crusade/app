# AWS 인프라 · IaC · CI/CD

## 핵심 원칙

> **간략화 우선** — 본 시스템은 학습·실습 규모. 멀티 region · disaster recovery · canary 배포 같은 고급 패턴은 도입하지 않는다. 단일 region 내 Multi-AZ + Rolling update 로 충분하다.

## 인프라 토폴로지 (요약)

```
Region (ap-northeast-2)
├─ VPC
│  ├─ Public subnet (AZ #1, #2)
│  │  ├─ ALB + ACM
│  │  ├─ Bastion
│  │  └─ NAT Gateway (Private → 외부)
│  └─ Private subnet (AZ #1, #2)
│     ├─ EKS Pod (FastAPI)
│     ├─ RDS #1 (core: user/event) — writer + reader
│     ├─ RDS #2 (reservation: reservation/payment) — writer + reader
│     ├─ ElastiCache (Redis cluster)
│     ├─ SQS (작업 큐 + DLQ)
│     ├─ Lambda (SQS consumer)
│     └─ EventBridge (정기 스케줄)
├─ CloudWatch (Logs / Metrics / Alarms)
├─ ECR (서비스 컨테이너 이미지)
└─ S3 (Terraform state + 정적 자산)
```

> 자세한 컴포넌트 책임은 [01-architecture.md](01-architecture.md) 의 "인프라 토폴로지" 섹션 참조.

## Terraform 구조

### 디렉토리 (Infra 레포)

```
terraform/
├── envs/
│   ├── dev/
│   │   ├── main.tf            # module 호출
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── terraform.tfvars
│   └── prod/
│       └── ...
├── modules/
│   ├── network/               # VPC, subnet, NAT, route table
│   ├── eks/                   # EKS cluster + node group
│   ├── rds/                   # RDS instance (writer + reader)
│   ├── elasticache/           # Redis cluster
│   ├── sqs_lambda/            # SQS + Lambda + EventBridge rule
│   ├── alb/                   # ALB + ACM + target group
│   ├── ecr/                   # ECR repository
│   ├── bastion/               # EC2 + SG
│   └── cloudwatch/            # alarm + SNS topic
└── backend.tf                 # S3 + DynamoDB state lock
```

### 작성 규칙
- **module 1개 = 1 책임** — `network` 모듈이 ALB 까지 하지 않는다
- **환경별 차이는 `terraform.tfvars` 만** — 코드 분기 (`if env == ...`) 금지
- **하드코딩 금지** — region, AMI ID, instance type 은 variable
- **state 는 S3 backend** — `backend.tf` 에 정의. DynamoDB 로 lock
- **module versioning** — `source = "../modules/network"` (로컬) 또는 git tag 고정
- **민감값은 SSM Parameter Store / Secrets Manager** — `.tfvars` 에 평문 저장 금지

### 명령 표준

```bash
# 환경 진입
cd terraform/envs/dev

# 변경 미리보기 (자율 진행 가능)
terraform plan -out=tfplan

# 적용 (외부 영향 → 사용자 확인 필수, 07-workflow.md 참조)
terraform apply tfplan

# 특정 리소스만 변경
terraform plan -target=module.eks
```

## EKS

### 클러스터 정책
- **버전**: 안정 버전 최신 -1 (예: 운영 1.30 → 1.29 권장). 새 버전 즉시 도입 금지
- **Node group**: 최소 2 노드 (AZ 분산). 스파이크 대응은 HPA + Cluster Autoscaler ([09-traffic-and-scaling.md](09-traffic-and-scaling.md))
- **노드 타입**: `t3.medium` 기본, 부하 테스트 후 조정
- **Pod 보안**: non-root, read-only root filesystem, securityContext 명시

### Manifest 구조 (Service 레포)

```
deploy/
├── base/                      # kustomize base
│   ├── deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml           # ALB ingress (aws-load-balancer-controller)
│   ├── configmap.yaml
│   ├── hpa.yaml
│   └── kustomization.yaml
├── overlays/
│   ├── dev/
│   │   ├── kustomization.yaml
│   │   └── replicas-patch.yaml
│   └── prod/
│       └── ...
```

### Deployment 표준

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ticketing-api
spec:
  replicas: 2
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels: {app: ticketing-api}
  template:
    metadata:
      labels: {app: ticketing-api}
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: api
          image: <ECR>/ticketing-api:<tag>
          ports: [{containerPort: 8000}]
          envFrom:
            - configMapRef: {name: ticketing-config}
            - secretRef: {name: ticketing-secrets}
          livenessProbe:
            httpGet: {path: /healthz, port: 8000}
            initialDelaySeconds: 10
            periodSeconds: 10
          readinessProbe:
            httpGet: {path: /readyz, port: 8000}
            initialDelaySeconds: 5
            periodSeconds: 5
            failureThreshold: 3
          resources:
            requests: {cpu: "200m", memory: "256Mi"}
            limits:   {cpu: "1000m", memory: "512Mi"}
          lifecycle:
            preStop:
              exec:
                command: ["/bin/sh", "-c", "sleep 5"]   # ALB drain
```

### 규칙
- **`maxUnavailable: 0`** — rolling update 시 가용성 유지
- **`preStop sleep 5`** — ALB 가 target 을 deregister 할 시간 확보
- **resource requests/limits 명시** — HPA·QoS class 결정
- **secret 은 k8s Secret + ExternalSecrets** (Secrets Manager 연동) — manifest 평문 X
- **HPA 정책은 [09-traffic-and-scaling.md](09-traffic-and-scaling.md)** 참조

## ALB + ACM

### 정책
- **TLS 종료는 ALB 에서** — Pod 까지 HTTPS 전파 X (mTLS 도입 전까지)
- **ACM 인증서** — 무료, 자동 갱신
- **타깃은 IP 모드** — AWS Load Balancer Controller (k8s ingress controller) 사용
- **헬스체크 경로**: `/readyz` (5xx 또는 503 응답 시 unhealthy)
- **WAF 미도입** — 필요해질 때 본 룰셋 갱신

### Ingress 예시

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ticketing-api
  annotations:
    kubernetes.io/ingress.class: alb
    alb.ingress.kubernetes.io/scheme: internet-facing
    alb.ingress.kubernetes.io/target-type: ip
    alb.ingress.kubernetes.io/listen-ports: '[{"HTTPS":443}]'
    alb.ingress.kubernetes.io/certificate-arn: arn:aws:acm:...
    alb.ingress.kubernetes.io/healthcheck-path: /readyz
spec:
  rules:
    - host: api.ticketing.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service: {name: ticketing-api, port: {number: 80}}
```

## RDS

### 정책
- **엔진**: PostgreSQL 16 (최신 stable LTS)
- **클래스**: `db.r6g.large` 기본 (writer), `db.t3.medium` (reader). 부하 측정 후 조정
- **Multi-AZ writer**: 자동 페일오버
- **Read replica**: AZ 분산, 최소 1대씩
- **백업**: 자동 daily, 7일 보존
- **암호화**: 저장·전송 모두 (`storage_encrypted = true`, `force_ssl = 1`)
- **파라미터 그룹**: 커스텀 (`max_connections`, `shared_buffers` 조정)

### 커넥션 풀
- **SQLAlchemy `pool_size`**: writer 10, reader 30 (per Pod)
- **`pool_pre_ping = true`** — 끊긴 커넥션 자동 감지
- **`pool_recycle = 1800`** — 30분마다 재생성 (RDS proxy timeout 회피)
- **Pod 수 × pool_size 가 RDS `max_connections` 를 넘지 않도록** 사전 계산
  - 예: 20 Pod × 10 (writer) + 20 Pod × 30 (reader) = 800 → max_connections 1000 이상

### RDS Proxy (선택)
- Pod 수가 RDS 직결 한계를 넘으면 RDS Proxy 도입 검토
- 학습 단계에서는 미도입

## ElastiCache (Redis)

### 정책
- **엔진**: Redis 7.x
- **모드**: cluster mode disabled (단일 primary + replica) — 단순화
- **노드 타입**: `cache.t3.small` 기본
- **암호화**: AUTH token + TLS in-transit
- **eviction policy**: `allkeys-lru`
- **maxmemory**: 인스턴스 메모리의 75%

### 사용 용도 — 좌석 hold + 잔여 카운터 + 결제·예매 캐시

| 용도 | Key prefix | TTL |
|---|---|---|
| 좌석 hold | `seat:hold:{event_id}:{seat_no}` | 5 분 |
| 좌석 잔여 카운터 | `seats:remain:{event_id}` | 무기한 (이벤트 종료 시 수동 삭제) |
| 결제 내역 캐시 | `payment:{payment_history_id}` | `PAYMENT_CACHE_TTL_SECONDS` (기본 3600s) |
| 결제 미영속 인덱스 | `payment:user:{user_id}` (set) | `PAYMENT_CACHE_TTL_SECONDS` (생성 시 갱신) |
| 예매 단건 캐시 | `reservation:{reservation_id}` | `RESERVATION_CACHE_TTL_SECONDS` (기본 300s) |
| 예매 미영속 인덱스 | `reservation:user:{user_id}` (set) | `RESERVATION_CACHE_TTL_SECONDS` (생성 시 갱신) |

> 결제 캐시는 단건 cache-aside + **생성 시 낙관적 적재**(write 가 SQS→Lambda 비동기라 DB 반영 전에도 단건/다건 조회에 보이도록). 결제 기록은 불변이라 무효화 없이 TTL 만으로 충분. 목록 조회는 per-user 인덱스(`payment:user:{user_id}`)로 미영속분을 DB 결과와 병합하며, DB 영속·만료분은 조회 시 인덱스에서 정리(self-heal)한다.
>
> 예매 단건 캐시(value=전체 ReservationRead). 생성 시 낙관적 적재 — write 가 SQS→Lambda 비동기라 DB 반영 전에도 단건/다건 조회가 hit 하도록 한다. 조회 miss 시에도 적재(cache-aside). 목록 조회는 결제와 동일하게 per-user 인덱스(`reservation:user:{user_id}`)로 미영속분을 DB 결과와 병합하며, DB 영속·만료분은 조회 시 인덱스에서 정리(self-heal)한다. 예매는 취소로 변경 가능하므로 cancel 요청 시 단건 캐시 무효화 + 인덱스에서 제거하고, 잔여 staleness 는 짧은 TTL 로 제한한다.

### 규칙
- **key prefix 는 위 표 다섯 가지만** — 신규 prefix 추가 시 본 문서 갱신 필수
- **TTL 필수** — 위 카운터 외 무기한 key 금지
- **mutate 전 `nx=True` 보장** — race 회피 (좌석 hold)
- **장애 시 graceful fallback** — Redis 다운 시 좌석 hold 는 DB row lock 으로 fallback (성능 ↓, 동작 유지)

### 클라이언트 구성

```python
# app/common/redis.py
from redis.asyncio import Redis, ConnectionPool

_pool: ConnectionPool | None = None

def buildRedis() -> Redis:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(
            settings.redis_url, max_connections=50, decode_responses=True,
        )
    return Redis(connection_pool=_pool)


async def getRedisClient() -> Redis:
    return buildRedis()
```

## SQS + Lambda + EventBridge

### 정책
- **Queue 1개만 정의** — `seat-release` 만. 추가 큐 필요해지면 본 문서 갱신
- **DLQ 필수** — main queue 에 DLQ 연결 (`maxReceiveCount: 3`)
- **Visibility timeout** — Lambda 평균 실행시간 × 6
- **메시지 보존**: main 4 일, DLQ 14 일
- **Encryption**: SSE-SQS

### 표준 큐 정의

| Queue | 용도 | Trigger |
|---|---|---|
| `seat-release` | 만료 hold 의 좌석 잔여 카운터 복구 + 좌석 정합성 보정 | EventBridge 5분 cron |
| `seat-release-dlq` | DLQ | (자동) |

> Redis TTL 만으로 hold 자체는 자동 해제된다. Lambda 가 처리하는 것은 **DB 좌석 잔여 카운터 와 Redis 카운터 의 정합성 보정** 이다.

### Lambda 작성 규칙
- **언어**: Python (FastAPI 와 일관)
- **runtime**: `python3.12`
- **Memory**: 512MB 기본
- **Timeout**: 30s
- **환경변수**: DB URL, Redis URL 등 SSM Parameter Store 참조
- **공통 코드 공유**: Lambda Layer (DB 클라이언트, 도메인 모델)
- **로깅**: structlog → CloudWatch Logs

### 메시지 발행 (FastAPI 측)

API 가 SQS 로 발행할 일은 현재 없다. 모든 메시지는 **EventBridge → SQS → Lambda** 의 정기 cron 흐름이다. FastAPI 측에 `aioboto3` 기반 publisher 도 추가하지 않는다.

> 외부에서 트리거할 비동기 작업이 생기면 본 문서를 갱신하면서 publisher 도입.

### EventBridge

- **정기 cron 규칙 1개만** — `rate(5 minutes)` → `seat-release` queue
- **Custom event bus 도입 X**
- **타깃은 SQS 만** — 직접 EKS 호출 X

## Bastion

### 정책
- **EC2 t3.micro** — 최소 사양
- **Public subnet** + Elastic IP 고정
- **SSH 22 포트** — Source IP whitelist (회사 VPN / 개인 IP)
- **SSM Session Manager 우선** — SSH 보다 권장 (감사 로그 자동)
- **Pod 접근 시** — `kubectl` 설치, IAM Role 부여
- **운영자 수동 작업 전용** — 자동화 스크립트 실행 X

## CloudWatch

### 로그
- **EKS Pod stdout → Fluent Bit (DaemonSet) → CloudWatch Logs**
- **Log group 명명**: `/ticketing/eks/{namespace}/{pod_name}`
- **보존**: 30 일 (운영), 7 일 (dev)
- **Logs Insights 쿼리 저장** — 자주 쓰는 쿼리는 saved query 로

### 메트릭
- **인프라**: AWS 자동 (ALB, RDS, ElastiCache, SQS, Lambda)
- **애플리케이션**: EMF 포맷으로 stdout 출력 ([04-error-handling.md](04-error-handling.md))
- **K8s**: Container Insights (옵션)

### 알람
- Terraform `module/cloudwatch` 에서 일괄 정의
- SNS 토픽 → Slack webhook
- 알람 룰은 [04-error-handling.md](04-error-handling.md) 참조

## CI/CD

### 레포 분리

| 레포 | 역할 | 트리거 |
|---|---|---|
| **Infra GitHub** | Terraform 코드 | PR → `terraform plan` 코멘트, merge → 수동 apply |
| **Service GitHub** | FastAPI 애플리케이션 | PR → 테스트, merge → 이미지 빌드 → ECR push → EKS rollout |

### Service CI/CD (GitHub Actions)

```yaml
# .github/workflows/deploy.yml
name: deploy

on:
  push:
    branches: [main]

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      id-token: write   # OIDC for AWS
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<account>:role/github-actions
          aws-region: ap-northeast-2
      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr
      - name: 이미지 빌드 + push
        run: |
          docker build -t $REPO:${{ github.sha }} .
          docker push $REPO:${{ github.sha }}
        env:
          REPO: ${{ steps.ecr.outputs.registry }}/ticketing-api
      - name: kubeconfig
        run: aws eks update-kubeconfig --name ticketing-cluster
      - name: 매니페스트 갱신
        run: |
          cd deploy/overlays/prod
          kustomize edit set image ticketing-api=$REPO:${{ github.sha }}
          kubectl apply -k .
          kubectl rollout status deployment/ticketing-api --timeout=5m
```

### 규칙
- **OIDC 사용** — `AWS_ACCESS_KEY` 환경변수 금지 (장기 credential 노출)
- **이미지 태그는 commit SHA** — `latest` 금지 (rollback 불가)
- **`rollout status` 로 확인** — 배포 실패 시 CI 도 실패
- **dev 자동 배포 / prod 수동 승인** — GitHub Environment 의 required reviewer

### Dockerfile 표준

```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN pip install --no-deps -e .

COPY app ./app

# non-root 사용자
RUN useradd -u 10001 -m appuser
USER 10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--timeout-graceful-shutdown", "30"]
```

### Dockerfile 규칙
- **slim 베이스** — 풀 이미지 사용 X
- **non-root** — UID 10000+
- **multi-stage 빌드** — 의존성 설치와 런타임 분리 (필요 시)
- **`COPY` 순서 최적화** — 자주 변경되는 코드는 마지막
- **`EXPOSE` 명시** — 문서화 목적 (k8s 와 무관하지만)
- **단일 워커** — Pod 단위 스케일 (k8s 가 멀티 워커 역할)

## 보안

### IAM 원칙
- **Pod IAM Role** — IRSA (IAM Roles for Service Accounts) 로 부여
- **최소 권한** — `s3:GetObject` 하나면 `s3:*` 부여 금지
- **장기 credential 미사용** — Lambda/EKS 모두 IAM Role
- **MFA 필수** — root 계정, IAM 사용자 콘솔 로그인

### 네트워크
- **Private subnet 에서 외부** — NAT Gateway 경유
- **DB 보안 그룹** — EKS Pod SG 만 허용 (Bastion 은 별도 SG)
- **VPC Flow Logs** — CloudWatch Logs 로 저장

### 시크릿
- **DB password / JWT secret / 외부 API key** — Secrets Manager
- **EKS 에서 사용** — ExternalSecrets Operator 로 k8s Secret 으로 합성
- **`.env` 평문 commit 금지** — `.gitignore` 에 명시. `app/.env.example` 만 제공

## 비용 최적화

학습·실습 규모 가정.

| 영역 | 최적화 |
|---|---|
| EKS 노드 | 평시 최소 2 노드. HPA + Cluster Autoscaler 로 자동 스케일 |
| RDS reader | 평시 1대씩. 부하 측정 후 확장 |
| NAT Gateway | AZ 당 1개 → 비용 큼. dev 환경은 단일 AZ |
| CloudWatch Logs | 보존 기간 짧게. 로그 양 모니터링 |
| Lambda | Reserved concurrency 설정으로 폭주 방지 (비용 + DB 보호) |

## 안티 패턴

### 금지
- **Terraform state 로컬 보관** — S3 backend 필수
- **`terraform apply` 무인 실행** — 외부 영향, 사용자 확인 ([07-workflow.md](07-workflow.md))
- **하드코딩된 AWS 계정 ID / region** — variable
- **`latest` 태그 사용** — commit SHA 또는 semver
- **Secret 을 ConfigMap 에** — Secret 객체 사용
- **EKS root 컨테이너** — non-root 필수
- **Public subnet 에 RDS / ElastiCache** — Private subnet only
- **SG 0.0.0.0/0 inbound** — Bastion SSH 도 IP whitelist
- **단일 AZ 구성** (운영) — Multi-AZ 필수
- **Lambda 안에 SQS receive long-polling 무한 루프** — 이벤트 트리거 방식만 사용
