"""Weekly paper monitor runner - called by cron every Sunday 10:00 AM Beijing time."""
import asyncio
import sys
from pathlib import Path

# Ensure paper_expert is importable
sys.path.insert(0, str(Path(__file__).parent))

from paper_expert.core.config import PaperExpertConfig
from paper_expert.core.library import Library


async def main():
    config = PaperExpertConfig.load()
    lib = Library(config)

    print("=" * 60)
    print("Paper Expert Weekly Monitor - 光芯片前沿研究")
    print("=" * 60)

    # Run all active watch topics
    result = await lib.run_monitor()

    if hasattr(result, "results"):
        print(f"\nRun at: {result.run_at}")
        print(f"Topics checked: {result.topics_checked}")
        print(f"Papers found: {result.total_found}")
        print(f"Papers added: {result.total_added}")

        for r in result.results:
            print(f"\n--- {r.topic_name} ---")
            print(f"  Papers found: {r.papers_found}")
            print(f"  Papers added: {r.papers_added}")
            if r.new_papers:
                print(f"  New papers:")
                for p in r.new_papers:
                    print(f"    - {p['title'][:80]}")
            if r.notify_results:
                print(f"  Notified via: {list(r.notify_results.keys())}")
            if r.error:
                print(f"  Error: {r.error}")
    else:
        print(f"\nTopic: {result.topic_name}")
        print(f"Papers found: {result.papers_found}")
        print(f"Papers added: {result.papers_added}")
        if result.new_papers:
            for p in result.new_papers:
                print(f"  - {p['title'][:80]}")
        if result.error:
            print(f"Error: {result.error}")

    print("\n" + "=" * 60)
    print("Monitor complete.")
    await lib.close()


if __name__ == "__main__":
    asyncio.run(main())
