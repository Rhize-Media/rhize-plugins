#!/usr/bin/env python3
"""
Emergency error triage script for production incidents.
Quickly assesses error severity and impact to guide response.
"""

import json
import sys
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Any

class ErrorTriageSystem:
    def __init__(self):
        self.severity_levels = {
            'P0': 'Complete outage or data loss',
            'P1': 'Critical feature broken, >100 users affected',
            'P2': 'Important feature degraded, 10-100 users affected',
            'P3': 'Minor feature issue, <10 users affected',
            'P4': 'Cosmetic or edge case issue'
        }
        
    def assess_severity(self, error_data: Dict[str, Any]) -> str:
        """Determine error severity based on impact metrics."""
        user_count = error_data.get('user_count', 0)
        error_rate = error_data.get('error_rate', 0)
        is_payment = 'payment' in error_data.get('title', '').lower()
        is_auth = 'auth' in error_data.get('title', '').lower()
        
        # P0: Complete outage
        if error_rate > 90:
            return 'P0'
        
        # P1: Critical features or many users
        if is_payment or is_auth or user_count > 100:
            return 'P1'
        
        # P2: Important features
        if user_count > 10 or error_rate > 50:
            return 'P2'
        
        # P3: Some users affected
        if user_count > 0:
            return 'P3'
        
        # P4: Edge cases
        return 'P4'
    
    def get_response_actions(self, severity: str) -> List[str]:
        """Get required actions based on severity."""
        actions = {
            'P0': [
                'Page on-call engineer immediately',
                'Create war room channel',
                'Update status page',
                'Begin rollback procedure',
                'Notify executives'
            ],
            'P1': [
                'Notify on-call engineer',
                'Create incident channel',
                'Update status page',
                'Consider rollback',
                'Prepare customer communication'
            ],
            'P2': [
                'Create incident ticket',
                'Notify team via Slack',
                'Monitor for escalation',
                'Schedule fix for next deploy'
            ],
            'P3': [
                'Create bug ticket',
                'Add to sprint backlog',
                'Monitor error rate'
            ],
            'P4': [
                'Log for future reference',
                'Consider in next refactor'
            ]
        }
        return actions.get(severity, [])
    
    def generate_incident_command(self, error_data: Dict[str, Any], severity: str) -> str:
        """Generate incident management commands."""
        if severity in ['P0', 'P1']:
            return f"""
# IMMEDIATE ACTIONS REQUIRED

## 1. Create Incident Channel
/incident create "{error_data.get('title', 'Production Error')}" --severity {severity}

## 2. Page On-Call
/page oncall --priority {severity} --message "{error_data.get('title', '')}"

## 3. Begin Investigation
- Sentry Issue: {error_data.get('sentry_url', 'N/A')}
- Affected Users: {error_data.get('user_count', 0)}
- Error Rate: {error_data.get('error_rate', 0)}%
- First Seen: {error_data.get('first_seen', 'Unknown')}

## 4. Rollback Command (if needed)
vercel rollback --team your-team --project your-project

## 5. Status Page Update
"Service degradation detected. Team is investigating."
"""
        else:
            return f"""
# Non-Critical Error Detected

## Create Ticket
- Title: {error_data.get('title', 'Error')}
- Priority: {severity}
- Affected Users: {error_data.get('user_count', 0)}

## Monitor
- Set up alert for escalation
- Review in next standup
"""
    
    def check_recent_deployments(self) -> List[Dict]:
        """Check for recent deployments that might have caused the error."""
        # This would integrate with Vercel API
        # Placeholder for demonstration
        return [
            {
                'id': 'dpl_1',
                'created': datetime.now() - timedelta(hours=1),
                'commit': 'abc123',
                'author': 'developer@example.com',
                'message': 'feat: updated payment processing'
            }
        ]
    
    def triage(self, error_title: str, error_count: int = 1, user_count: int = 0):
        """Main triage function."""
        print("=" * 60)
        print("🚨 ERROR TRIAGE SYSTEM")
        print("=" * 60)
        
        # Simulate getting error data (would come from Sentry API)
        error_data = {
            'title': error_title,
            'error_count': error_count,
            'user_count': user_count,
            'error_rate': min(100, (error_count / 100) * 100),  # Simplified
            'first_seen': datetime.now() - timedelta(minutes=30),
            'last_seen': datetime.now(),
            'sentry_url': 'https://sentry.io/issues/12345'
        }
        
        # Assess severity
        severity = self.assess_severity(error_data)
        
        print(f"\n📊 ERROR ASSESSMENT")
        print(f"Title: {error_title}")
        print(f"Severity: {severity} - {self.severity_levels[severity]}")
        print(f"Users Affected: {user_count}")
        print(f"Occurrences: {error_count}")
        print(f"Error Rate: {error_data['error_rate']:.1f}%")
        
        # Get response actions
        actions = self.get_response_actions(severity)
        print(f"\n✅ REQUIRED ACTIONS:")
        for i, action in enumerate(actions, 1):
            print(f"{i}. {action}")
        
        # Check recent deployments
        deployments = self.check_recent_deployments()
        if deployments:
            print(f"\n🔄 RECENT DEPLOYMENTS:")
            for dep in deployments:
                print(f"- {dep['created'].strftime('%H:%M')} - {dep['message']} ({dep['commit'][:7]})")
        
        # Generate incident commands
        commands = self.generate_incident_command(error_data, severity)
        print(f"\n💻 COMMANDS TO RUN:")
        print(commands)
        
        # Save triage report
        report = {
            'timestamp': datetime.now().isoformat(),
            'error': error_data,
            'severity': severity,
            'actions': actions,
            'recent_deployments': [
                {**d, 'created': d['created'].isoformat()} 
                for d in deployments
            ]
        }
        
        with open('triage-report.json', 'w') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n📁 Full report saved to: triage-report.json")
        
        # Return exit code based on severity
        if severity in ['P0', 'P1']:
            return 1  # Critical
        return 0  # Non-critical

if __name__ == '__main__':
    triage_system = ErrorTriageSystem()
    
    # Parse command line arguments
    if len(sys.argv) > 1:
        error_title = sys.argv[1]
        error_count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        user_count = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    else:
        # Interactive mode
        error_title = input("Error title: ")
        error_count = int(input("Error count (default 1): ") or "1")
        user_count = int(input("Users affected (default 0): ") or "0")
    
    exit_code = triage_system.triage(error_title, error_count, user_count)
    sys.exit(exit_code)
