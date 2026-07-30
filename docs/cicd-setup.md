# CI/CD 파이프라인 (2026-07-30 구축)

## 요약

`main` 브랜치에 push하면 자동으로 Docker 이미지를 빌드해 ECR에 올리고,
EC2(`i-0b5c23a2287a72821`, `3.106.155.36`)에 배포합니다.

```
GitHub (main push)
  → GitHub Actions: docker build → ECR push (커밋 SHA 태그)
  → GitHub Actions: AWS SSM Send-Command로 EC2에 배포 스크립트 실행
  → EC2: docker pull → SSM Parameter Store에서 시크릿 주입 → 컨테이너 재기동
  → 헬스체크(HTTP 200) 통과 확인 후 종료
```

워크플로우 정의: `.github/workflows/deploy.yml`
배포 스크립트: `scripts/deploy.sh` (SSM으로 EC2에 전달되어 실행됨)

---

## 인증 방식: OIDC (장기 자격 증명 없음)

GitHub Actions는 AWS access key를 저장하지 않습니다. 대신:

1. AWS IAM에 OIDC ID 제공자 등록: `token.actions.githubusercontent.com`
2. IAM Role `github-actions-yuta-logagent` 생성, trust policy를 이 저장소의
   `main` 브랜치로만 제한:
   ```
   token.actions.githubusercontent.com:sub =
     repo:hrunj1230/yuta_logagent:ref:refs/heads/main
   ```
3. 이 Role에는 두 개의 inline policy만 부여:
   - `ecr-push-yuta-logagent`: `yuta-logagent` 리포지토리에 대한 push 권한만
   - `ssm-deploy-yuta-logagent`: 해당 EC2 인스턴스에 `ssm:SendCommand` +
     결과 조회 권한만

즉 GitHub Actions가 탈취되더라도 이 리포지토리 관련 리소스 밖으로 나갈 수
없고, 만료되지 않는 키가 어디에도 저장되어 있지 않습니다.

---

## 시크릿 관리: AWS SSM Parameter Store만 사용 (GitHub Secrets 아님)

