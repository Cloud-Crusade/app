# proto

서비스 간 gRPC 계약의 단일 진실원. 패키지는 `ccproto.<service>.v<n>` 규칙을 따른다
(공통 네임스페이스 `ccproto` 로 생성 스텁의 import 충돌 회피).

```
proto/
  ccproto/
    auth/v1/         # 인증 서비스
    event/v1/        # 행사 관리 서비스
    reservation/v1/  # 예약 관리 서비스
    payment/v1/      # 결제 관리 서비스
```

## 스텁 생성

```bash
buf generate          # libs/protos 에 생성 (cc-protos 패키지로 커밋)
```

## 검증

```bash
buf lint              # 스타일/구조 검증
buf breaking --against '.git#branch=main'   # 이전 버전 대비 호환성 깨짐 검출
```

설정은 레포 루트의 `buf.yaml`(모듈/lint/breaking), `buf.gen.yaml`(생성 플러그인) 참조.
