"""Fix dirty author data: trailing commas, email addresses, empty entries, concatenated names."""
import asyncio
import json
import re
from app.database import AsyncSessionLocal
from sqlalchemy import text as sa_text, select as sa_select
from app.models import Paper as PaperModel


def clean_author_name(name: str) -> str:
    name = name.strip().rstrip(',').rstrip('，').strip()
    name = re.sub(r'[\w.+-]+@[\w.+-]+', '', name)
    name = re.sub(r'[\w.+-]+@\.com', '', name)
    name = re.sub(r'@\.com', '', name)
    name = name.strip()
    name = re.sub(r'\s+', '', name)
    return name


def split_concatenated_authors(name: str) -> list[str]:
    if '@' in name or '.com' in name:
        parts = re.findall(r'[\u4e00-\u9fff]{2,4}', name)
        if len(parts) >= 2:
            return parts
    return [name]


def clean_authors_list(authors: list) -> list:
    cleaned = []
    for a in authors:
        if not isinstance(a, str):
            continue
        a = a.strip()
        if not a or a == ' ' * len(a):
            continue
        split_results = split_concatenated_authors(a)
        for part in split_results:
            cleaned_name = clean_author_name(part)
            if cleaned_name and len(cleaned_name) >= 2:
                if re.search(r'[\u4e00-\u9fff]', cleaned_name):
                    cleaned.append(cleaned_name)
    return cleaned


async def clean():
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            sa_select(PaperModel.id, PaperModel.authors)
        )
        papers = result.all()

        fixed = 0
        total_authors_before = 0
        total_authors_after = 0
        empty_removed = 0
        comma_fixed = 0
        email_fixed = 0

        for paper in papers:
            authors_val = paper.authors
            if not authors_val:
                continue

            if isinstance(authors_val, str):
                try:
                    authors_val = json.loads(authors_val)
                except (json.JSONDecodeError, TypeError):
                    continue

            if not isinstance(authors_val, list):
                continue

            total_authors_before += len(authors_val)

            needs_update = False
            for a in authors_val:
                if isinstance(a, str):
                    if a.endswith(',') or a.endswith('，'):
                        comma_fixed += 1
                        needs_update = True
                    if '@' in a or '.com' in a:
                        email_fixed += 1
                        needs_update = True
                    if not a.strip():
                        empty_removed += 1
                        needs_update = True

            if needs_update:
                cleaned = clean_authors_list(authors_val)
                total_authors_after += len(cleaned)

                if cleaned != authors_val:
                    await db.execute(
                        sa_text("UPDATE papers SET authors = :authors WHERE id = :id"),
                        {
                            "id": paper.id,
                            "authors": json.dumps(cleaned, ensure_ascii=False),
                        },
                    )
                    fixed += 1
            else:
                total_authors_after += len(authors_val)

        await db.commit()
        print(f"Fixed {fixed} papers with dirty author data")
        print(f"  Trailing commas fixed: {comma_fixed}")
        print(f"  Email addresses removed: {email_fixed}")
        print(f"  Empty entries removed: {empty_removed}")
        print(f"  Total authors: {total_authors_before} -> {total_authors_after}")


if __name__ == "__main__":
    asyncio.run(clean())
