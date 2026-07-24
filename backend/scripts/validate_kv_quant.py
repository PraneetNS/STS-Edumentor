import asyncio
import argparse
import json
import httpx
import os
import difflib
import sys

PROMPTS = [
    "What is a binary search tree, and how does it maintain its sorted property?",
    "Explain the difference between a process and a thread in operating systems.",
    "How does the quicksort algorithm choose a pivot and partition the array?",
    "What is recursion? Explain it with a simple analogy.",
    "Can you write a Python function to check if a string is a palindrome?",
    "What is dynamic programming, and how does it differ from divide-and-conquer?",
    "Explain the time complexity of lookup, insertion, and deletion in a hash table.",
    "What is a SQL injection vulnerability, and how can prepared statements prevent it?",
    "How does garbage collection work in Java or Python?",
    "What is the difference between TCP and UDP? When would you use each?",
    "Explain the concept of inheritance and polymorphism in object-oriented programming.",
    "What are the SOLID design principles? Briefly list and explain them.",
    "How does a REST API differ from GraphQL?",
    "What is a database index? How does it speed up queries, and what is the trade-off?",
    "Explain how the Dijkstra's algorithm finds the shortest path in a graph.",
    "What is a memory leak, and how can we detect/prevent it in C++?",
    "How does Git track changes under the hood?",
    "Explain the difference between deep learning and traditional machine learning.",
    "What is MVC architecture, and why is it used in web development?",
    "Can you explain what a docker container is to a beginner?"
]

async def query_llm(client: httpx.AsyncClient, prompt: str, base_url: str) -> str:
    payload = {
        "messages": [
            {"role": "system", "content": "You are a helpful engineering tutor. Explain the following concept clearly and concisely."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2, # low temperature for deterministic evaluation
        "max_tokens": 512,
        "stream": False
    }
    try:
        resp = await client.post(f"{base_url}/v1/chat/completions", json=payload, timeout=180.0)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Error querying LLM for prompt '{prompt}': {e}")
        return ""

async def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["generate", "compare"], required=True)
    parser.add_argument("--baseline", default="baseline_responses.json")
    parser.add_argument("--out", default="responses.json")
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    args = parser.parse_args()

    async with httpx.AsyncClient() as client:
        if args.mode == "generate":
            print(f"Generating completions for {len(PROMPTS)} prompts...")
            results = {}
            for i, p in enumerate(PROMPTS):
                print(f"[{i+1}/{len(PROMPTS)}] Querying: {p}")
                ans = await query_llm(client, p, args.url)
                results[p] = ans
            
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"Baseline responses written to {args.out}")

        elif args.mode == "compare":
            if not os.path.exists(args.baseline):
                print(f"Error: Baseline file '{args.baseline}' not found.")
                return

            with open(args.baseline, "r", encoding="utf-8") as f:
                baseline = json.load(f)

            print(f"Generating completions and comparing against baseline...")
            results = {}
            mismatches = 0
            for i, p in enumerate(PROMPTS):
                print(f"[{i+1}/{len(PROMPTS)}] Querying: {p}")
                ans = await query_llm(client, p, args.url)
                results[p] = ans
                
                base_ans = baseline.get(p, "")
                if base_ans != ans:
                    print(f"\n--- DIFF FOR PROMPT: {p} ---")
                    diff = list(difflib.unified_diff(
                        base_ans.splitlines(),
                        ans.splitlines(),
                        fromfile="baseline",
                        tofile="quantized"
                    ))
                    if diff:
                        print("\n".join(diff[:15]))
                        mismatches += 1
                    else:
                        print("Exact match except trailing whitespace.")
                    print("-" * 40)

            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)
            print(f"Quantized responses written to {args.out}")
            print(f"Total diffs/mismatches observed: {mismatches} / {len(PROMPTS)}")
            if mismatches == 0:
                print("SUCCESS: 100% exact matches or zero quality diffs!")
            else:
                print("Check details above for correctness comparison.")

if __name__ == "__main__":
    asyncio.run(main())
