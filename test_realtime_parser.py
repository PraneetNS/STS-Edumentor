from agent.realtime_parser import RealtimeStreamingParser

def run_test():
    # 1. Test original angle-bracket code tags
    parser = RealtimeStreamingParser()
    chunks1 = [
        "Hello! ", "Here is a function:\n",
        "<show type=", '"code" lang="', 'python">',
        "def factorial(n):\n",
        "    if n == 0:\n",
        "        return 1\n",
        "    return n * factorial(n-1)\n",
        "</show>\n",
        "<followup>Can you tell me the base case here?</followup>"
    ]
    
    raw_output1 = []
    planned_output1 = []
    
    for chunk in chunks1:
        for event in parser.feed(chunk):
            raw_output1.append(event["raw"])
            planned_output1.append(event["planned"])
            
    for event in parser.finalize():
        raw_output1.append(event["raw"])
        planned_output1.append(event["planned"])
        
    full_raw1 = "".join(raw_output1)
    full_planned1 = "".join(planned_output1)
    
    print("--- TEST 1: RAW OUTPUT (displayed on UI) ---")
    print(full_raw1)
    print("\n--- TEST 1: PLANNED OUTPUT (spoken by Kokoro) ---")
    print(full_planned1)
    
    assert "def factorial" in full_raw1
    assert "def factorial" not in full_planned1
    assert "base case" in full_raw1
    assert "base case" in full_planned1

    # 2. Test curly-brace tags and user's roadmap case
    parser2 = RealtimeStreamingParser()
    chunks2 = [
        "{speak} Azure is a cloud computing platform by Microsoft. ",
        "It offers virtual machines, databases, storage, networking services, and more. ",
        "{show type=\"roadmap\" lang=\"en\"}{show}{\"The Azure Cloud Services Roadmap\\n",
        "Step 1: Virtual Machines (VMs) — Run OS and apps like regular desktops.\\n",
        "Step 2: Storage & Databases — Store files or structured data reliably.\\n",
        "Step 3: Networking Services — Connect VMs, apps, and the internet securely.\\n",
        "Step 4: AI/ML Tools — Train models using Azure's GPU compute resources.\"}"
    ]
    
    raw_output2 = []
    planned_output2 = []
    
    for chunk in chunks2:
        for event in parser2.feed(chunk):
            raw_output2.append(event["raw"])
            planned_output2.append(event["planned"])
            
    for event in parser2.finalize():
        raw_output2.append(event["raw"])
        planned_output2.append(event["planned"])
        
    full_raw2 = "".join(raw_output2)
    full_planned2 = "".join(planned_output2)
    
    print("\n--- TEST 2: RAW OUTPUT (displayed on UI) ---")
    print(full_raw2.encode('ascii', errors='replace').decode('ascii'))
    print("\n--- TEST 2: PLANNED OUTPUT (spoken by Kokoro) ---")
    print(full_planned2.encode('ascii', errors='replace').decode('ascii'))
    
    # Assertions for Test 2
    assert "Azure is a cloud computing platform" in full_raw2
    assert "Azure is a cloud computing platform" in full_planned2
    assert "{speak}" not in full_raw2
    assert "{speak}" not in full_planned2
    assert "{show" not in full_raw2
    assert "{show" not in full_planned2
    assert "Virtual Machines (VMs)" in full_raw2
    assert "Virtual Machines (VMs)" not in full_planned2
    assert "Step 1:" not in full_raw2  # Should be formatted as "1. "
    assert "1. **Virtual Machines (VMs)** —" in full_raw2  # Nice custom markdown list item formatting
    assert "The Azure Cloud Services Roadmap" in full_raw2
    assert "{" not in full_raw2  # Should strip curly braces around content
    assert '"' not in full_raw2  # Should strip double quotes around content
    
    print("\n[SUCCESS] RealtimeStreamingParser tests passed successfully!")

if __name__ == "__main__":
    run_test()
