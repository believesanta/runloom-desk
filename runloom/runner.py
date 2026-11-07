"""Observable shell-free subprocess execution with bounded logs and cancellation."""
import codecs
import ctypes
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import threading
import time

from .manifest import bind_command, substitute, validate_manifest, validate_values

LOG_LIMIT = 262144
LINE_LIMIT = 16384


class _WindowsJob:
    """Kill all assigned descendants when the job handle closes."""
    def __init__(self, process):
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('per_process',ctypes.c_int64),('per_job',ctypes.c_int64),('flags',wintypes.DWORD),('min_ws',ctypes.c_size_t),('max_ws',ctypes.c_size_t),('active',wintypes.DWORD),('affinity',ctypes.c_size_t),('priority',wintypes.DWORD),('scheduling',wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(name,ctypes.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_ = [('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        self.api = ctypes.WinDLL('kernel32',use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p,wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE,wintypes.HANDLE]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.CreateJobObjectW(None,None)
        info = Extended()
        info.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.handle or not self.api.SetInformationJobObject(self.handle,9,ctypes.byref(info),ctypes.sizeof(info)) or not self.api.AssignProcessToJobObject(self.handle,wintypes.HANDLE(int(process._handle))):
            error = ctypes.get_last_error()
            self.close()
            raise OSError(error,'Cannot establish Windows process-tree ownership')

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None

    @staticmethod
    def resume(process):
        # subprocess closes the primary thread handle. NtResumeProcess resumes
        # the suspended process after assignment, eliminating the spawn/assign race.
        ntdll = ctypes.WinDLL('ntdll')
        ntdll.NtResumeProcess.argtypes = [ctypes.c_void_p]
        ntdll.NtResumeProcess.restype = ctypes.c_long
        result = ntdll.NtResumeProcess(ctypes.c_void_p(int(process._handle)))
        if result != 0:
            raise OSError(f'Cannot resume owned process (NTSTATUS {result:#x})')


class Runner:
    def __init__(self, store):
        self.store = store
        self.events = queue.Queue(maxsize=1024)
        self.active = {}
        self._lock = threading.RLock()
        self._closing = False

    def _event(self, run_id, kind, **data):
        event = dict(run_id=run_id,type=kind,**data)
        try: self.events.put_nowait(event)
        except queue.Full:
            # Latest snapshot is durable; queue must never block process drainage.
            try: self.events.get_nowait()
            except queue.Empty: pass
            try: self.events.put_nowait(event)
            except queue.Full: pass

    def start(self, manifest, values, preview=False):
        m = validate_manifest(manifest)
        values = validate_values(m,values)
        if preview and not m['preview']:
            raise ValueError('This task does not support preview')
        command = bind_command(m,values)
        if preview: command.append('--preview')
        secret_values = [values[p['id']] for p in m['parameters'] if p.get('secret') and values[p['id']] != '']
        secrets = set()
        for value in secret_values:
            text = str(value).lower() if isinstance(value,bool) else str(value)
            # Cover native line endings and JSON wire escapes as well as decoded
            # protocol text. Multiline values must not leak one line at a time.
            for variant in (text, *text.splitlines(), text.replace('\n','\r\n')):
                if variant:
                    secrets.update((variant, json.dumps(variant,ensure_ascii=True)[1:-1], json.dumps(variant,ensure_ascii=False)[1:-1]))
        secrets = sorted(secrets,key=len,reverse=True)
        def redact(text):
            for secret in secrets: text = text.replace(secret,'••••')
            return text.encode('utf-8',errors='replace').decode('utf-8')
        with self._lock:
            if self._closing: raise ValueError('Runner is shutting down')
            if not m['allow_parallel'] and any(v['task_id'] == m['id'] for v in self.active.values()):
                raise ValueError('This task is already running')
            rid = self.store.create_run(dict(task_id=m['id'],task_name=m['name'],name=m['name'],status='queued',
                values={k:('••••' if any(p['id']==k and p.get('secret') for p in m['parameters']) else v) for k,v in values.items()},
                command=[redact(x) for x in command],cwd=redact(substitute(m['cwd'],values)),logs='',artifacts=[],progress=None,
                preview=bool(preview),started_at=None,finished_at=None,exit_code=None,error=None))
            entry = dict(task_id=m['id'],cancel=threading.Event(),process=None,thread=None)
            thread = threading.Thread(target=self._work,args=(rid,m,values,command,redact,entry,secrets),daemon=True,name=f'runloom-{rid[:8]}')
            entry['thread'] = thread
            self.active[rid] = entry
            self._event(rid,'run',status='queued')
            thread.start()
        return rid

    def cancel(self, run_id):
        with self._lock:
            entry = self.active.get(run_id)
            if entry: entry['cancel'].set()

    def shutdown(self):
        with self._lock:
            self._closing = True
            entries = list(self.active.values())
            for entry in entries: entry['cancel'].set()
        for entry in entries:
            entry['thread'].join(timeout=12)

    def _kill(self, process, job):
        if job:
            job.close()
        elif os.name == 'nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW,timeout=5)
        else:
            try: os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        if process.poll() is None: process.kill()

    def _work(self, rid, manifest, values, command, redact, entry, secrets):
        process = job = reader = None
        logs = ''
        artifacts = []
        progress = None
        status = 'failed'
        error = None
        exit_code = None
        raw = queue.Queue(maxsize=128)
        reader_stop = threading.Event()
        reader_done = threading.Event()
        def feed(text):
            nonlocal logs,progress
            payload = None
            if len(text) <= LINE_LIMIT:
                try: payload = json.loads(text)
                except (ValueError,TypeError): pass
            if isinstance(payload,dict) and type(payload.get('runloom')) is int and payload['runloom'] == 1:
                kind = payload.get('type')
                if kind == 'progress' and type(payload.get('value')) in (int,float) and 0 <= payload['value'] <= 100:
                    progress = payload['value']
                    self._event(rid,'progress',value=progress)
                    return
                if kind == 'artifact' and isinstance(payload.get('path'),str) and '\0' not in payload['path']:
                    try:
                        payload['path'].encode('utf-8')
                        path = redact(str((cwd / payload['path']).resolve()))
                    except (OSError,ValueError,UnicodeError):
                        pass  # Malformed protocol remains visible as ordinary output.
                    else:
                        if path not in artifacts and len(artifacts) < 1000:
                            artifacts.append(path)
                            self._event(rid,'artifact',path=path)
                        return
                if kind == 'message': text = str(payload.get('message',payload.get('text',''))) + '\n'
            text = redact(text)
            logs = (logs + text)[-LOG_LIMIT:]
            self._event(rid,'log',text=text)
        try:
            directory = substitute(manifest['cwd'],values)
            if not directory.strip(): raise ValueError('Working directory is empty')
            cwd = Path(directory).expanduser().resolve()
            if not cwd.is_dir(): raise ValueError(f'Working directory does not exist: {cwd}')
            executable = command[0]
            if not Path(executable).is_absolute() and (os.sep in executable or '/' in executable or '\\' in executable):
                executable = str(cwd / executable)
            resolved = shutil.which(executable)
            if not resolved or not Path(resolved).is_file(): raise ValueError(f'Executable not found: {command[0]}')
            if os.name == 'nt' and Path(resolved).suffix.lower() in ('.bat','.cmd'):
                raise ValueError('Use an explicit interpreter executable instead of a .bat or .cmd file')
            if entry['cancel'].is_set():
                status = 'cancelled'
                return
            env = dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',RUNLOOM_PREVIEW='1' if '--preview' in command else '0')
            process = subprocess.Popen([resolved,*command[1:]],cwd=str(cwd),stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,stderr=subprocess.STDOUT,bufsize=0,env=env,
                creationflags=(subprocess.CREATE_NO_WINDOW | 0x4) if os.name == 'nt' else 0,start_new_session=os.name != 'nt')
            entry['process'] = process
            if os.name == 'nt':
                job = _WindowsJob(process)
                job.resume(process)
            self.store.update_run(rid,status='running',started_at=time.time(),pid=process.pid)
            self._event(rid,'run',status='running')
            def read_output():
                decoder = codecs.getincrementaldecoder('utf-8')('replace')
                try:
                    while not reader_stop.is_set():
                        block = process.stdout.read(4096)
                        if not block: break
                        text = decoder.decode(block)
                        while not reader_stop.is_set():
                            try: raw.put(text,timeout=.05); break
                            except queue.Full: pass
                    tail = decoder.decode(b'',final=True)
                    while tail and not reader_stop.is_set():
                        try: raw.put(tail,timeout=.05); break
                        except queue.Full: pass
                finally:
                    reader_done.set()
            reader = threading.Thread(target=read_output,daemon=True,name=f'output-{rid[:8]}')
            reader.start()
            started = time.monotonic()
            last_save = started
            pending = ''
            terminated = False
            exited_at = None
            status = 'running'
            while True:
                now = time.monotonic()
                alive = process.poll() is None
                if not alive and exited_at is None:
                    exited_at = now
                    if job: job.close()  # includes children retaining stdout
                    elif os.name != 'nt':
                        try: os.killpg(process.pid,signal.SIGKILL)
                        except ProcessLookupError: pass
                if alive and not terminated and (entry['cancel'].is_set() or now-started >= manifest['timeout']):
                    status = 'cancelled' if entry['cancel'].is_set() else 'timed_out'
                    self._kill(process,job)
                    terminated = True
                try:
                    chunk = raw.get(timeout=.03)
                    pending += chunk
                except queue.Empty: pass
                while '\n' in pending:
                    line,pending = pending.split('\n',1)
                    feed(line+'\n')
                # Leave sufficient suffix to avoid splitting a secret between chunks.
                reserve = max([len(s) for s in secrets] or [1])
                if len(pending) > LINE_LIMIT + reserve:
                    safe = len(pending)-reserve
                    # Redact before cutting, then retain the raw suffix for matching.
                    for secret in secrets:
                        left = pending.rfind(secret,0,safe+len(secret))
                        if left >= 0 and left < safe < left+len(secret): safe = left
                    feed(pending[:safe]); pending = pending[safe:]
                if now-last_save > .25:
                    self.store.update_run(rid,logs=logs,artifacts=artifacts,progress=progress)
                    last_save = now
                if exited_at is not None and reader_done.is_set() and raw.empty(): break
            if pending: feed(pending)
            exit_code = process.wait(timeout=5)
            if status == 'running': status = 'succeeded' if exit_code == 0 else 'failed'
            if status == 'failed': error = f'Process exited with code {exit_code}'
            if status == 'timed_out': error = f'Time limit of {manifest["timeout"]} seconds exceeded'
        except Exception as exc:
            error = redact(str(exc))
            status = 'cancelled' if entry['cancel'].is_set() else 'failed'
        finally:
            if process is not None:
                try:
                    if process.poll() is None: self._kill(process,job)
                    process.wait(timeout=5)
                except Exception: pass
            if job: job.close()
            reader_stop.set()
            if reader: reader.join(timeout=2)
            if process and process.stdout: process.stdout.close()
            with self._lock:
                self.store.update_run(rid,status=status,logs=logs,artifacts=artifacts,progress=progress,error=error,
                                      exit_code=exit_code,finished_at=time.time())
                self.active.pop(rid,None)
            self._event(rid,'run',status=status)
