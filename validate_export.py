import pandas as pd
import json
from datetime import datetime
from pathlib import Path

def main():
    base_dir = Path(__file__).resolve().parent

    exported_path = base_dir / 'output' / 'exported_tasks.csv'
    req_path = base_dir / 'input' / 'project_requirements.txt'
    delivery_path = base_dir / 'input' / 'deliverable_structure.csv'

    df_exported = pd.read_csv(exported_path)
    with open(req_path, 'r') as f:
        requirements = json.load(f)

    df_delivery = pd.read_csv(delivery_path, sep=';')

    print("--- VALIDATION REPORT ---")
    print(f"Total exported tasks: {len(df_exported)}")
    
    # Check if milestones match
    milestones_in_export = df_exported['Milestone ID'].dropna().unique()
    print(f"Milestones in export: {sorted(list(milestones_in_export))}")
    
    req_milestones = [m.get('milestone_id') for m in requirements]
    print(f"Milestones in requirements: {sorted(req_milestones)}")

    # Check predecessors constraints
    df_exported['Start Date'] = pd.to_datetime(df_exported['Start Date'])
    df_exported['End Date'] = pd.to_datetime(df_exported['End Date'])
    
    task_dict = df_exported.set_index('Task ID').to_dict('index')

    predecessor_violations = 0
    date_violations = 0
    duration_mismatches = 0
    for task_id, row in task_dict.items():
        if pd.notna(row['Predecessor IDs']):
            preds = [int(p.strip()) for p in str(row['Predecessor IDs']).split(',')]
            for p in preds:
                if p in task_dict:
                    pred_end = task_dict[p]['End Date']
                    if row['Start Date'] < pred_end:
                        predecessor_violations += 1
                        print(f"VIOLATION: Task {task_id} starts at {row['Start Date']} before predecessor {p} ends at {pred_end}")
        
        if row['End Date'] < row['Start Date']:
            date_violations += 1
        
        # duration should match End - Start roughly (excluding non-working hours, so End - Start >= duration)
        time_diff = (row['End Date'] - row['Start Date']).total_seconds() / 60
        if time_diff < row['Duration (minutes)']:
            duration_mismatches += 1

    print(f"Predecessor logic violations: {predecessor_violations}")
    print(f"End Date < Start Date violations: {date_violations}")
    print(f"Duration physical impossibility violations: {duration_mismatches}")
    
    # Check Customization duration changes
    print("--- Customization Duration Checks ---")
    customization_length_path = base_dir / 'input' / 'customization_length.csv'
    if customization_length_path.exists():
        df_len = pd.read_csv(customization_length_path, sep=';')
        print(f"Loaded customization length: {len(df_len)} rows")
        
    customization_color_path = base_dir / 'input' / 'customization_color.csv'
    if customization_color_path.exists():
        df_color = pd.read_csv(customization_color_path, sep=';')
        print(f"Loaded customization color: {len(df_color)} rows")

    # Pick a specific customized task to check.
    # From project_requirements.txt: Milestone 1 has color: red, length: 576.
    # 60010.1 has color: red, length: 576. Check parts with part number prefix 60010
    
    parts_60010 = df_exported[df_exported['Part Number'].astype(str).str.startswith('60010')]
    print(f"Found {len(parts_60010)} parts starting with 60010")
    for idx, row in parts_60010.head(10).iterrows():
       print(f"  Task {row['Task ID']} | PN: {row['Part Number']} | Type: {row['Task Type Description']} | Dur: {row['Duration (minutes)']} | Milestone: {row['Milestone ID']}")

if __name__ == '__main__':
    main()
