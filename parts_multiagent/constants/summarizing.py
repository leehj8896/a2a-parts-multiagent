from __future__ import annotations


SUMMARY_PROMPT_TEMPLATE = """
You answer inventory questions from Google Sheets query results.

User question:
{query}

Google Sheets context:
{csv_context}

Query result:
{raw_result}

Return a concise Korean answer. Do not invent data that is not in the result.
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
