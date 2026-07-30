# Git 소스 타입 자동 판단 가이드

**문제:** Git URL만으로는 이것이 TIL/메모용(GIT)인지 작업 로그용(GIT_LOG)인지 구분하기 어렵다

**목표:** 사용자 편의성을 높이면서도 정확한 타입 판단

---

## 📊 비교: GIT vs GIT_LOG

| 특성 | GIT (파일 저장소) | GIT_LOG (커밋 히스토리) |
|------|------------------|----------------------|
| **용도** | TIL, 메모, 문서 저장소 | 프로젝트 작업 히스토리 |
| **수집 대상** | 모든 텍스트 파일 (.md, .py 등) | 커밋 메시지, 작성자, 날짜 |
| **임베딩 크기** | 큼 (파일 수에 비례) | 작음 (커밋 수에 비례) |
| **예시 저장소** | `Yuta_TIL`, `blog`, `notes` | `yuta_logagent`, `project-x` |
| **파일 특징** | .md 파일 많음 | .py, .js 등 코드 파일 많음 |

---

## 🎯 전략 비교

### 전략 1: 명시적 사용자 입력 (현재 방식)

**동작:**
```
사용자: "https://github.com/user/repo.git 추가해줘"
AI: "이 저장소를 어떤 타입으로 추가하시겠습니까?"
     - git: 파일 저장소
     - git_log: 커밋 로그
```

**장점:**
- ✅ 가장 정확함
- ✅ 사용자가 의도를 명확히 전달

**단점:**
- ❌ 매번 물어봐야 함
- ❌ 사용자 경험 저하

**현재 구현:**
```python
# src/tools/source.py:175-199
@tool
def request_source_type_clarification() -> str:
    return """🤔 소스 타입을 명확히 지정해주세요:
    **git** - Git 저장소를 clone하고 파일을 임베딩
    **git_log** - Git 커밋 히스토리를 임베딩
    ..."""
```

---

### 전략 2: 저장소 이름 패턴 분석 (간단)

**휴리스틱 규칙:**

```python
def detect_source_type_by_name(repo_url: str) -> str:
    """저장소 이름으로 타입 추론"""
    repo_name = repo_url.split('/')[-1].replace('.git', '').lower()

    # TIL/메모 저장소 키워드
    til_keywords = ['til', 'blog', 'notes', 'memo', 'diary', 'journal',
                    'wiki', 'docs', 'learning', 'study']

    # 프로젝트 저장소 키워드
    project_keywords = ['project', 'app', 'service', 'api', 'backend',
                       'frontend', 'web', 'bot', 'agent', 'server']

    if any(keyword in repo_name for keyword in til_keywords):
        return "git"  # 파일 저장소

    if any(keyword in repo_name for keyword in project_keywords):
        return "git_log"  # 커밋 로그

    return "unknown"  # 판단 불가
```

**예시:**
```
✅ Yuta_TIL           → git
✅ my-notes          → git
✅ yuta_logagent     → git_log
✅ project-backend   → git_log
❌ awesome-repo      → unknown (사용자에게 물어봄)
```

**장점:**
- ✅ 빠른 판단
- ✅ 추가 API 호출 불필요

**단점:**
- ❌ 이름만으로는 부정확
- ❌ 예외 케이스 많음

---

### 전략 3: 저장소 내용 분석 (정확)

**동작:**
1. 저장소를 shallow clone (최근 커밋만)
2. 파일 구조 분석
3. 타입 자동 판단

```python
def detect_source_type_by_content(repo_url: str) -> str:
    """저장소 내용 분석으로 타입 추론"""
    import subprocess
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp_dir:
        # Shallow clone (빠른 분석)
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, tmp_dir],
            capture_output=True
        )

        # 파일 통계
        md_files = list(Path(tmp_dir).rglob("*.md"))
        code_files = list(Path(tmp_dir).rglob("*.py")) + \
                    list(Path(tmp_dir).rglob("*.js")) + \
                    list(Path(tmp_dir).rglob("*.java"))

        total_files = len(md_files) + len(code_files)

        if total_files == 0:
            return "unknown"

        md_ratio = len(md_files) / total_files

        # 판단 기준: .md 파일이 70% 이상이면 TIL
        if md_ratio >= 0.7:
            return "git"  # 문서/메모 저장소
        elif md_ratio < 0.3:
            return "git_log"  # 코드 프로젝트
        else:
            return "unknown"  # 혼합형
```

