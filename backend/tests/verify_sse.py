import sys
import os
import asyncio
import json

# Add the parent folder of tests to the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from edmentor.confidence_router import StreamingDualParser, to_sse

MOCK_RESPONSES = {
    "prime": (
        "<speak>Sure! Here is a simple Python function to check if a number is prime. "
        "It checks for factors up to the square root of the number.</speak>"
        '<show type="code" lang="python">\n'
        "def is_prime(n):\n"
        "    if n < 2: return False\n"
        "    for i in range(2, int(n**0.5) + 1):\n"
        "        if n % i == 0: return False\n"
        "    return True\n"
        "</show>"
        "<followup>Want me to show you how to optimize this further using the Sieve of Eratosthenes?</followup>"
    ),
    "thread": (
        "<speak>A process is an independent executing program with its own memory space. "
        "A thread is a lightweight execution unit within a process, sharing memory with other threads. "
        "This makes threads faster to create and switch, but they can conflict over shared memory.</speak>"
        '<show type="table">\n'
        "| Feature | Process | Thread |\n"
        "|---|---|---|\n"
        "| Memory | Isolated | Shared |\n"
        "| Creation | Slow | Fast |\n"
        "</show>"
        "<followup>Want to go deeper into how mutex locks prevent threads from corrupting shared memory?</followup>"
    ),
    "dp": (
        "<speak>Dynamic Programming is a method for solving complex problems by breaking them down into simpler subproblems. "
        "It is applicable when subproblems overlap. "
        "Here is a study roadmap to master it.</speak>"
        '<show type="roadmap">\n'
        "Week 1: Recursion & Memoization\n"
        "Week 2: Iterative Tabulation\n"
        "Week 3: Classic Problems (Knapsack, LCS)\n"
        "</show>"
        "<followup>Should I break week three into a day by day plan since DP is usually the hardest part?</followup>"
    )
}

async def run_verification():
    print("=" * 60)
    print("           VERIFICATION OF STREAMING DUAL PARSER SSE           ")
    print("=" * 60)
    
    for query_name, raw_response in MOCK_RESPONSES.items():
        print(f"\n--- Testing Query: {query_name.upper()} ---")
        print(f"Raw response: {raw_response[:60]}...[truncated]")
        print("Parsing stream and generating SSE events:")
        print("-" * 40)
        
        parser = StreamingDualParser()
        # Simulate chunked streaming token-by-token
        chunk_size = 5
        for i in range(0, len(raw_response), chunk_size):
            chunk = raw_response[i:i+chunk_size]
            events = parser.feed(chunk)
            for event in events:
                print(to_sse(event), end="")
                
        # Finalize and print any remaining
        for event in parser.finalize():
            print(to_sse(event), end="")
            
        print("-" * 40)

if __name__ == "__main__":
    asyncio.run(run_verification())
