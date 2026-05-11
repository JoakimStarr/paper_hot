"""Fix double/triple-encoded JSON in authors and keywords_cn columns."""
import asyncio
import json
from app.database import AsyncSessionLocal
from sqlalchemy import text as sa_text, select as sa_select
from app.models import Paper as PaperModel


def _decode_json_recursive(value):
    if value is None:
        return None
    if isinstance(value, list):
        return value
    if not isinstance(value, str):
        return value
    try:
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, str):
            return _decode_json_recursive(parsed)
    except (json.JSONDecodeError, TypeError):
        pass
    return value


async def clean():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            sa_select(PaperModel.id, PaperModel.authors, PaperModel.keywords_cn)
        )
        papers = result.all()

        fixed = 0
        for paper in papers:
            needs_update = False
            authors_val = _decode_json_recursive(paper.authors)
            keywords_val = _decode_json_recursive(paper.keywords_cn)

            if isinstance(authors_val, list) and isinstance(paper.authors, str):
                needs_update = True
            elif authors_val is None and paper.authors is not None:
                needs_update = True
                authors_val = []

            if isinstance(keywords_val, list) and isinstance(paper.keywords_cn, str):
                needs_update = True
            elif keywords_val is None and paper.keywords_cn is not None:
                needs_update = True
                keywords_val = []

            if needs_update:
                await db.execute(
                    sa_text(
                        "UPDATE papers SET authors = :authors, keywords_cn = :keywords WHERE id = :id"
                    ),
                    {
                        "id": paper.id,
                        "authors": json.dumps(authors_val, ensure_ascii=False) if isinstance(authors_val, list) else paper.authors,
                        "keywords_cn": json.dumps(keywords_val, ensure_ascii=False) if isinstance(keywords_val, list) else paper.keywords_cn,
                    },
                )
                fixed += 1

        await db.commit()
        print(f"Fixed {fixed} papers with double/triple-encoded JSON")


if __name__ == "__main__":
    asyncio.run(clean())
