#!/usr/bin/env python3
"""
Configuration Generator Script

Generates project-specific context engineering configuration
based on detected project type, team size, and preferences.

Usage:
    python config_generator.py --scan /path/to/project
    python config_generator.py --interactive
    python config_generator.py --type web_fullstack --team solo
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


# Project type templates
PROJECT_TEMPLATES = {
    "web_fullstack": {
        "memory": {
            "declarative_topics": [
                "user_preferences",
                "frontend_architecture", 
                "backend_architecture",
                "api_patterns",
                "data_model",
                "integrations",
                "constraints"
            ],
            "procedural_topics": [
                "data_fetching",
                "state_management",
                "error_handling",
                "testing",
                "deployment"
            ],
            "extraction_triggers": [
                "explicit_preference",
                "architecture_decision",
                "pattern_discovery",
                "error_resolution"
            ]
        },
        "sessions": {
            "mandatory_new_triggers": [
                "repository_switch",
                "feature_complete",
                "context_exhaustion"
            ],
            "recommended_new_triggers": {
                "message_count": 25,
                "duration_minutes": 90
            },
            "compaction_strategy": "recursive_summarization"
        },
        "retrieval": {
            "proactive": [
                "user_preferences",
                "active_project_context",
                "critical_constraints"
            ],
            "reactive": [
                "historical_patterns",
                "past_errors",
                "archived_decisions"
            ]
        }
    },
    
    "api_backend": {
        "memory": {
            "declarative_topics": [
                "api_design",
                "data_model",
                "auth_patterns",
                "performance_constraints",
                "integrations"
            ],
            "procedural_topics": [
                "request_handling",
                "error_responses",
                "testing",
                "debugging",
                "deployment"
            ],
            "extraction_triggers": [
                "schema_decision",
                "endpoint_pattern",
                "error_pattern"
            ]
        },
        "sessions": {
            "mandatory_new_triggers": [
                "schema_migration",
                "api_version_change",
                "feature_complete"
            ],
            "recommended_new_triggers": {
                "message_count": 30,
                "duration_minutes": 120
            },
            "compaction_strategy": "topic_filter"
        },
        "retrieval": {
            "proactive": ["api_patterns", "data_model"],
            "reactive": ["past_errors", "performance_history"]
        }
    },
    
    "mobile_app": {
        "memory": {
            "declarative_topics": [
                "platform_specifics",
                "ui_patterns",
                "offline_support",
                "device_constraints",
                "store_requirements"
            ],
            "procedural_topics": [
                "state_persistence",
                "api_integration",
                "testing",
                "release_process"
            ],
            "extraction_triggers": [
                "platform_decision",
                "ui_pattern",
                "performance_requirement"
            ]
        },
        "sessions": {
            "mandatory_new_triggers": [
                "platform_switch",
                "release_complete"
            ],
            "recommended_new_triggers": {
                "message_count": 25,
                "duration_minutes": 90
            },
            "compaction_strategy": "recursive_summarization"
        },
        "retrieval": {
            "proactive": ["platform_specifics", "ui_patterns"],
            "reactive": ["past_issues", "store_feedback"]
        }
    },
    
    "data_ml": {
        "memory": {
            "declarative_topics": [
                "data_sources",
                "transformations",
                "model_architecture",
                "evaluation_metrics",
                "infrastructure"
            ],
            "procedural_topics": [
                "data_validation",
                "experiment_tracking",
                "deployment",
                "monitoring"
            ],
            "extraction_triggers": [
                "experiment_result",
                "model_decision",
                "data_discovery"
            ]
        },
        "sessions": {
            "mandatory_new_triggers": [
                "experiment_complete",
                "data_schema_change",
                "model_version_change"
            ],
            "recommended_new_triggers": {
                "message_count": 40,
                "duration_minutes": 180
            },
            "compaction_strategy": "summarization"
        },
        "retrieval": {
            "proactive": ["current_experiment", "model_config"],
            "reactive": ["past_experiments", "failed_approaches"]
        }
    },
    
    "cli_library": {
        "memory": {
            "declarative_topics": [
                "api_surface",
                "compatibility",
                "conventions"
            ],
            "procedural_topics": [
                "testing",
                "documentation",
                "release"
            ],
            "extraction_triggers": [
                "api_decision",
                "breaking_change",
                "convention_established"
            ]
        },
        "sessions": {
            "mandatory_new_triggers": [
                "breaking_change",
                "release_complete"
            ],
            "recommended_new_triggers": {
                "message_count": 20,
                "duration_minutes": 60
            },
            "compaction_strategy": "truncation"
        },
        "retrieval": {
            "proactive": ["api_surface", "compatibility"],
            "reactive": ["past_releases", "user_feedback"]
        }
    },
    
    "generic": {
        "memory": {
            "declarative_topics": [
                "user_preferences",
                "project_architecture",
                "constraints",
                "decisions"
            ],
            "procedural_topics": [
                "development_workflow",
                "testing",
                "debugging"
            ],
            "extraction_triggers": [
                "explicit_preference",
                "decision",
                "pattern_discovery"
            ]
        },
        "sessions": {
            "mandatory_new_triggers": [
                "feature_complete",
                "context_exhaustion"
            ],
            "recommended_new_triggers": {
                "message_count": 25,
                "duration_minutes": 90
            },
            "compaction_strategy": "hybrid"
        },
        "retrieval": {
            "proactive": ["user_preferences", "active_context"],
            "reactive": ["historical_decisions", "past_errors"]
        }
    }
}

# Team size adjustments
TEAM_ADJUSTMENTS = {
    "solo": {
        "additional_topics": [],
        "compaction": "aggressive",
        "keep_recent": 8,
        "max_memories": 8
    },
    "small_team": {
        "additional_topics": ["team_conventions", "ownership"],
        "compaction": "standard",
        "keep_recent": 10,
        "max_memories": 12
    },
    "large_team": {
        "additional_topics": ["team_conventions", "ownership", "documentation_standards"],
        "compaction": "conservative",
        "keep_recent": 12,
        "max_memories": 15
    }
}


class ConfigGenerator:
    """Generates project-specific configuration."""
    
    def scan_project(self, project_path: Path) -> Dict[str, Any]:
        """Scan project directory to detect type and technology."""
        detection = {
            "frameworks": [],
            "languages": []
        }
        
        # Check for package managers / language indicators
        if (project_path / "package.json").exists():
            detection["languages"].append("javascript/typescript")
            
            try:
                with open(project_path / "package.json") as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    
                    if "next" in deps:
                        detection["frameworks"].append("nextjs")
                    if "react" in deps:
                        detection["frameworks"].append("react")
                    if "vue" in deps:
                        detection["frameworks"].append("vue")
                    if "express" in deps:
                        detection["frameworks"].append("express")
                    if "fastify" in deps:
                        detection["frameworks"].append("fastify")
            except Exception:
                pass
        
        if (project_path / "requirements.txt").exists() or (project_path / "pyproject.toml").exists():
            detection["languages"].append("python")
        
        if (project_path / "Cargo.toml").exists():
            detection["languages"].append("rust")
        
        if (project_path / "go.mod").exists():
            detection["languages"].append("go")
        
        # Check for common directories
        if (project_path / "ios").exists() or (project_path / "android").exists():
            detection["frameworks"].append("mobile")
        
        return detection
    
    def infer_project_type(self, detection: Dict[str, Any]) -> str:
        """Infer project type from detection results."""
        frameworks = detection.get("frameworks", [])
        
        if "mobile" in frameworks:
            return "mobile_app"
        
        if "nextjs" in frameworks:
            return "web_fullstack"
        
        if "react" in frameworks or "vue" in frameworks:
            return "web_fullstack"
        
        if "express" in frameworks or "fastify" in frameworks:
            return "api_backend"
        
        return "generic"
    
    def generate_config(
        self, 
        project_name: str,
        project_type: str,
        team_size: str = "solo"
    ) -> Dict[str, Any]:
        """Generate configuration for project."""
        
        template = PROJECT_TEMPLATES.get(project_type, PROJECT_TEMPLATES["generic"])
        team_adj = TEAM_ADJUSTMENTS.get(team_size, TEAM_ADJUSTMENTS["solo"])
        
        config = {
            "project": {
                "name": project_name,
                "type": project_type,
                "team_size": team_size,
                "created_at": datetime.now().isoformat()
            },
            "memory": {
                "declarative_topics": template["memory"]["declarative_topics"] + team_adj["additional_topics"],
                "procedural_topics": template["memory"]["procedural_topics"],
                "extraction_triggers": template["memory"]["extraction_triggers"],
                "confidence_threshold": 0.6
            },
            "sessions": {
                "mandatory_new_triggers": template["sessions"]["mandatory_new_triggers"],
                "recommended_new_triggers": template["sessions"]["recommended_new_triggers"],
                "compaction_strategy": template["sessions"]["compaction_strategy"],
                "keep_recent_messages": team_adj["keep_recent"]
            },
            "retrieval": {
                "proactive": template["retrieval"]["proactive"],
                "reactive": template["retrieval"]["reactive"],
                "max_memories": team_adj["max_memories"],
                "relevance_threshold": 0.7
            }
        }
        
        return config
    
    def config_to_yaml(self, config: Dict[str, Any]) -> str:
        """Convert config to YAML-like string."""
        lines = [
            f"# Context Engineering Configuration",
            f"# Generated: {config['project']['created_at']}",
            f"",
            f"project:",
            f"  name: {config['project']['name']}",
            f"  type: {config['project']['type']}",
            f"  team_size: {config['project']['team_size']}",
            f"",
            f"memory:",
            f"  declarative_topics:",
        ]
        
        for topic in config["memory"]["declarative_topics"]:
            lines.append(f"    - {topic}")
        
        lines.extend([f"", f"  procedural_topics:"])
        for topic in config["memory"]["procedural_topics"]:
            lines.append(f"    - {topic}")
        
        lines.extend([f"", f"  extraction_triggers:"])
        for trigger in config["memory"]["extraction_triggers"]:
            lines.append(f"    - {trigger}")
        
        lines.extend([
            f"",
            f"  confidence_threshold: {config['memory']['confidence_threshold']}",
            f"",
            f"sessions:",
            f"  mandatory_new_triggers:"
        ])
        
        for trigger in config["sessions"]["mandatory_new_triggers"]:
            lines.append(f"    - {trigger}")
        
        lines.extend([f"", f"  recommended_new_triggers:"])
        for key, value in config["sessions"]["recommended_new_triggers"].items():
            lines.append(f"    {key}: {value}")
        
        lines.extend([
            f"",
            f"  compaction_strategy: {config['sessions']['compaction_strategy']}",
            f"  keep_recent_messages: {config['sessions']['keep_recent_messages']}",
            f"",
            f"retrieval:",
            f"  proactive:"
        ])
        
        for item in config["retrieval"]["proactive"]:
            lines.append(f"    - {item}")
        
        lines.extend([f"", f"  reactive:"])
        for item in config["retrieval"]["reactive"]:
            lines.append(f"    - {item}")
        
        lines.extend([
            f"",
            f"  max_memories: {config['retrieval']['max_memories']}",
            f"  relevance_threshold: {config['retrieval']['relevance_threshold']}",
        ])
        
        return "\n".join(lines)


def interactive_mode() -> Dict[str, str]:
    """Run interactive configuration wizard."""
    print("\n" + "=" * 60)
    print("CONTEXT ENGINEERING CONFIGURATION WIZARD")
    print("=" * 60)
    
    project_name = input("\nProject name: ").strip() or "my_project"
    
    print("\nProject types:")
    print("  1. web_fullstack  - Full-stack web application")
    print("  2. api_backend    - API or backend service")
    print("  3. mobile_app     - Mobile application")
    print("  4. data_ml        - Data pipeline or ML project")
    print("  5. cli_library    - CLI tool or library")
    print("  6. generic        - Generic project")
    
    type_choice = input("\nSelect project type (1-6): ").strip()
    type_map = {"1": "web_fullstack", "2": "api_backend", "3": "mobile_app",
                "4": "data_ml", "5": "cli_library", "6": "generic"}
    project_type = type_map.get(type_choice, "generic")
    
    print("\nTeam size:")
    print("  1. solo        - Just you")
    print("  2. small_team  - 2-5 people")
    print("  3. large_team  - 5+ people")
    
    team_choice = input("\nSelect team size (1-3): ").strip()
    team_map = {"1": "solo", "2": "small_team", "3": "large_team"}
    team_size = team_map.get(team_choice, "solo")
    
    return {"project_name": project_name, "project_type": project_type, "team_size": team_size}


def main():
    parser = argparse.ArgumentParser(description='Generate context engineering configuration')
    parser.add_argument('--scan', type=str, help='Path to project to scan')
    parser.add_argument('--interactive', action='store_true', help='Run interactive wizard')
    parser.add_argument('--type', type=str, choices=list(PROJECT_TEMPLATES.keys()), 
                        default='generic', help='Project type')
    parser.add_argument('--team', type=str, choices=['solo', 'small_team', 'large_team'],
                        default='solo', help='Team size')
    parser.add_argument('--name', type=str, default='my_project', help='Project name')
    parser.add_argument('--output', type=str, help='Output file path')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    generator = ConfigGenerator()
    
    if args.interactive:
        params = interactive_mode()
        config = generator.generate_config(**params)
    elif args.scan:
        project_path = Path(args.scan)
        if not project_path.exists():
            print(f"Error: Path does not exist: {project_path}")
            sys.exit(1)
        
        print(f"Scanning project: {project_path}")
        detection = generator.scan_project(project_path)
        print(f"Detected languages: {detection['languages']}")
        print(f"Detected frameworks: {detection['frameworks']}")
        
        project_type = generator.infer_project_type(detection)
        print(f"Inferred type: {project_type}")
        
        config = generator.generate_config(project_path.name, project_type, args.team)
    else:
        config = generator.generate_config(args.name, args.type, args.team)
    
    if args.json:
        output = json.dumps(config, indent=2)
    else:
        output = generator.config_to_yaml(config)
    
    if args.output:
        with open(args.output, 'w') as f:
            f.write(output)
        print(f"Configuration saved to: {args.output}")
    else:
        print("\n" + "=" * 60)
        print("GENERATED CONFIGURATION")
        print("=" * 60)
        print(output)
        print("=" * 60)


if __name__ == '__main__':
    main()
