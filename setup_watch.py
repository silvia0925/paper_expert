"""Set up photonic chip watch topic."""
import asyncio
from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library


async def main():
    config = PaperExpertConfig.load()
    lib = Library(config)

    # Check existing watch topics
    existing = lib.list_watch_topics()
    print(f"Existing watch topics: {len(existing)}")
    for t in existing:
        print(f"  - ID={t['id']}, name={t['name']}, queries={t.get('queries')}")

    # Create photonic chip watch topic
    queries = [
        "silicon photonics chip",
        "photonic integrated circuit AI",
        "optical interconnect chip",
        "optoelectronic integration",
        "silicon optical computing",
        "photonic neural network accelerator",
        "silicon photonic AI accelerator",
        "optical computing chiplet",
        "光芯片",
        "硅光芯片",
        "光子集成电路",
        "光互联芯片",
        "光电融合计算",
    ]

    topic_id = lib.add_watch_topic(
        name="光芯片前沿研究",
        queries=queries,
        fetch_limit=15,
        notify_channels=["wechat"],
    )

    topic = lib.get_watch_topic(topic_id)
    print(f"\nCreated watch topic:")
    print(f"  ID: {topic_id}")
    print(f"  Name: {topic['name']}")
    print(f"  Queries ({len(topic['queries'])}):")
    for q in topic["queries"]:
        print(f"    - {q}")
    print(f"  Fetch limit: {topic['fetch_limit']}")
    print(f"  Notify channels: {topic['notify_channels']}")
    print(f"  Active: {topic['is_active']}")

    await lib.close()


if __name__ == "__main__":
    asyncio.run(main())