API 키(`ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `LANGSMITH_*`)는
**AWS SSM Parameter Store**에 `SecureString`으로 저장되어 있습니다
(`/yuta-logagent/prod/*`). EC2 인스턴스 역할(`YutaLogAgentEC2Role`)이 이
경로만 읽을 수 있도록 스코프되어 있고, `scripts/deploy.sh`가 배포 시점에
이 값들을 읽어 `docker run -e`로 주입합니다.

**GitHub Actions 워크플로우는 이 키들을 전혀 참조하지 않습니다.**
빌드 단계는 소스 코드만 필요하고, 배포 단계는 SSM 명령을 "실행하라"는
지시만 내릴 뿐 키 값 자체를 보지 않습니다.

### ⚠️ 겪었던 실수 (주의사항)

초기 설계 단계에서 "EC2에 SSH로 접속해 `.env` 파일을 직접 심는 방식"을
먼저 시도하면서, 로컬 `.env`의 6개 키를 전부 GitHub Secrets에도
등록했습니다. 이후 이미 구성되어 있던 SSM Parameter Store 기반 설계를
발견하고 그쪽으로 방식을 바꿨는데, **GitHub Secrets에 넣어둔 6개를
정리하지 않고 그대로 방치**했습니다.

그 결과 한동안 같은 API 키가 두 곳(GitHub Secrets, SSM Parameter Store)에
중복 저장되어 있었고, 워크플로우는 그중 아무것도 실제로 쓰지 않는
"죽은 시크릿" 상태였습니다. 이런 상태가 위험한 이유:

- 키를 로테이션할 때 한쪽만 갱신하고 다른 쪽을 잊어버리기 쉬움
- 어디가 진짜 소스인지 헷갈려서 디버깅 시간 낭비
- 불필요하게 노출 지점(attack surface)이 하나 더 생김

**교훈: 시크릿의 진실 공급원(source of truth)은 하나로 유지하고, 설계를
바꿀 때는 이전 설계의 흔적(사용하지 않는 시크릿/변수/하드코딩된 값)을
반드시 같이 정리한다.** 실제로 이 문서를 쓰기 직전에 `EC2_HOST`,
`EC2_USER`(SSH 방식 때 계획했다가 SSM으로 바꾸며 안 쓰게 된 변수)와
워크플로우에 하드코딩되어 있던 인스턴스 ID도 같은 이유로 같이 정리했습니다.

---

## GitHub Secrets / Variables 최종 상태

**Secrets** (민감, 값 비공개):
| 이름 | 용도 |
|---|---|
| `AWS_ROLE_ARN` | GitHub Actions가 assume할 IAM Role ARN |

**Variables** (비민감, 값 공개):
| 이름 | 값 |
|---|---|
| `AWS_REGION` | `ap-southeast-2` |
| `ECR_REPOSITORY` | `yuta-logagent` |
| `EC2_INSTANCE_ID` | `i-0b5c23a2287a72821` |

API 키 관련 시크릿은 GitHub에 **하나도 없습니다.** 전부 AWS SSM Parameter
Store가 유일한 소스입니다.

---

## 배포 방식: SSH가 아니라 SSM Run Command

EC2에 SSH 키를 GitHub Secret으로 넣는 대신, `aws ssm send-command`로
EC2에 이미 설치된 SSM Agent를 통해 배포 스크립트를 실행합니다.

장점:
- SSH 개인키를 GitHub 어디에도 저장할 필요 없음
- 22번 포트를 열어둘 필요도 없어짐 (지금은 편의상 열려있지만, 배포
  파이프라인 관점에서는 더 이상 의존하지 않음)
- 실행 결과(stdout/stderr, 종료 코드)가 AWS 쪽에 감사 로그로 남음
- 이미 `YutaLogAgentEC2Role`에 `AmazonSSMManagedInstanceCore`가 붙어있어
  추가 설정 없이 바로 사용 가능했음

---

## 겪었던 버그와 수정 (참고용 트러블슈팅 기록)

1차 실행 시 배포 자체는 성공했지만 파이프라인은 "실패"로 표시됐습니다.
원인 2가지를 순서대로 발견하고 고쳤습니다.

1. **헬스체크가 너무 일찍 실행됨**: `docker run` 5초 뒤 바로 curl로
   확인했는데, 컨테이너가 HuggingFace 임베딩 모델을 로딩하는 데 그보다
   오래 걸려 연결이 끊겼고, 스크립트 상단의 `set -e` 때문에 그 실패로
   전체 배포 스크립트가 죽은 것으로 처리됨.
   → 최대 2분간 5초 간격으로 재시도하도록 수정.

2. **ECR 리포지토리가 태그 불변(IMMUTABLE)**: 매 빌드마다 `:latest`
   태그도 같이 push하도록 했는데, 두 번째 빌드부터 "이미 존재하는 태그는
   덮어쓸 수 없다"는 에러로 실패. 애초에 배포 스크립트는 커밋 SHA
   태그만 사용하므로 `:latest` 자체가 불필요했음.
   → `:latest` push를 워크플로우에서 제거.

3. **데이터 영속성 부재**: 기존 수동 배포(`docker run`)는 볼륨 마운트가
   전혀 없어 컨테이너를 내릴 때마다 `users.db`/`chroma_db`/`data`가
   초기화되는 상태였음. 이번에 `/home/ec2-user/yuta-logagent-data/`
   아래로 영구 마운트를 추가해 재배포해도 데이터가 유지되도록 개선.

4. **디스크 공간 고갈로 배포 실패**: 매 배포마다 커밋 SHA로 새 이미지
   (약 5.6GB, torch/sentence-transformers 포함)를 pull하는데,
   `docker image prune -f`는 dangling(태그 없는) 이미지만 지워서 이전
   커밋 태그의 이미지들이 계속 쌓였음. 5번째 배포 만에 30GB 디스크가
   가득 차 `no space left on device`로 실패. `docker image prune -af`
   (태그된 것도 포함해 미사용 이미지 전부 삭제)로 변경하고, 헬스체크
   통과 직후에 실행하도록 위치를 옮겨서 배포 실패 시엔 롤백용으로
   이전 이미지가 남아있게 함.
   → **교훈: 매번 새 태그로 이미지를 pull하는 파이프라인은 이미지
   정리 로직이 필수다.** 로컬 테스트 몇 번으로는 안 드러나고, 실제
   운영하면서 배포 횟수가 쌓여야 터지는 종류의 문제라 더 놓치기 쉽다.

---

## 최신 프랙티스 대비 평가

### 잘 맞는 부분
- **OIDC 기반 인증**은 2024~2026년 기준 GitHub Actions ↔ AWS 연동의
  표준 권장 방식입니다. 장기 액세스 키를 CI에 저장하는 구식 방식보다
  명확히 우위이고, 이 부분은 그대로 유지해도 됩니다.
- **최소 권한 IAM Role** (ECR push + 특정 인스턴스에 대한 SSM만): 리포지토리/브랜치 단위로 trust policy를 좁힌 것도 적절합니다.
- **SecureString 기반 Parameter Store**: 소규모 프로젝트에서 시크릿을
  코드/이미지 밖에 두고 런타임 주입하는 패턴 자체는 표준적입니다.
- **불변 이미지 태그(커밋 SHA)**: `latest`에 의존하지 않고 SHA로
  배포 대상을 명시하는 것은 재현성·롤백 측면에서 권장되는 방식입니다.

### 아쉬운 부분 / 개선하면 좋을 점
1. **단일 인스턴스, 무중단 배포 아님**: `docker rm -f` 후 `docker run`
   방식이라, pull~기동 사이 짧은 다운타임이 발생합니다. 트래픽이
   늘면 blue-green이나 최소 ALB + 헬스체크 기반 롤링 배포를 고려할
   시점입니다. 지금 규모(개인 프로젝트)에서는 과설계일 수 있어 당장
   급하지는 않습니다.
2. **롤백 절차 없음**: 배포가 "성공"으로 끝나도 앱이 실제로 오작동하면
   되돌릴 자동화된 방법이 없습니다. 이전 성공 이미지 태그를 기록해두고
   `scripts/rollback.sh` 같은 걸 만들어두면 좋습니다.
3. **Parameter Store vs Secrets Manager**: 지금 방식(Parameter Store
   SecureString)도 충분히 표준적이지만, 자동 로테이션이 필요해지면
   Secrets Manager가 더 적합합니다. 현재 규모에선 Parameter Store가
   비용/복잡도 면에서 합리적인 선택입니다.
4. **CI에 테스트 단계 없음**: 지금 워크플로우는 빌드→배포만 하고 자동
   테스트(`pytest`)를 안 돌립니다. 리포지토리에 `tests/`가 이미 있으니,
   `build-and-push` 이전에 테스트 job을 추가해 실패 시 배포를 막는 게
   다음으로 손볼 만한 부분입니다.
5. **모니터링/알림 부재**: 배포 실패 시 GitHub Actions 화면을 직접
   봐야 압니다. Slack/이메일 알림 연동을 추가하면 무인 운영에 가까워
   집니다.
6. **디스크 사용량 모니터링 없음**: 기본 CloudWatch 지표는 메모리와
   마찬가지로 디스크 사용량도 포함하지 않아, 이번 "no space left on
   device" 장애도 사후에야 발견했습니다. CloudWatch Agent로 디스크
   사용률 알람을 걸어두면 다음번엔 배포가 실패하기 전에 미리 알 수
   있습니다.
7. **저장소 자체의 보안 이슈(CI/CD와 별개, 미해결)**: 저장소가
   Public이고 과거 커밋에 `users.db`가 남아있는 문제는 CI/CD 구성과
   무관하게 여전히 열려 있습니다.

### 종합 의견
인증·시크릿 관리의 핵심 뼈대(OIDC, 최소 권한, Parameter Store, 불변
태그)는 개인/소규모 프로젝트 기준으로 이미 업계 권장 수준입니다.
지금 당장 더 손볼 필요는 없고, 트래픽이나 협업 인원이 늘어날 때
1번(무중단 배포)과 4번(CI 테스트 게이트)부터 순서대로 추가하는 걸
추천합니다.
