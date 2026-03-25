import csv
import os

def generate_rst(csv_path, output_path):
    requirements = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        for row in reader:
            if row.get('ID'):
                requirements.append(row)

    # Sort requirements into Functional and Non-Functional
    functional = [r for r in requirements if r['Type'].lower() == 'functional']
    non_functional = [r for r in requirements if r['Type'].lower() == 'non-functional' or r['Type'].lower() == 'non functional']

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("System Specifications\n")
        f.write("=====================\n\n")
        f.write("This page presents the comprehensive list of functional (RF) and non-functional (RNF) requirements that dictate the behavior and constraints of the Chrono Tailoring software.\n\n")

        def write_group(title, data):
            f.write(f"{title}\n")
            f.write("-" * len(title) + "\n\n")
            
            # Group by Category
            categories = {}
            for r in data:
                cat = r['Category']
                if cat not in categories:
                    categories[cat] = []
                categories[cat].append(r)
            
            for cat, reqs in categories.items():
                f.write(f"{cat}\n")
                f.write("^" * len(cat) + "\n\n")
                
                for r in reqs:
                    req_id = r['ID']
                    title = r['Title']
                    f.write(f"{req_id}: {title}\n")
                    f.write("~" * (len(req_id) + len(title) + 2) + "\n\n")
                    
                    f.write(f"**Description**\n    {r['Description']}\n\n")
                    if r['Intention'].strip():
                        f.write(f"**Intention**\n    {r['Intention']}\n\n")
                    if r['Example'].strip():
                        f.write(f"**Example**\n    ``{r['Example']}``\n\n")
                    if r['Implementation'].strip():
                        # Link if possible or just bold
                        f.write(f"**Source Traceability**\n    {r['Implementation']}\n\n")
                    
                    f.write("\n")

        write_group("Functional Requirements", functional)
        write_group("Non-Functional Requirements", non_functional)

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    generate_rst(
        os.path.join(base_dir, 'input', 'system_specifications.csv'),
        os.path.join(base_dir, 'docs', 'requirements.rst')
    )