**예시 분석:**
```
Yuta_TIL:
  - .md 파일: 50개
  - .py 파일: 2개
  - 비율: 96% → git ✅

yuta_logagent:
  - .md 파일: 5개
  - .py 파일: 15개
  - 비율: 25% → git_log ✅
```

**장점:**
- ✅ 매우 정확함
- ✅ 파일 구조 기반 판단

**단점:**
- ❌ clone 시간 소요
- ❌ 네트워크 비용

---

### 전략 4: LLM 기반 판단 (똑똑함)

**동작:**
1. 저장소 메타데이터 수집 (README, 설명)
2. LLM에게 판단 요청

```python
def detect_source_type_by_llm(repo_url: str, llm) -> str:
    """LLM이 저장소 정보를 보고 판단"""

    # GitHub API로 저장소 정보 가져오기
    repo_info = get_github_repo_info(repo_url)

    prompt = f"""
    다음 Git 저장소의 용도를 판단하세요:

    이름: {repo_info['name']}
    설명: {repo_info['description']}
    주요 언어: {repo_info['language']}
    README 첫 문단: {repo_info['readme_preview']}

    이 저장소가 다음 중 어디에 해당하는지 판단:
    1. "TIL/메모/블로그" - 학습 내용, 문서, 메모를 저장하는 저장소
    2. "프로젝트" - 실제 개발 프로젝트, 애플리케이션 코드

    답변은 "TIL" 또는 "프로젝트"로만 응답하세요.
    """

    result = llm.invoke(prompt).content.strip()

    return "git" if "TIL" in result else "git_log"
```

**예시:**
```
저장소: hrunj1230/Yuta_TIL
설명: "Today I Learned - 매일 학습한 내용 정리"
주요 언어: Markdown
README: "# Yuta의 학습 기록 저장소..."

LLM 판단: "TIL" → git ✅
```

**장점:**
- ✅ 컨텍스트 이해
- ✅ 설명/README 활용

**단점:**
- ❌ API 비용
- ❌ 응답 시간

---

### 전략 5: 하이브리드 (추천 ⭐)

**단계별 판단:**

```python
def detect_source_type_smart(repo_url: str) -> dict:
    """
    다단계 자동 판단 + 사용자 확인

    Returns:
        {
            "type": "git" | "git_log" | "both" | "ask_user",
            "confidence": 0.0 ~ 1.0,
            "reason": "판단 이유"
        }
    """

    # 1단계: 이름 패턴 검사 (0.1초)
    name_result = detect_by_name(repo_url)
    if name_result['confidence'] >= 0.9:
        return name_result

    # 2단계: 간단한 메타데이터 검사 (0.5초)
    #   - GitHub API로 언어, 설명 확인
    metadata_result = detect_by_metadata(repo_url)
    if metadata_result['confidence'] >= 0.8:
        return metadata_result

    # 3단계: 사용자에게 추천하며 확인 요청
    return {
        "type": "ask_user",
        "confidence": 0.5,
        "suggestion": metadata_result['type'],  # 추천
        "reason": "명확한 판단이 어렵습니다. 추천 타입을 선택하거나 수정해주세요."
    }
```

**사용자 경험:**

```
사용자: "https://github.com/user/my-repo.git 추가해줘"

AI (자동 판단 성공):
  "✅ 저장소를 분석했습니다.
   이름과 설명을 보니 학습 저장소로 보입니다.
   GIT 타입으로 추가하고 파일을 임베딩하겠습니다.

   (다른 타입으로 추가하려면 'git_log 타입으로' 라고 말씀해주세요)"

또는

AI (확신 부족):
  "🤔 저장소를 분석했습니다.
   추천: git_log (코드 프로젝트로 보임)

   이대로 추가할까요? 아니면 다른 타입으로 변경하시겠어요?
   - git: 파일 저장소
   - git_log: 커밋 로그만"
```

**장점:**
- ✅ 대부분 자동 처리
- ✅ 불확실할 때만 사용자 확인
- ✅ 점진적 분석 (비용 최소화)

**단점:**
- ❌ 구현 복잡도 높음

---

## 🎯 실전 전략: 양쪽 모두 추가 (가장 안전)

**새로운 접근: 둘 다 추가, 사용자가 선택**

