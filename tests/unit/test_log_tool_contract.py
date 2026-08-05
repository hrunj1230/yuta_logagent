"""
일지 도구의 인자 계약(argument contract) 단위 테스트

왜 필요한가:
    retriever_vectordb 의 시그니처는 여러 번 바뀌었는데 호출부가 따라오지 못했다.

        0cd141a  user_id 추가 (다중 사용자 전환)
                 → test_log_tools.py 가 user_id 없이 호출한 채로 남아 깨짐
        9c3f4e1  end_date 추가 (기간 조회). reference_len 은 유지
        이후     reference_len 제거, 개수 제한을 분량 예산(_render)으로 대체

    깨진 호출부가 오래 남은 이유는 test_log_tools.py 가 예외를 try/except 로
    삼켜 출력만 하기 때문이다. 종료 코드가 항상 0 이라 아무도 눈치채지 못했다.

    이 테스트는 도구가 실제로 받는 인자 이름을 못박아서, 시그니처가 바뀌면
    호출부를 고치기 전에 여기서 먼저 빨간불이 켜지게 한다.

    스키마만 검사한다 — ChromaDB 조회도, 네트워크도 타지 않는다.
"""
import pytest
from pydantic import ValidationError

from src.tools.log import maker_logfile, retriever_vectordb


def _schema(tool) -> dict:
    """도구의 인자 스키마(JSON Schema)를 꺼낸다."""
    return tool.args_schema.model_json_schema()


class TestRetrieverVectordbContract:
    def test_required_args(self):
        """date 와 user_id 는 필수다. user_id 가 빠지면 호출 자체가 불가능하다."""
        assert set(_schema(retriever_vectordb)["required"]) == {"date", "user_id"}

    def test_optional_end_date(self):
        """기간 조회용 end_date 는 선택 인자로 존재해야 한다."""
        props = _schema(retriever_vectordb)["properties"]
        assert "end_date" in props
        assert "end_date" not in _schema(retriever_vectordb)["required"]

    def test_reference_len_is_gone(self):
        """
        구 시그니처의 reference_len 은 남아 있으면 안 된다.

        개수로 자르면 '중요한 N건'이 아니라 '먼저 저장된 N건'이 남는다.
        날짜 필터는 정확일치라 문서 사이에 우열이 없기 때문이다. 그래서
        개수 제한을 없애고 분량 예산(_render)으로 대체했다.
        이 인자가 되살아나면 그 회귀가 다시 생긴다.
        """
        assert "reference_len" not in _schema(retriever_vectordb)["properties"]

    def test_old_call_shape_is_rejected(self):
        """
        구 호출부의 인자 조합은 반드시 거부된다.

        이 테스트가 실패한다면 누군가 user_id 를 선택 인자로 되돌린 것이고,
        그러면 사용자 컬렉션을 잘못 잡는 조용한 버그로 이어진다.
        """
        with pytest.raises(ValidationError):
            retriever_vectordb.invoke({"date": "2026년 07월 28일", "reference_len": "2"})

    def test_current_call_shape_validates(self):
        """현재 호출부가 쓰는 인자 조합은 스키마 검증을 통과한다."""
        args = retriever_vectordb.args_schema.model_validate(
            {"date": "2026-07-28", "user_id": "someone", "end_date": "2026-07-29"}
        )
        assert args.date == "2026-07-28"
        assert args.user_id == "someone"


class TestMakerLogfileContract:
    def test_required_args(self):
        """일지 저장은 세 인자 모두 필수다 — user_id 가 없으면 남의 컬렉션에 쓴다."""
        assert set(_schema(maker_logfile)["required"]) == {"date", "content", "user_id"}
