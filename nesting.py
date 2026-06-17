import json

with open('data/jobs.json') as f:
    jobs = json.load(f)
with open('data/inventory.json') as f:
    inventory = json.load(f)
with open('data/order_history.json') as f:
    history = json.load(f)

# Shop Constraints
MACHINE_RATE = 75.0 / 60.0  # $1.25 per minute
SETUP_TIME = 20.0          # minutes ($25.00 flat setup cost)
KERF = 0.1                 # 1/10th inch saw blade width
MIN_DROP_SHORT_SIDE = 6.0  # Hard machine/convention boundary

drops = [item for item in inventory if item['kind'] == 'drop']
plates = [item for item in inventory if item['kind'] == 'plate']

# Flatten and sort parts by area descending
parts = []
for job in jobs:
    for part in job['parts']:
        part['order_id'] = job['order_id']
        parts.append(part)
parts.sort(key=lambda p: p['width_in'] * p['length_in'], reverse=True)

def fits(p_w, p_l, s_w, s_l):
    """Checks if a part fits inside stock dimensions (including 90 deg rotation)"""
    return (p_w <= s_w and p_l <= s_l) or (p_l <= s_w and p_w <= s_l)

used_drops = set()
assignments = []
fresh_plate_runs = [] # Tracks multi-part packing on fresh plates

for part in parts:
    p_w, p_l = part['width_in'], part['length_in']
    
    # 1. TRY TO ASSIGN TO AN EXISTING VALID DROP
    matching_drops = [
        d for d in drops 
        if d['id'] not in used_drops 
        and d['alloy'] == part['alloy'] 
        and abs(d['thickness_in'] - part['thickness_in']) < 0.01 
        and fits(p_w, p_l, d['width_in'], d['length_in'])
        and min(d['width_in'], d['length_in']) >= MIN_DROP_SHORT_SIDE # Enforce drop safety
    ]
    
    if matching_drops:
        best_drop = min(matching_drops, key=lambda d: d['width_in'] * d['length_in'])
        used_drops.add(best_drop['id'])
        assignments.append({'part': part, 'stock_id': best_drop['id'], 'type': 'drop'})
        continue

    # 2. TRY TO PACK MULTIPLE PARTS ONTO AN ALREADY OPENED FRESH PLATE BIN
    packed_successfully = False
    for run in fresh_plate_runs:
        if run['alloy'] == part['alloy'] and abs(run['thickness'] - part['thickness_in']) < 0.01:
            # Simple area-based remaining tracker heuristic (accounting for Kerf)
            used_area = run['used_area']
            total_area = run['plate_spec']['width_in'] * run['plate_spec']['length_in']
            part_area = (p_w + KERF) * (p_l + KERF)
            
            if total_area - used_area >= part_area and fits(p_w, p_l, run['plate_spec']['width_in'], run['plate_spec']['length_in']):
                run['used_area'] += part_area
                run['parts'].append(part)
                assignments.append({'part': part, 'stock_id': f"Fresh-Plate-Run-{run['id']}", 'type': 'packed_fresh'})
                packed_successfully = True
                break
                
    if packed_successfully:
        continue

    # 3. IF NO DROPS OR EXISTING RUNS WORK, OPEN A BRAND NEW FRESH PLATE
    matching_plates = [
        p for p in plates 
        if p['alloy'] == part['alloy'] 
        and abs(p['thickness_in'] - part['thickness_in']) < 0.01
        and fits(p_w, p_l, p['width_in'], p['length_in'])
    ]
    
    if matching_plates:
        # Pick the standard stock sheet size available
        selected_plate = matching_plates[0] 
        new_run_id = len(fresh_plate_runs) + 1
        fresh_plate_runs.append({
            'id': new_run_id,
            'alloy': part['alloy'],
            'thickness': part['thickness_in'],
            'plate_spec': selected_plate,
            'used_area': (p_w + KERF) * (p_l + KERF),
            'parts': [part]
        })
        assignments.append({'part': part, 'stock_id': f"Fresh-Plate-Run-{new_run_id}", 'type': 'new_fresh'})
    else:
        assignments.append({'part': part, 'stock_id': 'UNASSIGNED', 'type': 'error'})

# --- FINANCIAL COST MODEL EVALUATION ---
total_drops_used = len(used_drops)
total_fresh_plates_opened = len(fresh_plate_runs)

optimized_setup_cost = total_fresh_plates_opened * SETUP_TIME * MACHINE_RATE
naive_setup_cost = len(parts) * SETUP_TIME * MACHINE_RATE

print(f"--- Refined Optimization Output ---")
print(f"Parts Cut from Drops: {total_drops_used}")
print(f"Total Unique Fresh Stock Plates Loaded: {total_fresh_plates_opened}")
print(f"Optimized Setup Cost: ${optimized_setup_cost:.2f}")
print(f"Naive Baseline Setup Cost: ${naive_setup_cost:.2f}")
print(f"True Setup Cost Reduction: ${naive_setup_cost - optimized_setup_cost:.2f}")