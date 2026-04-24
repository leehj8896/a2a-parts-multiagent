from __future__ import annotations


SUMMARY_PROMPT_TEMPLATE = """
Google Sheets 조회 결과를 바탕으로 재고 질문에 답변합니다.

사용자 질문:
{query}

Google Sheets 컨텍스트:
{csv_context}

조회 결과:
{raw_result}

간결한 한국어 답변만 반환하세요. 조회 결과에 없는 데이터는 지어내지 마세요.
"""


def build_summary_prompt(
    query: str,
    csv_context: str,
    raw_result: str,
) -> str:
    return SUMMARY_PROMPT_TEMPLATE.format(
        query=query,
        csv_context=csv_context,
        raw_result=raw_result,
    )
