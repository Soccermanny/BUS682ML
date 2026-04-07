import re
from pathlib import Path

log_file = Path('enrich_output.log')
if log_file.exists():
    with open(log_file, 'r') as f:
        lines = f.readlines()
    
    print("="*80)
    print("ENRICHMENT PROGRESS CHECK")
    print("="*80)
    
    # Find the highest film number processed
    pattern = r'\[(\d+)/744\]'
    matches = []
    for line in lines:
        m = re.search(pattern, line)
        if m:
            matches.append(int(m.group(1)))
    
    if matches:
        latest = max(matches)
        pct = (latest / 744) * 100
        print(f"\n✅ ENRICHMENT RUNNING!")
        print(f"Progress: {latest} / 744 films processed ({pct:.1f}%)")
        
        # Count enrichments
        enriched_count = len([l for l in lines if re.search(r': \$[\d,]+', l)])
        not_found_count = len([l for l in lines if ': NOT FOUND' in l])
        
        print(f"\nEnrichments found: {enriched_count}")
        print(f"Not found: {not_found_count}")
        print(f"Remaining: {744 - latest}")
        
        # Show last few entries
        print(f"\nLast 5 processed films:")
        for line in lines[-10:]:
            if '[' in line and ']' in line:
                print(f"  {line.strip()}")
    else:
        print("No progress found in log yet")
else:
    print("Log file not found yet")
