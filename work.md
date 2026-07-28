tool파일 새롭게 생성

1. source tool -source.py
    1. 소스 목록 조회
    2. 소스 추가
    3. 소스 삭제
    4. SourceType의 판단 부족시 확실한 SourceType 요청 
    예시 ->
    SOURCE_TYPE_OPTIONS = [

    {

        "label": "Git 저장소",

        "value": "git",

        "description": "GitHub 등의 저장소를 clone하고 임베딩합니다.",

    },
    {

        "label": "Git log",

        "value": "git_log",

        "description": "Git log를 임베딩합니다.",

    },
    {

        "label": "로컬",

        "value": "local",

        "description": "서버에 존재하는 로컬 디렉터리를 사용합니다.",

    },

    {

        "label": "에이전트 대화 로그",

        "value": "agent_chatlog",

        "description": "에이전트 대화 기록을 소스로 등록합니다.",

    },

    {

        "label": "메모리 검색",

        "value": "memsearch",

        "description": "기존 메모리 검색 데이터를 연결합니다.",

    },

]
2. embedding tool -embedding.py
    1. 임베딩할 파일 목록 조회( 임베딩 진행 여부 판단 - 중복제거)
    2. 임베딩 실행
        1. 소스의 종류에 따른 임베딩 실행
            1. git -> clone 후 업로드
            2. git_log -> git log
            3. local -> 업로드
            4. agent_chatlog -> 업로드
            5. memsearch -> 업로드
    3. 임베딩 삭제