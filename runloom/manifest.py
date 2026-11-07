"""Declarative, shell-free command manifests. Manifests are trusted local code."""
from copy import deepcopy
import math
from pathlib import Path
import re
import shutil
import sys

APP_ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r'\{([A-Za-z_][A-Za-z0-9_-]*)\}')
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*$')
TYPES = {'string', 'number', 'boolean', 'select', 'file', 'folder'}


def _finite_number(value):
    try:
        return type(value) in (int,float) and math.isfinite(value)
    except OverflowError:
        return False


def _validate_unicode(value):
    """JSON permits lone surrogates, but SQLite and Windows paths cannot."""
    if isinstance(value,str):
        try: value.encode('utf-8')
        except UnicodeEncodeError: raise ValueError('Text contains an invalid Unicode surrogate') from None
    elif isinstance(value,dict):
        for key,item in value.items():
            _validate_unicode(key)
            _validate_unicode(item)
    elif isinstance(value,list):
        for item in value: _validate_unicode(item)


def validate_manifest(data):
    if not isinstance(data, dict):
        raise ValueError('Manifest must be a JSON object')
    _validate_unicode(data)
    m = deepcopy(data)
    if type(m.get('schema_version')) is not int or m['schema_version'] != 1:
        raise ValueError('schema_version must be 1')
    for key in ('id', 'name', 'executable'):
        if not isinstance(m.get(key), str) or not m[key].strip() or '\0' in m[key]:
            raise ValueError(f'{key} must be a nonempty string')
    if not IDENTIFIER.fullmatch(m['id']):
        raise ValueError('Task id must contain letters, digits, underscores or hyphens')
    for key, default in [('description',''), ('category','General'), ('cwd','{app}')]:
        m.setdefault(key, default)
        if not isinstance(m[key], str) or '\0' in m[key]:
            raise ValueError(f'{key} must be a string without NUL characters')
    if not m['cwd'].strip():
        raise ValueError('cwd must be a nonempty directory path')
    for key in ('allow_parallel', 'preview'):
        m.setdefault(key, False)
        if not isinstance(m[key], bool):
            raise ValueError(f'{key} must be boolean')
    m.setdefault('timeout', 3600)
    if not _finite_number(m['timeout']) or m['timeout'] <= 0:
        raise ValueError('timeout must be a positive finite number of seconds')
    m.setdefault('args', [])
    if not isinstance(m['args'], list) or any(not isinstance(a,str) or '\0' in a for a in m['args']):
        raise ValueError('args must be an array of strings without NUL characters')
    m.setdefault('parameters', [])
    if not isinstance(m['parameters'], list):
        raise ValueError('parameters must be an array')
    ids = set()
    for p in m['parameters']:
        if not isinstance(p,dict) or not isinstance(p.get('id'),str) or not IDENTIFIER.fullmatch(p['id']):
            raise ValueError('Every parameter requires a valid id')
        if p['id'] in ids or p['id'] in ('app','python'):
            raise ValueError(f'Duplicate or reserved parameter id: {p["id"]}')
        ids.add(p['id'])
        p.setdefault('type','string')
        p.setdefault('label',p['id'])
        if not isinstance(p['type'],str) or p['type'] not in TYPES:
            raise ValueError(f'Unknown parameter type: {p["type"]}')
        if not isinstance(p['label'],str) or not p['label'].strip() or '\0' in p['label']:
            raise ValueError(f'{p["id"]}: label must be nonempty text')
        for flag in ('required','secret'):
            if flag in p and not isinstance(p[flag],bool):
                raise ValueError(f'{p["id"]}: {flag} must be boolean')
        if p['type'] == 'select' and (not isinstance(p.get('options'),list) or not p['options'] or any(not isinstance(x,str) for x in p['options'])):
            raise ValueError(f'{p["id"]}: select requires nonempty string options')
        for bound in ('min','max'):
            if bound in p and not _finite_number(p[bound]):
                raise ValueError(f'{p["id"]}: {bound} must be a finite number')
        if 'min' in p and 'max' in p and p['min'] > p['max']:
            raise ValueError(f'{p["id"]}: min exceeds max')
        if 'default' in p:
            default = p['default']
            if p['type'] == 'boolean':
                if not isinstance(default,bool): raise ValueError(f'{p["id"]}: boolean default must be true or false')
            elif p['type'] == 'number':
                if not _finite_number(default):
                    raise ValueError(f'{p["id"]}: numeric default must be finite')
                if ('min' in p and default < p['min']) or ('max' in p and default > p['max']):
                    raise ValueError(f'{p["id"]}: default is outside the allowed range')
            elif not isinstance(default,str) or '\0' in default:
                raise ValueError(f'{p["id"]}: default must be text without NUL characters')
            elif p['type'] == 'select' and default and default not in p['options']:
                raise ValueError(f'{p["id"]}: default is not an available option')
    for text in [m['executable'],m['cwd'],*m['args']]:
        for name in TOKEN.findall(text):
            if name not in ids | {'app','python'}:
                raise ValueError(f'Unknown placeholder: {{{name}}}')
    if 'schedule' in m:
        from .scheduler import next_run
        schedule = m['schedule']
        if not isinstance(schedule,dict): raise ValueError('schedule must be an object')
        if 'enabled' in schedule and not isinstance(schedule['enabled'],bool):
            raise ValueError('schedule.enabled must be boolean')
        if not isinstance(schedule.get('values',{}),dict): raise ValueError('schedule.values must be an object')
        if set(schedule.get('values',{})) - ids: raise ValueError('schedule.values contains an unknown parameter')
        for key in ('next_at','last_at'):
            value = schedule.get(key)
            if value is not None and not _finite_number(value):
                raise ValueError(f'schedule.{key} must be a finite timestamp')
        next_run({**schedule,'enabled':True},0)
        if schedule.get('enabled',True) and any(p.get('secret') for p in m['parameters']):
            raise ValueError('Tasks with secret parameters must be run manually')
        if schedule.get('enabled',True):
            unscheduled = dict(m)
            unscheduled.pop('schedule')
            schedule['values'] = validate_values(unscheduled,schedule.get('values',{}))
    return m


