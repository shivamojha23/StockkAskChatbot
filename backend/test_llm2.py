import asyncio
from rag_service import get_rag_service

async def main():
    print("Connecting to Pinecone...")
    rag = get_rag_service()
    print("Pinecone Init OK!")
    stream = rag.generate_stream('What is P/E ratio?', [])
    async for c in stream:
        print(c, end='', flush=True)
    print("\nStream Complete")

if __name__ == "__main__":
    asyncio.run(main())
