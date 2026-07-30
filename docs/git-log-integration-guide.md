# Git 로그 통합 가이드

**목적:** Git 커밋 히스토리를 일지에 자동으로 포함시키기

---

## 📋 현재 지원 기능

### SourceType 종류

| 타입 | 설명 | 수집 데이터 |
|------|------|------------|
| **GIT** | Git 저장소 전체 파일 | 모든 텍스트 파일 (.md, .py 등) |
| **GIT_LOG** | Git 커밋 히스토리 | 커밋 SHA, 작성자, 날짜, 메시지 |
| **LOCAL** | 로컬 디렉토리 | 로컬 파일들 |

---

## 🚀 빠른 시작

### 1. Git 저장소 URL 가져오기

**현재 프로젝트 (yuta_logagent):**
```bash
git remote get-url origin
# 결과: https://github.com/hrunj1230/yuta_logagent.git
```

**다른 저장소:**
- GitHub에서 "Code" 버튼 클릭
- HTTPS URL 복사
- 예: `https://github.com/username/repository.git`

---

### 2. 챗봇으로 추가

**user_page의 AI 어시스턴트에서:**

#### 옵션 A: Git 로그만 (커밋 메시지)
```
"https://github.com/hrunj1230/yuta_logagent.git을 git_log 타입으로 추가해줘"
```

**수집되는 정보:**
- ✅ 커밋 메시지
- ✅ 작성자
- ✅ 날짜
- ❌ 코드 변경사항 (diff)

#### 옵션 B: 전체 파일 + 로그 (모든 것)
```
1. "https://github.com/hrunj1230/yuta_logagent.git을 git 타입으로 추가해줘"
2. "https://github.com/hrunj1230/yuta_logagent.git을 git_log 타입으로 추가해줘"
```

**수집되는 정보:**
- ✅ 모든 소스 코드 파일
- ✅ 커밋 메시지
- ✅ 작성자, 날짜
- ✅ 파일 전체 내용 (코드 전문)

---

### 3. 임베딩 자동 실행

AI 어시스턴트가 자동으로 다음을 수행합니다:
1. Git 저장소 clone
2. 커밋 로그 수집
3. ChromaDB에 임베딩
4. 일지 작성 시 자동으로 검색 가능

---

## 📝 일지 작성 시 활용

### 일지 작성 요청

```
"2026년 7월 28일 일지 작성해줘"
```

**AI가 자동으로:**
1. ChromaDB에서 7월 28일 관련 데이터 검색
   - TIL 파일 (Today I Learn/2026_07_28.md)
   - Git 커밋 로그 (7월 28일에 작성한 커밋들)
2. 검색된 정보를 바탕으로 일지 작성
3. `logs/2026.07.28_log.md` 파일로 저장

**생성되는 일지 예시:**
```markdown
# 2026년 7월 28일 개발 일지

## 오늘의 학습
- MCP Context Isolation 개념 학습
- FastAPI 프로젝트 구조 개선

## 오늘의 작업
- fix: Gemini에서 Anthropic Claude로 전환 (쿼터 한도 문제 해결)
  - 커밋: ab18a51
  - 작성자: hrunj1230

- feat: 데이터베이스 리셋 스크립트 추가
  - 커밋: 3fe47f4
  - 스키마 업데이트 시 편리하게 사용

## 내일 할 일
- Docker 배포 테스트
- 프로덕션 환경 구성
```

---

## 🔍 현재 구현 상세

### Git 로그 수집 코드 (src/tools/embedding.py:190-244)

```python
def _collect_git_log(source: Source, user_id: str) -> list[Document]:
    """Git 커밋 히스토리 수집 (message + author + date)"""

    # Git log 가져오기
    result = subprocess.run(
        ["git", "-C", str(repo_dir), "log",
         "--pretty=format:%H|%an|%ad|%s", "--date=iso"],
        capture_output=True, text=True
    )

    # 각 커밋을 Document로 변환
    for line in result.stdout.strip().split("\n"):
        sha, author, date, message = line.split("|", 3)

        content = f"Commit: {message}\nAuthor: {author}\nDate: {date}"

        doc = Document(
            page_content=content,
            metadata={
                "commit_sha": sha,
                "author": author,
                "date": date,
                "message": message,
                ...
            }
        )
```

