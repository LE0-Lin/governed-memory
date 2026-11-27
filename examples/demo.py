"""Run the packaged offline demo from a source checkout."""

import asyncio

from governed_memory.demo import main

if __name__ == "__main__":
    asyncio.run(main())