```python
@tool
def add_git_source_auto(user_id: str, location: str) -> str:
    """
    Git 저장소를 자동으로 분석하여 적절한 타입(들)으로 추가

    Args:
        user_id: 사용자 ID
        location: Git 저장소 URL

    Returns:
        추가 결과 메시지
    """
    # 저장소 이름 추출
    repo_name = location.split('/')[-1].replace('.git', '')

    # 간단한 패턴 분석
    confidence = analyze_repo_name(location)

    if confidence['type'] == 'til' and confidence['score'] > 0.8:
        # 확실히 TIL → GIT만
        return add_source_to_db(user_id, repo_name, "git", location)

    elif confidence['type'] == 'project' and confidence['score'] > 0.8:
        # 확실히 프로젝트 → GIT_LOG만
        return add_source_to_db(user_id, repo_name, "git_log", location)

    else:
        # 불확실 → 둘 다 추가
        result1 = add_source_to_db(user_id, f"{repo_name}_files", "git", location)
        result2 = add_source_to_db(user_id, f"{repo_name}_commits", "git_log", location)

        return f"""✅ 저장소를 두 가지 타입으로 모두 추가했습니다:

1. {repo_name}_files (GIT) - 파일 저장소
   - 모든 .md, .py 등 텍스트 파일 임베딩

2. {repo_name}_commits (GIT_LOG) - 커밋 히스토리
   - 커밋 메시지, 작성자, 날짜 임베딩

필요 없는 타입은 삭제해주세요:
"1번 소스 삭제해줘" 또는 "2번 소스 삭제해줘"
"""
```

**사용자 경험:**
```
사용자: "https://github.com/user/repo.git 추가해줘"

AI: "✅ 저장소를 두 가지 타입으로 추가했습니다:
     1. repo_files (파일 저장소)
     2. repo_commits (커밋 로그)

     모두 임베딩을 시작하겠습니다.
     필요 없는 것은 나중에 삭제하시면 됩니다."

사용자: "2번만 남기고 1번 삭제해줘"

AI: "✅ repo_files를 삭제했습니다."
```

**장점:**
- ✅ 판단 오류 없음
- ✅ 사용자가 나중에 선택
- ✅ 양쪽 다 필요한 경우도 커버

**단점:**
- ❌ 중복 임베딩 (비용)
- ❌ 관리할 소스 증가

---

## 📊 전략별 비교표

| 전략 | 정확도 | 속도 | 사용자 편의 | 구현 난이도 | 비용 |
|------|--------|------|------------|------------|------|
| 1. 명시적 입력 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐ | 무료 |
| 2. 이름 패턴 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | 무료 |
| 3. 내용 분석 | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | Git clone |
| 4. LLM 판단 | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | API 비용 |
| 5. 하이브리드 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 조건부 |
| 6. 둘 다 추가 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | 임베딩 2배 |

---

## 🎯 최종 추천

### 단기 개선 (빠른 구현)

**전략 6 (둘 다 추가) + 전략 2 (이름 패턴)**

```python
def add_git_source_smart(user_id: str, location: str) -> str:
    """스마트 Git 소스 추가"""
    repo_name = extract_repo_name(location)

    # 1단계: 이름으로 빠른 판단
    detected_type = detect_by_name(location)

    if detected_type['confidence'] > 0.85:
        # 확신 있음 → 해당 타입만 추가
        return add_source_to_db(
            user_id, repo_name, detected_type['type'], location
        ) + f"\n\n💡 다른 타입으로도 추가하려면 '{detected_type['alternative']} 타입으로 추가해줘'라고 말씀해주세요."

    else:
        # 확신 없음 → 둘 다 추가
        return add_both_types(user_id, repo_name, location)
```

**구현 시간:** 1-2시간
**효과:** 80% 케이스 자동 처리

---

### 중기 개선 (최적 UX)

**전략 5 (하이브리드)**

1. 이름 패턴 분석 (즉시)
2. GitHub API 메타데이터 (0.5초)
3. 확신 없으면 사용자에게 추천과 함께 확인

**구현 시간:** 1일
**효과:** 95% 케이스 자동 처리

---

## 💻 구현 예시 (권장)

### 1. 이름 패턴 검사 함수

