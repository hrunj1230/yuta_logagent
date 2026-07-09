
 # Log Maker

Log 세상에서 일지를 쓰는게 제일 힘들고 귀찮은 사람들을 위한 딸깍 에이전트

파일 구조
main
src /
    router
    controller
tools/
    ai_chat_vectorstore
    git_vectorstore
    log_generator
log_design/
    origin_log_design


프롬프트 입력 -> loop[프롬프트에 따른 에이전트 판단에 따른 tools호출 -> 에이전트 검증 ]-> 2026.99.99log.md or 복사 문서 생성 답변
## 필수 기능
tools
(특정 날짜의 daliy_log 생성형 에이전트 -- > 날짜와 데이터가 없다면 수행 x)
(벡터 db조회 후 특정 날짜의 정보를 가져와 분석,요약후 log 파일 생성)
(aichatlog 파일 벡터화, git 파일 벡터화)

## 추후
(origin 프롬프트 커스텀 기능)


## 개발 일지

### 2026.07.08
- 프로젝트 세팅
- 구조 작성
- 순서도
- tools정리
- main - router -controller : design pattern 작성
- llm_router 추가 (embedding model - gemini,llm - codex, gemini, claude)
### 2026.07.09
- langgraph test 구성
- 

* codexoauth - messages 가 streaming으로 온다. 