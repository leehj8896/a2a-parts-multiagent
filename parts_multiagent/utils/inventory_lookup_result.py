from __future__ import annotations

import re


# 재고 조회 결과 문자열에서 일치 행 수를 추출합니다.
def extract_matched_row_count(result_text: str) -> int:
    if "조건에 맞는 행이 없습니다." in result_text:
        return 0

    matched_row_count = re.search(r"일치한 행 수:\s*(\d+)", result_text)
    if matched_row_count is None:
        return 0
    return int(matched_row_count.group(1))
