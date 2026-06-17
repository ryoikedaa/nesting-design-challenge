import json

with open('data/jobs.json') as f:
    jobs = json.load(f)

with open('data/inventory.json') as f:
    inventory = json.load(f)

with open('data/order_history.json') as f:
    history = json.load(f)

print(f"Jobs: {len(jobs)}")
print(f"Inventory: {len(inventory)}")
print(f"History: {len(history)}")




drops = [item for item in inventory if item['kind'] == 'drop']
plates = [item for item in inventory if item['kind'] == 'plate']

print(f"Drops: {len(drops)}")
print(f"Fresh plates: {len(plates)}")

# Flatten all parts from all jobs into one list
parts = []
for job in jobs:
    for part in job['parts']:
        part['order_id'] = job['order_id']
        parts.append(part)

# Sort biggest to smallest by area
parts.sort(key=lambda p: p['width_in'] * p['length_in'], reverse=True)

print(f"\nTotal parts to cut: {len(parts)}")
print(f"Biggest part: {parts[0]['width_in']}x{parts[0]['length_in']} {parts[0]['alloy']}")
print(f"Smallest part: {parts[-1]['width_in']}x{parts[-1]['length_in']} {parts[-1]['alloy']}")

def fits(part, stock):
    w, l = part['width_in'], part['length_in']
    sw, sl = stock['width_in'], stock['length_in']
    # fits normally or rotated 90 degrees
    return (w <= sw and l <= sl) or (l <= sw and w <= sl)

# For each part, find matching drops
print("\nDrop matching:")
for part in parts:
    matching = [d for d in drops if 
                d['alloy'] == part['alloy'] and 
                abs(d['thickness_in'] - part['thickness_in']) < 0.01 and
                fits(part, d)]
    print(f"  {part['width_in']}x{part['length_in']} {part['alloy']} {part['thickness_in']
    }\" → {len(matching)} drops fit")

#Greedy algorithm to find the best layout

print("\nGreedy assignment:")
used_drops = set()
assignments = []

for part in parts:
    # find matching drops not already used
    matching = [d for d in drops if 
                d['id'] not in used_drops and
                d['alloy'] == part['alloy'] and 
                abs(d['thickness_in'] - part['thickness_in']) < 0.01 and
                fits(part, d)]
    
    if matching:
        # pick the tightest fitting drop (least waste)
        best = min(matching, key=lambda d: d['width_in'] * d['length_in'])
        used_drops.add(best['id'])
        assignments.append((part, best, 'drop'))
        print(f"  {part['width_in']}x{part['length_in']} {part['alloy']} → DROP {best['id']} ({best['width_in']}x{best['length_in']})")
    else:
        assignments.append((part, None, 'fresh plate'))
        print(f"  {part['width_in']}x{part['length_in']} {part['alloy']} → FRESH PLATE")

MACHINE_RATE = 75 / 60  # per minute
SETUP_TIME = 20  # minutes

fresh_needed = [a for a in assignments if a[2] == 'fresh plate']
drops_used = [a for a in assignments if a[2] == 'drop']

# Cost with drops
setup_cost = len(fresh_needed) * SETUP_TIME * MACHINE_RATE
print(f"\n--- Cost Summary ---")
print(f"Parts from drops: {len(drops_used)}")
print(f"Parts needing fresh plates: {len(fresh_needed)}")
print(f"Setup cost (fresh plates only): ${setup_cost:.2f}")

# Cost without drops (baseline)
baseline_setup = len(assignments) * SETUP_TIME * MACHINE_RATE
print(f"\nBaseline (no drops, every part its own plate): ${baseline_setup:.2f}")
print(f"Savings from using drops: ${baseline_setup - setup_cost:.2f}")