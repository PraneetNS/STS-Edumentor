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
    assert "base case" not in full_raw1
    assert "base case" not in full_planned1

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
    
    # 3. Test programmatic visual introduction injection (when missing)
    parser3 = RealtimeStreamingParser()
    chunks3 = [
        "<show type=\"code\">def f(): pass</show>",
        "<show type=\"workflow\">A -> B</show>",
        "<show type=\"checklist\">- Option A</show>",
        "<show type=\"table\">ColA | ColB</show>",
        "<show type=\"roadmap\">Step 1</show>",
    ]
    planned_output3 = []
    for chunk in chunks3:
        for event in parser3.feed(chunk):
            planned_output3.append(event["planned"])
    for event in parser3.finalize():
        planned_output3.append(event["planned"])
    full_planned3 = "".join(planned_output3)
    
    print("\n--- TEST 3: PLANNED OUTPUT (without preceding intro) ---")
    print(full_planned3)
    assert "Below is the code for this." in full_planned3
    assert "Below is the workflow for this." in full_planned3
    assert "Below is the checklist for this." in full_planned3
    assert "Below is the table for this." in full_planned3
    assert "Here is a diagram for this." in full_planned3

    # 4. Test no duplicate visual introduction injection (when already present)
    parser4 = RealtimeStreamingParser()
    chunks4 = [
        "<speak>Below is the code for implementation:</speak><show type=\"code\">def f(): pass</show>",
        "<speak>Here is the workflow for compiler design:</speak><show type=\"workflow\">A -> B</show>",
    ]
    planned_output4 = []
    for chunk in chunks4:
        for event in parser4.feed(chunk):
            planned_output4.append(event["planned"])
    for event in parser4.finalize():
        planned_output4.append(event["planned"])
    full_planned4 = "".join(planned_output4)
    
    print("\n--- TEST 4: PLANNED OUTPUT (with preceding intro) ---")
    print(full_planned4)
    assert "Below is the code for implementation" in full_planned4
    assert "Here is the workflow for compiler design" in full_planned4
    assert full_planned4.count("Below is the code") == 1
    assert full_planned4.count("Below is the workflow") == 0
    
    # 5. Test custom title attribute parsing and rendering
    parser5 = RealtimeStreamingParser()
    chunks5 = [
        "<show type=\"checklist\" title=\"Advantages of OOP\">- Abstraction\n- Inheritance</show>",
        "<show type=\"table\" title=\"Comparison matrix\">Columns</show>",
        "<show type=\"roadmap\" title=\"DSA Roadmap\">Step 1: Arrays</show>",
    ]
    raw_output5 = []
    for chunk in chunks5:
        for event in parser5.feed(chunk):
            raw_output5.append(event["raw"])
    for event in parser5.finalize():
        raw_output5.append(event["raw"])
    full_raw5 = "".join(raw_output5)
    
    print("\n--- TEST 5: RAW OUTPUT (with custom titles) ---")
    print(full_raw5.encode('ascii', errors='replace').decode('ascii'))
    assert "### 📋 Advantages of OOP" in full_raw5
    assert "### 📋 Comparison matrix" in full_raw5
    assert "### 🗺️ DSA Roadmap" in full_raw5
    
    # 6. Test case-insensitivity, spaces in tags, and unclosed tags discard
    parser6 = RealtimeStreamingParser()
    chunks6 = [
        "< SPEAK >Hello world! < / Speak >",
        "<  SHOW type = \"checklist\" title = \"Robust Checklist\"  > - Item 1\n- Item 2 < / Show >",
        "Some trailing text < speak",
    ]
    raw_output6 = []
    planned_output6 = []
    for chunk in chunks6:
        for event in parser6.feed(chunk):
            raw_output6.append(event["raw"])
            planned_output6.append(event["planned"])
    for event in parser6.finalize():
        raw_output6.append(event["raw"])
        planned_output6.append(event["planned"])
    full_raw6 = "".join(raw_output6)
    full_planned6 = "".join(planned_output6)
    
    print("\n--- TEST 6: RAW OUTPUT (with spaces, casing, and unclosed tag) ---")
    print(full_raw6.encode('ascii', errors='replace').decode('ascii'))
    print("\n--- TEST 6: PLANNED OUTPUT (with spaces, casing, and unclosed tag) ---")
    print(full_planned6.encode('ascii', errors='replace').decode('ascii'))
    
    assert "Hello world!" in full_raw6
    assert "Hello world!" in full_planned6
    assert "Robust Checklist" in full_raw6
    assert "Item 1" in full_raw6
    assert "Some trailing text" in full_raw6
    assert "Some trailing text" in full_planned6
    # Tags should not be visible anywhere
    assert "SPEAK" not in full_raw6
    assert "speak" not in full_raw6
    assert "SHOW" not in full_raw6
    assert "show" not in full_raw6
    
    # 7. Test table auto-closing when hitting followup, </table> close alias, and table wrapping heal
    parser7 = RealtimeStreamingParser()
    chunks7_a = [
        '<show type="table" title="Engineers comparison"><thead><tr><th>Name</th></tr></thead>',
        '</table>',
        '<followup>Next step?</followup>'
    ]
    raw_output7_a = []
    for chunk in chunks7_a:
        for event in parser7.feed(chunk):
            raw_output7_a.append(event["raw"])
    for event in parser7.finalize():
        raw_output7_a.append(event["raw"])
    full_raw7_a = "".join(raw_output7_a)
    
    print("\n--- TEST 7A: RAW OUTPUT (closed by </table> and wrapped in <table>) ---")
    print(full_raw7_a.encode('ascii', errors='replace').decode('ascii'))
    assert "<table>" in full_raw7_a
    assert "</table>" in full_raw7_a
    assert "</table>\n</table>" not in full_raw7_a
    assert "### 📋 Engineers comparison" in full_raw7_a
    
    parser7_b = RealtimeStreamingParser()
    chunks7_b = [
        '<show type="table" title="Engineers comparison"><thead><tr><th>Name</th></tr></thead>',
        '<followup>Next step?</followup>'
    ]
    raw_output7_b = []
    for chunk in chunks7_b:
        for event in parser7_b.feed(chunk):
            raw_output7_b.append(event["raw"])
    for event in parser7_b.finalize():
        raw_output7_b.append(event["raw"])
    full_raw7_b = "".join(raw_output7_b)
    
    print("\n--- TEST 7B: RAW OUTPUT (auto-closed by <followup> and wrapped in <table>) ---")
    print(full_raw7_b.encode('ascii', errors='replace').decode('ascii'))
    assert "<table>" in full_raw7_b
    assert "### 📋 Engineers comparison" in full_raw7_b

    print("\n[SUCCESS] RealtimeStreamingParser tests passed successfully!")

if __name__ == "__main__":
    run_test()