**수집 형식:**
```
git log --pretty=format:%H|%an|%ad|%s --date=iso

결과:
ab18a51|hrunj1230|2026-07-28 18:32:15 +0900|fix: switch from Gemini to...
3fe47f4|hrunj1230|2026-07-28 18:43:52 +0900|feat: add database reset...
```

---

## 🎯 개선 아이디어: 코드 Diff 포함

### 현재 제한사항
- 커밋 메시지만 수집
- 실제 코드 변경사항(diff)은 미포함

### 개선안: GIT_DIFF 타입 추가

**새로운 소스 타입:**
```python
class SourceType(str, enum.Enum):
    GIT = "git"
    GIT_LOG = "git_log"
    GIT_DIFF = "git_diff"  # 신규
    LOCAL = "local"
    ...
```

**수집할 정보:**
```bash
git log -p --since="2026-07-28" --until="2026-07-29"

결과:
commit ab18a51
Author: hrunj1230
Date: 2026-07-28 18:32:15 +0900

    fix: switch from Gemini to Anthropic Claude

diff --git a/src/llm_router.py b/src/llm_router.py
@@ -5,7 +5,7 @@
-from langchain_google_genai import ChatGoogleGenerativeAI
+from langchain_anthropic import ChatAnthropic

-llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash-exp")
+llm = ChatAnthropic(model="claude-sonnet-4-5")
```

**장점:**
- 실제 코드 변경사항 확인 가능
- 더 상세한 일지 작성

**단점:**
- 임베딩 용량 증가
- API 비용 증가

---

## 📊 사용 시나리오

### 시나리오 1: 개인 개발 일지

**목표:** 매일 작성한 코드를 자동으로 일지에 포함

**설정:**
```
1. 개발 저장소 추가 (GIT_LOG)
   "https://github.com/hrunj1230/yuta_logagent.git을 git_log로 추가해줘"

2. TIL 저장소 추가 (GIT - 이미 추가됨)
   ✅ Yuta_TIL 등록 완료

3. 일지 요청
   "오늘 일지 작성해줘"
```

**결과:**
- TIL에 작성한 학습 내용
- 프로젝트에 커밋한 작업 내용
- 자동으로 통합되어 일지 생성

---

### 시나리오 2: 팀 프로젝트 추적

**목표:** 팀원들의 커밋도 함께 추적

**설정:**
```
"https://github.com/team/project.git을 git_log로 추가해줘"
```

**활용:**
```
"이번 주 우리 팀이 뭘 했는지 정리해줘"
```

**결과:**
- 팀원별 커밋 내역
- 주요 기능 개발 사항
- 버그 수정 내역

---

### 시나리오 3: 여러 프로젝트 동시 관리

**설정:**
```
1. "https://github.com/user/project-a.git을 git_log로 추가해줘"
2. "https://github.com/user/project-b.git을 git_log로 추가해줘"
3. "https://github.com/user/til.git을 git로 추가해줘"
```

**활용:**
```
"7월 28일에 내가 모든 프로젝트에서 한 일 정리해줘"
```

---

## ⚙️ 고급 설정

### 1. 날짜 범위 필터링

현재는 전체 커밋 히스토리를 수집합니다.

**개선안:**
```python
# 최근 30일만 수집
git log --since="30 days ago" --pretty=format:...
```

### 2. 특정 브랜치만

```python
# main 브랜치만
git log main --pretty=format:...

# 모든 브랜치
git log --all --pretty=format:...
```

### 3. 작성자 필터