def validate_values(manifest, values):
    m = validate_manifest(manifest)
    if not isinstance(values,dict):
        raise ValueError('Parameter values must be an object')
    _validate_unicode(values)
    result = {}
    for p in m['parameters']:
        key, kind = p['id'], p['type']
        value = values.get(key,p.get('default',False if kind == 'boolean' else ''))
        if value is None: value = ''
        if value == '' and p.get('required'):
            raise ValueError(f'{p["label"]} is required')
        if kind == 'boolean':
            if isinstance(value,str) and value.lower() in ('true','false','1','0',''):
                value = value.lower() in ('true','1')
            if not isinstance(value,bool):
                raise ValueError(f'{p["label"]} must be true or false')
        elif kind == 'number' and value != '':
            try:
                if isinstance(value,bool): raise ValueError()
                value = float(value)
                if not math.isfinite(value): raise ValueError()
            except (TypeError,ValueError,OverflowError):
                raise ValueError(f'{p["label"]} must be a finite number') from None
            if ('min' in p and value < p['min']) or ('max' in p and value > p['max']):
                raise ValueError(f'{p["label"]} is outside the allowed range')
            if value.is_integer(): value = int(value)
        else:
            if not isinstance(value,str):
                raise ValueError(f'{p["label"]} must be text')
            if '\0' in value: raise ValueError(f'{p["label"]} contains a NUL character')
            if kind == 'select' and value != '' and value not in p['options']:
                raise ValueError(f'{p["label"]} is not an available option')
        result[key] = value
    return result


def substitute(text, values):
    python = sys.executable
    if getattr(sys,'frozen',False):
        # The frozen desktop executable is not a general Python interpreter.
        python = shutil.which('python') or 'python'
    bindings = {**values, 'app':str(APP_ROOT), 'python':python}
    def replace(match):
        value = bindings[match.group(1)]
        return str(value).lower() if isinstance(value,bool) else str(value)
    return TOKEN.sub(replace,text)


def bind_command(manifest, values):
    m = validate_manifest(manifest)
    values = validate_values(m, values)
    return [substitute(part,values) for part in [m['executable'],*m['args']]]
