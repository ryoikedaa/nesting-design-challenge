import json
import math

#  Shop Constraints & Financial Rates 
MACHINE_RATE = 85.0 / 60.0  # $1.4167 per minute
SETUP_TIME = 15.0          # minutes ($21.25 flat setup cost)
KERF = 0.125               # 1/8th inch saw blade width
MIN_DROP_SHORT_SIDE = 6.0  # Hard machine safety/clamping threshold
HORIZON_MONTHS = 6.0

# Material Properties & Base Weights
DENSITY = {"6061-T6": 0.0975, "7075-T6": 0.1010}
MAT_PRICE = {"6061-T6": 4.20, "7075-T6": 7.50}

with open('data/jobs.json') as f:
    jobs = json.load(f)
with open('data/inventory.json') as f:
    inventory = json.load(f)
with open('data/order_history.json') as f:
    history = json.load(f)

# 1. Historical Demand & Valuation Engine
dates = sorted(h["ordered_at"] for h in history)
y0, m0 = int(dates[0][:4]), int(dates[0][5:7])
y1, m1 = int(dates[-1][:4]), int(dates[-1][5:7])
SPAN_MONTHS = (y1 - y0) * 12 + (m1 - m0) + 1

def fits(p_w, p_l, s_w, s_l):
    """Checks structural sizing parameters including 90-degree rotations."""
    return (p_w <= s_w and p_l <= s_l) or (p_l <= s_w and p_w <= s_l)

def get_expected_value(alloy, thick, w, l):
    """Calculates economic opportunity cost based on Poisson re-use probability."""
    area = w * l
    if min(w, l) < MIN_DROP_SHORT_SIDE:
        return 0.0  # Safety violation = completely worthless to store
        
    matched, util_sum = 0, 0.0
    for h in history:
        if h["alloy"] != alloy or h["thickness_in"] != thick:
            continue
        if not fits(h["width_in"], h["length_in"], w, l):
            continue
            
        matched += 1
        def n_fit(dim, part):
            return int((dim + KERF) // (part + KERF))
            
        max_fit = max(
            n_fit(w, h["width_in"]) * n_fit(l, h["length_in"]),
            n_fit(w, h["length_in"]) * n_fit(l, h["width_in"]),
        )
        used_area = h["width_in"] * h["length_in"] * min(h["quantity"], max_fit)
        util_sum += min(used_area / area, 1.0)
        
    lam = matched / SPAN_MONTHS
    p_reuse = 1.0 - math.exp(-lam * HORIZON_MONTHS)
    e_util = (util_sum / matched) if matched else 0.0
    
    raw_material_cost = area * DENSITY[alloy] * thick * MAT_PRICE[alloy]
    return raw_material_cost * p_reuse * e_util

# Separate inventory sources
drops = [item for item in inventory if item['kind'] == 'drop']
plates = [item for item in inventory if item['kind'] == 'plate']

# Calculate initial asset values of drops in inventory
for d in drops:
    d['calculated_value'] = get_expected_value(d['alloy'], d['thickness_in'], d['width_in'], d['length_in'])

# Flatten active demand and sort descending by surface area
parts = []
for job in jobs:
    for part in job['parts']:
        part['order_id'] = job['order_id']
        parts.append(part)
parts.sort(key=lambda p: p['width_in'] * p['length_in'], reverse=True)

#2. Dynamic Algorithmic Nesting Engine 
used_drops = set()
assignments = []
fresh_plate_runs = []

for part in parts:
    p_w, p_l = part['width_in'], part['length_in']
    
    # Track matching valid drops that conform to physical safety rules
    matching_drops = [
        d for d in drops 
        if d['id'] not in used_drops 
        and d['alloy'] == part['alloy'] 
        and abs(d['thickness_in'] - part['thickness_in']) < 0.01 
        and fits(p_w, p_l, d['width_in'], d['length_in'])
        and min(d['width_in'], d['length_in']) >= MIN_DROP_SHORT_SIDE
    ]
    
    if matching_drops:
        # Select the drop that minimizes financial opportunity cost
        best_drop = min(matching_drops, key=lambda d: d['calculated_value'])
        used_drops.add(best_drop['id'])
        assignments.append({
            'part': part, 
            'stock_id': best_drop['id'], 
            'type': 'drop', 
            'cost': best_drop['calculated_value']
        })
        continue

    # Area-based packaging tracker across active raw plate layouts
    packed_successfully = False
    for run in fresh_plate_runs:
        if run['alloy'] == part['alloy'] and abs(run['thickness'] - part['thickness_in']) < 0.01:
            used_area = run['used_area']
            total_area = run['plate_spec']['width_in'] * run['plate_spec']['length_in']
            part_area = (p_w + KERF) * (p_l + KERF)
            
            if total_area - used_area >= part_area and fits(p_w, p_l, run['plate_spec']['width_in'], run['plate_spec']['length_in']):
                run['used_area'] += part_area
                run['parts'].append(part)
                assignments.append({
                    'part': part, 
                    'stock_id': f"Fresh-Plate-Run-{run['id']}", 
                    'type': 'packed_fresh', 
                    'cost': 0.0  # Shared overhead setup penalty
                })
                packed_successfully = True
                break
                
    if packed_successfully:
        continue

    # Open a new raw factory sheet SKU
    matching_plates = [
        p for p in plates 
        if p['alloy'] == part['alloy'] 
        and abs(p['thickness_in'] - part['thickness_in']) < 0.01
        and fits(p_w, p_l, p['width_in'], p['length_in'])
    ]
    
    if matching_plates:
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
        assignments.append({
            'part': part, 
            'stock_id': f"Fresh-Plate-Run-{new_run_id}", 
            'type': 'new_fresh', 
            'cost': SETUP_TIME * MACHINE_RATE
        })
    else:
        assignments.append({'part': part, 'stock_id': 'UNASSIGNED', 'type': 'error', 'cost': 0.0})

# ---- 3. Financial Optimization Diagnostics ----
total_drops_used = len(used_drops)
total_fresh_plates_opened = len(fresh_plate_runs)

optimized_setup_cost = total_fresh_plates_opened * SETUP_TIME * MACHINE_RATE
naive_setup_cost = len(parts) * SETUP_TIME * MACHINE_RATE
total_opportunity_cost = sum(d['calculated_value'] for d in drops if d['id'] in used_drops)

print(f"--- Refined Optimization Output ---")
print(f"Parts Cut from Drops: {total_drops_used}")
print(f"Total Unique Fresh Stock Plates Loaded: {total_fresh_plates_opened}")
print(f"Optimized Labor Setup Cost: ${optimized_setup_cost:.2f}")
print(f"Total Drop Opportunity Cost Consumed: ${total_opportunity_cost:.2f}")
print(f"Naive Baseline Setup Cost: ${naive_setup_cost:.2f}")
print(f"Net Setup Expense Savings: ${naive_setup_cost - optimized_setup_cost:.2f}")