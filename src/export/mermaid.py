from typing import List, Optional
from datetime import datetime, timedelta
from pathlib import Path
from src.core.models import ProjectMilestone
from src.config import DEBUG

def export_tasks_to_mermaid_graph(milestones: List[ProjectMilestone], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid flowchart (graph TD) representation of tasks, grouped by milestone.
    Can generate a detailed graph of individual tasks or a high-level graph based on task types.
    """
    mermaid_lines = ["graph TD"]
    all_tasks = [task for milestone in milestones for task in milestone.tasks]

    def sanitize_id(text: str) -> str:
        return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

    if detail_level == 'full':
        node_styles = []

        task_type_colors = {
            'release': 'fill:#F96',
            'drawing': 'fill:#9F6',
            'part_model': 'fill:#69F',
            'part_list': 'fill:#FC6',
            'milestone': 'fill:#C6F'
        }

        for milestone in milestones:
            mermaid_lines.append(f"    subgraph M_{milestone.name}[Milestone {milestone.name}]")
            
            for task in milestone.tasks:
                init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
                end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'

                shape_map = {
                    'release': '[[{}]]',
                    'drawing': '({})',
                    'part_model': '({})',
                    'part_list': '{{{}}}',
                    'milestone': '(( {} ))'
                }
                shape_template = shape_map.get(task.type.description, '[{}]')

                node_label_content = (f"{task.name}<br>"
                                      f"Type: {task.type.description}<br>"
                                      f"Part No: {task.part_number}<br>"
                                      f"Init: {init_date_str}<br>"
                                      f"End: {end_date_str}<br>"
                                      f"Dur: {task.duration_minutes}min")
                
                node_definition = f"{task.id}{shape_template.format(node_label_content)}"
                mermaid_lines.append(f"        {node_definition}")

                color_style = task_type_colors.get(task.type.description, 'fill:#CCC')
                node_styles.append(f"        style {task.id} {color_style}")
            mermaid_lines.append("    end")
        
        for task in all_tasks:
            for successor_task in getattr(task, 'successors_tasks', []):
                if any(s_task.id == successor_task.id for m in milestones for s_task in m.tasks):
                    mermaid_lines.append(f"    {task.id} --> {successor_task.id}")
        
        mermaid_lines.extend(node_styles)

    elif detail_level == 'type':
        for milestone in milestones:
            mermaid_lines.append(f"    subgraph M_{milestone.name}[Milestone {milestone.name} (Types)]")
            
            unique_task_types_in_milestone = set()
            type_dependencies_in_milestone = set()

            for task in milestone.tasks:
                source_type_desc = task.type.description
                unique_task_types_in_milestone.add(source_type_desc)

                for successor_task in getattr(task, 'successors_tasks', []):
                    # We assume task grouping allows resolving milestone membership implicitly 
                    if hasattr(successor_task, 'part_number') and str(successor_task.part_number) == str(milestone.name):
                        target_type_desc = successor_task.type.description
                        unique_task_types_in_milestone.add(target_type_desc)
                        type_dependencies_in_milestone.add((source_type_desc, target_type_desc))

            for type_desc in sorted(list(unique_task_types_in_milestone)):
                sanitized_id = sanitize_id(type_desc)
                mermaid_lines.append(f"        {sanitized_id}_{milestone.name}[{type_desc}]")

            for source_type_desc, target_type_desc in sorted(list(type_dependencies_in_milestone)):
                sanitized_source_id = sanitize_id(source_type_desc)
                sanitized_target_id = sanitize_id(target_type_desc)
                mermaid_lines.append(f"        {sanitized_source_id}_{milestone.name} --> {sanitized_target_id}_{milestone.name}")
            mermaid_lines.append("    end")
        
        # Simplify global dependency logic - rely on tasks part numbers for mapping if crossing 
        global_type_dependencies = set()
        for task in all_tasks:
            for successor_task in getattr(task, 'successors_tasks', []):
                if str(task.part_number) != str(successor_task.part_number) and task.part_number != '70000':
                    source_type_desc = task.type.description
                    target_type_desc = successor_task.type.description
                    global_type_dependencies.add((str(task.part_number), source_type_desc, str(successor_task.part_number), target_type_desc))

        for source_mid, source_td, target_mid, target_td in sorted(list(global_type_dependencies)):
            sanitized_source_id_node = sanitize_id(source_td) + f"_{source_mid}"
            sanitized_target_id_node = sanitize_id(target_td) + f"_{target_mid}"
            mermaid_lines.append(f"    {sanitized_source_id_node} --> {sanitized_target_id_node}")

    elif detail_level == 'milestone':
        milestone_dependencies = set()
        task_to_milestone_map = {task.id: milestone.name for milestone in milestones for task in milestone.tasks}

        for milestone in milestones:
            sanitized_milestone_id = sanitize_id(str(milestone.name))
            mermaid_lines.append(f"    {sanitized_milestone_id}[Milestone {milestone.name}]")

            for task in milestone.tasks:
                for successor_task in getattr(task, 'successors_tasks', []):
                    successor_milestone_id = task_to_milestone_map.get(successor_task.id)
                    if successor_milestone_id and str(successor_milestone_id) != str(milestone.name):
                        milestone_dependencies.add((str(milestone.name), str(successor_milestone_id)))
        
        for source_milestone_id, target_milestone_id in sorted(list(milestone_dependencies), key=lambda x: (x[0], x[1])):
            sanitized_source_milestone_id = sanitize_id(source_milestone_id)
            sanitized_target_milestone_id = sanitize_id(target_milestone_id)
            mermaid_lines.append(f"    {sanitized_source_milestone_id} --> {sanitized_target_milestone_id}")

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full', 'type', or 'milestone'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            if DEBUG:
                print(f"Mermaid graph exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid graph to {output_file_path}: {e}")
            
    return mermaid_syntax

def export_tasks_to_mermaid_gantt(milestones: List[ProjectMilestone], output_file_path: Optional[Path] = None, detail_level: str = 'full') -> str:
    """
    Generates a Mermaid Gantt chart representation of tasks, grouped by milestone.
    """
    mermaid_lines = [
        "gantt",
        "    dateFormat  YYYY-MM-DD",
        "    axisFormat %d-%m",
        "    title       Task Schedule Overview",
        "    excludes    weekends"
    ]

    def sanitize_id(text: str) -> str:
        return text.replace(" ", "_").replace("-", "_").replace(".", "").lower()

    if detail_level == 'full':
        for milestone in milestones:
            mermaid_lines.append(f"    section Milestone {milestone.name}")
            
            for task in milestone.tasks:
                init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
                end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'
                
                task_duration_mermaid_format = ""
                if task.duration_minutes is not None:
                    total_minutes = task.duration_minutes
                    days = total_minutes // (8 * 60)
                    hours = (total_minutes % (8 * 60)) // 60
                    minutes = total_minutes % 60
                    
                    if days > 0:
                        task_duration_mermaid_format += f"{days}d "
                    if hours > 0:
                        task_duration_mermaid_format += f"{hours}h "
                    if minutes > 0:
                        task_duration_mermaid_format += f"{minutes}m "
                    
                    if not task_duration_mermaid_format:
                        task_duration_mermaid_format = "0d"
                    else:
                        task_duration_mermaid_format = task_duration_mermaid_format.strip()
                
                task_duration_mermaid_format = "0d" if task.type.description == "milestone" else task_duration_mermaid_format

                task_label_gantt = f"{task.name} ({task.part_number})"

                if task.init_date and task.end_date:
                    mermaid_lines.append(f"    {task_label_gantt} :{task.id}, {init_date_str}, {end_date_str}")
                else:
                    mermaid_lines.append(f"    {task_label_gantt} :{task.id}, {init_date_str}, {task_duration_mermaid_format}")

    elif detail_level == 'type':
        all_tasks = [task for milestone in milestones for task in milestone.tasks]
        mermaid_lines.append("    section Task Types Overview")
        type_date_spans = {} 

        for task in all_tasks:
            type_desc = task.type.description
            if type_desc not in type_date_spans:
                type_date_spans[type_desc] = {
                    'min_init': task.init_date, 
                    'max_end': task.end_date, 
                    'total_duration': timedelta(minutes=0)
                }
            
            if task.init_date and (type_date_spans[type_desc]['min_init'] is None or type_date_spans[type_desc]['min_init'] > task.init_date):
                type_date_spans[type_desc]['min_init'] = task.init_date
            
            if task.end_date and (type_date_spans[type_desc]['max_end'] is None or type_date_spans[type_desc]['max_end'] < task.end_date):
                type_date_spans[type_desc]['max_end'] = task.end_date
            
            type_date_spans[type_desc]['total_duration'] += timedelta(minutes=task.duration_minutes)
        
        for type_desc in sorted(type_date_spans.keys()):
            type_info = type_date_spans[type_desc]
            
            total_seconds = type_info['total_duration'].total_seconds()
            total_minutes = int(total_seconds / 60)
            
            duration_parts = []
            if total_minutes >= (8 * 60):
                days = total_minutes // (8 * 60)
                duration_parts.append(f"{days}d")
                total_minutes %= (8 * 60)
            
            if total_minutes >= 60:
                hours = total_minutes // 60
                duration_parts.append(f"{hours}h")
                total_minutes %= 60
            
            if total_minutes > 0:
                duration_parts.append(f"{total_minutes}m")
            
            duration_display = " ".join(duration_parts) if duration_parts else "0m"

            min_init_str = type_info['min_init'].strftime('%Y-%m-%d') if type_info['min_init'] else 'None'
            max_end_str = type_info['max_end'].strftime('%Y-%m-%d') if type_info['max_end'] else 'None'

            if type_desc == "milestone":
                type_label = type_desc
                duration_mermaid_format = "0d"
            else:
                type_label = f"{type_desc} ({duration_display})"
                duration_mermaid_format = f"{min_init_str}, {max_end_str}"

            mermaid_lines.append(f"    {type_label} :{sanitize_id(type_desc)}, {duration_mermaid_format}")
    
    elif detail_level == 'milestone_type_summary':
        for milestone in milestones:
            mermaid_lines.append(f"    section {milestone.name}")

            tasks_to_summarize = []
            individual_tasks = []
            
            for task in milestone.tasks:
                if task.type.description == "milestone" or str(task.part_number) == str(milestone.name):
                    individual_tasks.append(task)
                else:
                    tasks_to_summarize.append(task)

            type_date_spans_in_milestone = {}

            for task in tasks_to_summarize:
                type_desc = task.type.description
                if type_desc not in type_date_spans_in_milestone:
                    type_date_spans_in_milestone[type_desc] = {
                        'min_init': task.init_date,
                        'max_end': task.end_date,
                        'total_duration': timedelta(minutes=0)
                    }
                if task.init_date and (type_date_spans_in_milestone[type_desc]['min_init'] is None or type_date_spans_in_milestone[type_desc]['min_init'] > task.init_date):
                    type_date_spans_in_milestone[type_desc]['min_init'] = task.init_date
                if task.end_date and (type_date_spans_in_milestone[type_desc]['max_end'] is None or type_date_spans_in_milestone[type_desc]['max_end'] < task.end_date):
                    type_date_spans_in_milestone[type_desc]['max_end'] = task.end_date
                type_date_spans_in_milestone[type_desc]['total_duration'] += timedelta(minutes=task.duration_minutes)

            for type_desc in sorted(type_date_spans_in_milestone.keys()):
                type_info = type_date_spans_in_milestone[type_desc]
                
                total_seconds = type_info['total_duration'].total_seconds()
                total_minutes = int(total_seconds / 60)
                
                duration_parts = []
                if total_minutes >= (8 * 60):
                    days = total_minutes // (8 * 60)
                    duration_parts.append(f"{days}d")
                    total_minutes %= (8 * 60)
                if total_minutes >= 60:
                    hours = total_minutes // 60
                    duration_parts.append(f"{hours}h")
                    total_minutes %= 60
                if total_minutes > 0:
                    duration_parts.append(f"{total_minutes}m")
                duration_display = " ".join(duration_parts) if duration_parts else "0m"

                min_init_str = type_info['min_init'].strftime('%Y-%m-%d') if type_info['min_init'] else 'None'
                max_end_str = type_info['max_end'].strftime('%Y-%m-%d') if type_info['max_end'] else 'None'

                type_label = f"{type_desc} {milestone.name} ({duration_display})"
                duration_mermaid_format = f"{min_init_str}, {max_end_str}"
                mermaid_task_id = f"{sanitize_id(type_desc)}_{milestone.name}"
                
                mermaid_lines.append(f"    {type_label} :{mermaid_task_id}, {duration_mermaid_format}")

            for task in individual_tasks:
                init_date_str = task.init_date.strftime('%Y-%m-%d') if task.init_date else 'None'
                end_date_str = task.end_date.strftime('%Y-%m-%d') if task.end_date else 'None'
                
                task_duration_mermaid_format = ""
                if task.duration_minutes is not None:
                    total_minutes = task.duration_minutes
                    days = total_minutes // (8 * 60)
                    hours = (total_minutes % (8 * 60)) // 60
                    minutes = total_minutes % 60
                    
                    if days > 0: task_duration_mermaid_format += f"{days}d "
                    if hours > 0: task_duration_mermaid_format += f"{hours}h "
                    if minutes > 0: task_duration_mermaid_format += f"{minutes}m "
                    task_duration_mermaid_format = task_duration_mermaid_format.strip() if task_duration_mermaid_format else "0d"

                if task.type.description == "milestone":
                    type_label = str(milestone.name)
                    duration_mermaid_format = "0d"
                    mermaid_task_id = "milestone"
                else:
                    if task.name == "storage_cabinet":
                        type_label = f"{milestone.name} {task.type.description} ({task_duration_mermaid_format})"
                    else:
                        type_label = f"{task.name} ({task_duration_mermaid_format})"
                    
                    duration_mermaid_format = f"{init_date_str}, {end_date_str}"
                    mermaid_task_id = str(task.id)
                    
                mermaid_lines.append(f"    {type_label} :{mermaid_task_id}, {duration_mermaid_format}")

    else:
        raise ValueError(f"Unknown detail_level: {detail_level}. Expected 'full' or 'type'.")
            
    mermaid_syntax = "\n".join(mermaid_lines)

    if output_file_path:
        try:
            output_file_path.write_text(mermaid_syntax)
            if DEBUG:
                print(f"Mermaid Gantt chart exported to: {output_file_path}")
        except Exception as e:
            print(f"Error exporting Mermaid Gantt chart to {output_file_path}: {e}")
            
    return mermaid_syntax
