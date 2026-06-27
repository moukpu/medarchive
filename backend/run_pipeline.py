import asyncio
from sqlalchemy import select
from app.db import SessionLocal
from app.pipeline.runner import process_pending, PriceDocument, ParseStatus

async def main():
    async with SessionLocal() as session:
        print("Starting process_pending...")
        await process_pending(session)
        
    # Now we need to wait until no documents are pending or processing
    while True:
        await asyncio.sleep(5)
        async with SessionLocal() as session:
            res = await session.execute(
                select(PriceDocument.doc_id).where(
                    PriceDocument.parse_status.in_([ParseStatus.pending, ParseStatus.processing])
                )
            )
            pending = len(res.all())
            print(f"Waiting... {pending} documents still pending/processing")
            if pending == 0:
                break
                
    print("All done!")

if __name__ == "__main__":
    asyncio.run(main())