```python
# src/tools/source_detector.py (신규 파일)

def detect_source_type_by_name(repo_url: str) -> dict:
    """
    저장소 이름으로 타입 추론

    Returns:
        {
            "type": "git" | "git_log",
            "confidence": 0.0 ~ 1.0,
            "reason": str
        }
    """
    repo_name = repo_url.split('/')[-1].replace('.git', '').lower()

    # TIL/학습 키워드
    til_keywords = {
        'til': 0.95, 'blog': 0.9, 'notes': 0.9, 'memo': 0.85,
        'diary': 0.85, 'journal': 0.85, 'wiki': 0.8, 'docs': 0.7,
        'learning': 0.85, 'study': 0.85
    }

    # 프로젝트 키워드
    project_keywords = {
        'project': 0.8, 'app': 0.8, 'service': 0.85, 'api': 0.85,
        'backend': 0.9, 'frontend': 0.9, 'web': 0.7, 'bot': 0.85,
        'agent': 0.85, 'server': 0.85, 'client': 0.8
    }

    # TIL 검사
    for keyword, score in til_keywords.items():
        if keyword in repo_name:
            return {
                "type": "git",
                "confidence": score,
                "reason": f"저장소 이름에 '{keyword}'가 포함되어 학습/메모 저장소로 판단"
            }

    # 프로젝트 검사
    for keyword, score in project_keywords.items():
        if keyword in repo_name:
            return {
                "type": "git_log",
                "confidence": score,
                "reason": f"저장소 이름에 '{keyword}'가 포함되어 프로젝트로 판단"
            }

    # 판단 불가
    return {
        "type": "git",  # 기본값
        "confidence": 0.5,
        "reason": "명확한 판단 키워드가 없어 기본값(git) 사용"
    }
```

### 2. 스마트 추가 도구

```python
# src/tools/source.py

@tool
def add_git_source_smart(user_id: str, location: str, name: str = None) -> str:
    """
    Git 저장소를 자동으로 분석하여 적절한 타입으로 추가합니다.

    Args:
        user_id: 사용자 ID
        location: Git 저장소 URL
        name: 소스 이름 (선택, 미지정 시 저장소 이름 사용)

    Returns:
        추가 결과 메시지
    """
    from .source_detector import detect_source_type_by_name

    # 저장소 이름 추출
    if not name:
        name = location.split('/')[-1].replace('.git', '')

    # 타입 자동 감지
    detection = detect_source_type_by_name(location)

    if detection['confidence'] >= 0.85:
        # 확신 있음 → 감지된 타입으로 추가
        result = add_source_to_db(user_id, name, detection['type'], location)

        alternative = "git_log" if detection['type'] == "git" else "git"

        return f"""{result}

💡 판단 근거: {detection['reason']}

다른 타입({alternative})으로도 추가하려면:
"{name}을 {alternative} 타입으로 추가해줘" 라고 말씀해주세요."""

    else:
        # 확신 없음 → 둘 다 추가
        result1 = add_source_to_db(user_id, f"{name}_files", "git", location)
        result2 = add_source_to_db(user_id, f"{name}_commits", "git_log", location)

        return f"""🤔 저장소 타입을 명확히 판단하기 어려워 두 가지 모두 추가했습니다:

{result1}

{result2}

필요 없는 타입은 삭제해주세요:
"소스 목록 보여줘" → ID 확인 → "X번 소스 삭제해줘"
"""
```

---

## 🔄 마이그레이션 전략

### 기존 코드 유지하면서 개선

```python
# src/unified_controller_single.py

# 기존 도구 유지
unified_tools = [
    source_tools.add_source_to_db,        # 명시적 타입 지정
    source_tools.add_git_source_smart,    # 🆕 스마트 자동 감지
    source_tools.get_user_sources,
    ...
]

# 시스템 메시지 업데이트
system_message = f"""...
소스 추가 방법:
1. 타입을 명확히 알 때: add_source_to_db 사용
2. 타입을 모를 때: add_git_source_smart 사용 (자동 감지)
..."""
```

---

## 📈 효과 예측

### 현재 (명시적 입력)
```
사용자 요청: 100건
AI가 타입 물어봄: 100건
사용자 재입력: 100건
평균 대화 횟수: 2.0회
```

### 개선 후 (스마트 감지)
```
사용자 요청: 100건
자동 판단 성공: 80건
확인 요청: 20건
사용자 재입력: 5건 (타입 변경)
평균 대화 횟수: 1.25회 (37.5% 감소)
```

---

## 🎯 결론

### 즉시 적용 가능 (추천)

**전략 6 + 전략 2 조합:**
1. 저장소 이름으로 빠른 판단
2. 확신 있으면 해당 타입만 추가
3. 확신 없으면 둘 다 추가

**구현:**
- `source_detector.py` 추가 (100줄)
- `add_git_source_smart` 도구 추가 (50줄)
- 시스템 메시지 업데이트

**예상 시간:** 2-3시간
**효과:** 사용자 경험 크게 개선

---

**작성일:** 2026-07-29
**프로젝트:** yuta_logagent
