"""Optional Sentry completion signal. No report/source content leaves the host."""
import json
from pathlib import Path
import re
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlsplit, urljoin
import uuid


def check_in(config_path, run_id, status):
    if not config_path:
        return {'status':'disabled'}
    try:
        config = json.loads(Path(config_path).read_text())
        if set(config) != {'organization', 'monitor_slug', 'environment', 'keychain_service'}:
            raise ValueError('invalid_monitor_config')
        if status not in {'in_progress', 'ok', 'error'}:
            raise ValueError('invalid_status')
        for field in ('organization','monitor_slug','environment'):
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,80}', config[field]):
                raise ValueError('invalid_monitor_identity')
        credential = subprocess.run(['/usr/bin/security','find-generic-password','-s',config['keychain_service'],'-w'],
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3)
        if credential.returncode:
            return {'status':'failed','reason':'monitor_credential_unavailable'}
        dsn = credential.stdout.decode().strip()
        parsed = urlsplit(dsn)
        if parsed.scheme != 'https' or not parsed.hostname or not parsed.hostname.endswith('.sentry.io') or not parsed.username or parsed.password or not parsed.path.strip('/').isdigit() or parsed.query or parsed.fragment:
            raise ValueError('invalid_dsn')
        check_id = uuid.UUID(run_id).hex
        url = urljoin('https://' + parsed.hostname, 'api/' + parsed.path.strip('/') + '/envelope/')
        payload = json.dumps({'check_in_id':check_id, 'monitor_slug':config['monitor_slug'],
                              'status':status, 'environment':config['environment']}).encode()
        envelope = (json.dumps({'dsn':dsn}).encode() + b'\n' +
                    json.dumps({'type':'check_in','length':len(payload)}).encode() + b'\n' + payload + b'\n')
        request = urllib.request.Request(url, data=envelope,
                   headers={'Content-Type':'application/x-sentry-envelope'}, method='POST')
        with urllib.request.urlopen(request, timeout=5) as response:
            if response.status not in (200,201,202):
                raise ValueError('checkin_rejected')
        return {'status':'accepted'}
    except (OSError, ValueError, TypeError, KeyError, subprocess.TimeoutExpired, urllib.error.URLError):
        return {'status':'failed','reason':'monitor_delivery_failed'}