```python
# 본인 커밋만
git log --author="hrunj1230" --pretty=format:...
```

---

## 🔧 트러블슈팅

### Q1: "소스를 찾을 수 없습니다" 오류

**원인:** Git 저장소가 private일 경우 접근 권한 필요

**해결:**
```
1. Public 저장소 사용
2. 또는 로컬 클론된 경로 사용:
   "로컬 경로 /Users/hrun/Documents/project를 local로 추가해줘"
```

### Q2: "임베딩 실패" 오류

**원인:** Git clone 실패

**해결:**
```bash
# 수동으로 먼저 clone 테스트
cd data/sources/hrunj1230
git clone https://github.com/user/repo.git
```

### Q3: 일지에 커밋 정보가 안 나옴

**원인:**
- ChromaDB 검색 실패
- 날짜 메타데이터 불일치

**해결:**
```
1. 임베딩 상태 확인:
   "소스 목록 보여줘"

2. 재임베딩:
   "1번 소스 임베딩 다시 해줘"
```

---

## 📈 향후 개선 계획

### 1. Git Diff 지원 (코드 변경사항)
```python
# 새로운 타입: GIT_DIFF
- 실제 코드 변경 내용 포함
- diff 통계 (추가/삭제 라인 수)
```

### 2. Issue & PR 연동
```python
# GitHub API 활용
- 연결된 이슈 정보
- PR 리뷰 코멘트
```

### 3. 커밋 분류
```python
# Conventional Commits 파싱
- feat: 새 기능
- fix: 버그 수정
- docs: 문서 작업
- refactor: 리팩토링
```

---

## 💡 베스트 프랙티스

### 1. 저장소 분리
```
✅ 추천:
- TIL 저장소: GIT 타입 (학습 내용)
- 프로젝트 저장소: GIT_LOG 타입 (작업 내역)

❌ 비추천:
- 모든 저장소를 GIT 타입으로 (임베딩 용량 폭증)
```

### 2. 정기 동기화
```
매일 아침:
"모든 소스 동기화해줘"

주말:
"이번 주 일지 정리해줘"
```

### 3. 커밋 메시지 규칙
```
명확한 커밋 메시지 작성 → 더 나은 일지 생성

좋은 예:
✅ "feat: add Docker deployment configuration"
✅ "fix: resolve ChromaDB collection name issue"

나쁜 예:
❌ "update"
❌ "fix bug"
```

---

## 🎯 실전 예제

### 전체 플로우

**1단계: 저장소 추가**
```
챗봇: "https://github.com/hrunj1230/yuta_logagent.git을 git_log로 추가해줘"
AI: "✅ 임베딩 완료: yuta_logagent
      - 처리된 파일: 0개 (git_log는 커밋만)
      - 생성된 청크: 47개
      - 커밋 개수: 47개"
```

**2단계: 일지 요청**
```
챗봇: "7월 28일 일지 작성해줘"
AI: "retriever_vectordb로 검색 중..."
    → TIL/2026_07_28.md 발견
    → Git 커밋 3개 발견

    "maker_logfile로 저장 중..."
    → logs/2026.07.28_log.md 생성
```

**3단계: 결과 확인**
```
logs/2026.07.28_log.md:
# 2026년 7월 28일 개발 일지

## 학습 내용
- Anthropic Claude API 사용법
- Docker 멀티스테이지 빌드

## 작업 내용
### yuta_logagent 프로젝트
- fix: Gemini → Claude 전환 (ab18a51)
- feat: DB 리셋 스크립트 추가 (3fe47f4)
- docs: 구현 가이드 문서 작성 (7d0c98c)

## 회고
...
```

---

## 📚 참고

- Git 로그 수집 코드: `src/tools/embedding.py:190-244`
- 소스 타입 정의: `src/storage/models.py:10-15`
- 일지 작성 도구: `src/tools/log.py`

---

**작성일:** 2026-07-29
**프로젝트:** yuta_logagent
