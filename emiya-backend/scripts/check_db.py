import asyncio
from app.database import AsyncSessionLocal
from sqlalchemy import text
async def main():
    async with AsyncSessionLocal() as db:
        for t in ['users','conversations','messages','relationships']:
            r = await db.execute(text(f"SELECT COUNT(*) FROM {t}"))
            print(f'{t}: {r.scalar()}')
        r = await db.execute(text("SELECT id, user_id, persona_id, user_persona_id, title FROM conversations"))
        for row in r.all(): print(f'  conv={str(row[0])[:8]} user={str(row[1])[:8]} persona={str(row[2])[:8] if row[2] else None} up={str(row[3])[:8] if row[3] else None} title={row[4]}')
        r = await db.execute(text("SELECT id, email FROM users"))
        for row in r.all(): print(f'  user={str(row[0])[:8]} email={row[1]}')
asyncio.run(main())
