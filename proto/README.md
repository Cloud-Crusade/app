# proto

서비스 간 gRPC 계약의 단일 진실원. 패키지는 `<service>.v<n>` 규칙을 따른다.

```
proto/
  auth/v1/         # 인증 서비스
  event/v1/        # 행사 관리 서비스
  reservation/v1/  # 예약 관리 서비스
  payment/v1/      # 결제 관리 서비스
```

## 스텁 생성

```bash
buf generate          # gen/python/ 에 생성 (gitignore 대상)
```

## 검증

```bash
buf lint              # 스타일/구조 검증
buf breaking --against '.git#branch=main'   # 이전 버전 대비 호환성 깨짐 검출
```

설정은 레포 루트의 `buf.yaml`(모듈/lint/breaking), `buf.gen.yaml`(생성 플러그인) 참조.
