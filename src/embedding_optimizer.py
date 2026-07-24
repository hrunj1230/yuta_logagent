# 임베딩 최적화: 토큰 절약 전략

import hashlib
from datetime import datetime, timedelta

# 이미 임베딩된 파일 추적 (간단한 캐시)
embedding_cache = {}

def should_embed_file(file_path: str, content: str, last_modified: datetime) -> bool:
    """
    파일을 임베딩해야 하는지 판단 (토큰 절약)

    Returns:
        True: 임베딩 필요
        False: 이미 임베딩됨 (스킵)
    """
    # 파일 해시 생성
    content_hash = hashlib.md5(content.encode()).hexdigest()

    cache_key = f"{file_path}_{content_hash}"

    # 캐시 확인
    if cache_key in embedding_cache:
        cached_time = embedding_cache[cache_key]

        # 7일 이내에 임베딩했으면 스킵
        if datetime.now() - cached_time < timedelta(days=7):
            return False

    # 임베딩 필요 (캐시에 기록)
    embedding_cache[cache_key] = datetime.now()
    return True


# 실제 토큰 절약 예시
"""
100개 파일, 각 1000 토큰

[중복 방지 없음]
- 매번 전체 임베딩: 100 * 1000 = 100,000 토큰/동기화

[중복 방지 있음]
- 첫 동기화: 100,000 토큰
- 2번째 동기화 (변경 10개): 10,000 토큰 (90% 절약!)
- 3번째 동기화 (변경 5개): 5,000 토큰 (95% 절약!)
"""


def filter_unnecessary_content(content: str) -> str:
    """
    불필요한 내용 제거 (토큰 절약)

    제거 대상:
    - 긴 코드 블록 (요약으로 대체)
    - 반복되는 패턴
    - 메타데이터
    """
    import re

    # 1. 긴 코드 블록 축약
    def shorten_code_block(match):
        code = match.group(1)
        lines = code.split('\n')
        if len(lines) > 10:
            return f"```\n[코드 블록: {len(lines)}줄 생략]\n```"
        return match.group(0)

    content = re.sub(r'```[\s\S]*?```', shorten_code_block, content)

    # 2. 연속된 빈 줄 제거
    content = re.sub(r'\n{3,}', '\n\n', content)

    # 3. 불필요한 공백 제거
    content = re.sub(r' +', ' ', content)

    return content


# 사용 예시
"""
원본: 5,000자 (코드 블록 포함)
필터링 후: 2,000자 (60% 토큰 절약!)
"""
