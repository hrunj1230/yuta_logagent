# Source & Embedding Tools 사용 가이드

## 개요

소스 관리 및 임베딩 도구를 통해 Git 저장소, 로컬 파일, 커밋 로그 등을 벡터DB에 임베딩할 수 있습니다.

## 도구 목록

### 소스 관리
- `add_source_to_db`: 소스 등록
- `get_user_sources`: 소스 목록 조회
- `delete_source_from_db`: 소스 삭제
- `request_source_type_clarification`: 소스 타입 안내

### 임베딩
- `embed_source`: 소스 임베딩 실행
- `get_embedding_status`: 임베딩 상태 조회

## 사용 예시

### 1. Git 저장소 임베딩
```
사용자: https://github.com/user/repo.git
Agent: add_source_to_db 호출 → 소스 등록
사용자: 1번 소스 임베딩해줘
Agent: embed_source 호출 → 파일 수집 및 임베딩
```

### 2. 증분 업데이트
- 같은 소스를 다시 임베딩하면 변경된 파일만 처리
- 파일 해시(SHA256)로 중복 감지

### 3. 지원 파일 타입
- .txt, .md, .py, .js, .tsx, .jsx, .java, .go, .rs, .c, .cpp, .h

## 내부 구조

- **DB**: SQLite (Source 메타데이터)
- **파일시스템**: `./data/sources/{user_id}/{source_name}/`
- **벡터DB**: ChromaDB (`./chroma_db/user_{user_id}/`)

## 소스 타입

1. **git**: Git 저장소 clone 후 파일 임베딩
2. **git_log**: Git 커밋 히스토리 임베딩
3. **local**: 로컬 디렉토리 사용
4. **agent_chatlog**: 에이전트 대화 로그 (추후 구현)
5. **memsearch**: 메모리 검색 데이터 (추후 구현)

## 상태 추적

각 소스는 다음 상태 중 하나를 가집니다:
- **PENDING** (⏳): 등록됨, 임베딩 대기
- **IN_PROGRESS** (🔄): 임베딩 진행 중
- **COMPLETED** (✅): 임베딩 완료
- **FAILED** (❌): 임베딩 실패

## 문제 해결

### 임베딩 실패 시
1. `get_embedding_status`로 오류 메시지 확인
2. Git URL이 올바른지 확인
3. 로컬 경로가 존재하는지 확인
4. 네트워크 연결 확인

### ChromaDB 초기화
```bash
rm -rf ./chroma_db
```
