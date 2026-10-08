"""Bounded declared Python operations; explicit Docker policy never falls back."""
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import subprocess
import sys
import time
import uuid
from workbench_suite import Suite, digest, require, tomllib


def capture(argv, cwd, env, seconds, limit):
    start = time.monotonic()
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, start_new_session=True)
    streams = selectors.DefaultSelector()
    streams.register(proc.stdout, selectors.EVENT_READ, 'stdout')
    streams.register(proc.stderr, selectors.EVENT_READ, 'stderr')
    output = {'stdout': bytearray(), 'stderr': bytearray()}
    status = 'exited'
    try:
        while streams.get_map():
            if time.monotonic() - start >= seconds:
                status = 'timeout'; break
            for key, _ in streams.select(min(.05, max(0, seconds - (time.monotonic() - start)))):
                chunk = os.read(key.fd, 8192)
                if not chunk:
                    streams.unregister(key.fileobj); continue
                remaining = limit - sum(map(len, output.values()))
                output[key.data].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    status = 'output-limit'; break
            if status != 'exited': break
        if status != 'exited':
            os.killpg(proc.pid, signal.SIGKILL)
        try: code = proc.wait(timeout=max(.01, seconds - (time.monotonic()-start)))
        except subprocess.TimeoutExpired:
            status = 'timeout'; os.killpg(proc.pid, signal.SIGKILL); code = proc.wait()
        return {'exit_code': code if status == 'exited' else 124,
                'execution_status': status, 'elapsed_seconds': round(time.monotonic()-start, 3),
                **{key: value.decode('utf-8', errors='replace') for key, value in output.items()}}
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL); proc.wait()
        streams.close(); proc.stdout.close(); proc.stderr.close()


class ExecutionSuite(Suite):
    def __init__(self, base, roots, policy):
        self.__dict__.update(base.__dict__)
        self.execution_roots = {base.root(root) for root in roots}
        self.policy = {'mode': 'trusted-local', 'timeout_seconds': 60, 'output_bytes': 1048576, **(policy or {})}
        require(self.policy['mode'] in ('trusted-local', 'docker'), 'Unknown execution policy.')
        require(type(self.policy['timeout_seconds']) is int and 1 <= self.policy['timeout_seconds'] <= 600, 'Invalid execution timeout.')
        require(type(self.policy['output_bytes']) is int and 1024 <= self.policy['output_bytes'] <= 16777216, 'Invalid output limit.')
        self.execution_records = []
        if self.policy['mode'] == 'docker':
            image = self.policy.get('image', '')
            require(bool(re.fullmatch(r'(sha256:[a-f0-9]{64}|[^ ]+@sha256:[a-f0-9]{64})', image)), 'Docker policy requires a pinned local image ID or digest.')
            inspect = subprocess.run(['docker', 'image', 'inspect', '--format', '{{.Id}} {{.Os}} {{.Architecture}}', image], capture_output=True, text=True, timeout=15)
            require(inspect.returncode == 0, 'Pinned Docker image is unavailable; build/load it first. No host fallback.')
            self.policy.update(image_identity=inspect.stdout.strip(), network='none', filesystem='read-only candidate and input mounts; writable bounded /tmp only',
                               cpus=1, memory_bytes=268435456, pids=64, user='65534:65534', capabilities='none', no_new_privileges=True)
        else:
            self.policy.update(environment_identity={'python': sys.version, 'platform': sys.platform},
                               network='ambient', filesystem='ambient', resource_isolation=False)
        self.policy_sha256 = digest(self.policy)

    def call(self, root, task, args=(), timeout=240, expect_json=True, stdout_limit=30000):
        root = self.root(root)
        if root not in self.execution_roots:
            return super().call(root, task, args, timeout, expect_json, stdout_limit)
        manifest = self.manifest(root)
        require(manifest.get('kind') == 'code' and not manifest.get('requires') and not manifest.get('reaches'), 'Only pure-code execution is supported.')
        allowed = {x.get('task') for x in manifest.get('interfaces', [])} | {'test', 'eval', 'check'}
        require(task in allowed, 'Operation is not declared by candidate.')
        with (root/'pixi.toml').open('rb') as stream: declared = tomllib.load(stream).get('tasks', {}).get(task)
        if isinstance(declared, dict): declared = declared.get('cmd')
        require(isinstance(declared, str), 'Missing task declaration.')
        argv = shlex.split(declared)
        require(argv and argv[0] in ('python', 'python3') and not any(x in (';', '&&', '|', '||', '>', '<') for x in argv), 'Isolation supports declared Python argv tasks only.')
        container = None
        env = {k:v for k,v in os.environ.items() if not k.startswith('PIXI_')}
        if self.policy['mode'] == 'docker':
            container = 'cog-verify-' + uuid.uuid4().hex
            mounts = ['--mount', 'type=bind,src='+str(root)+',dst=/candidate,readonly']
            mapped = []
            for arg in args:
                path = Path(str(arg))
                if path.is_absolute():
                    require(path.is_file() and not path.is_symlink(), 'Only regular input files may be mounted.')
                    target = '/inputs/'+str(len(mapped))
                    require(',' not in str(path), 'Unsupported mount path.')
                    mounts += ['--mount', 'type=bind,src='+str(path)+',dst='+target+',readonly']; mapped.append(target)
                else: mapped.append(str(arg))
            require(',' not in str(root), 'Unsupported candidate mount path.')
            argv = ['docker', 'run', '--name', container, '--pull', 'never', '--network', 'none', '--read-only',
                    '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--user', '65534:65534',
                    '--cpus', '1', '--memory', '256m', '--memory-swap', '256m', '--pids-limit', '64',
                    '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m', '--workdir', '/candidate',
                    '--env', 'PYTHONDONTWRITEBYTECODE=1', '--env', 'HOME=/tmp', *mounts,
                    '--entrypoint', 'python', self.policy['image'], *argv[1:], *mapped]
        else:
            python = root/'.pixi/envs/default/bin/python'
            argv[0] = str(python) if python.is_file() else sys.executable
            argv += list(map(str, args))
        self.journal('suite-isolated-operation-start', cog=manifest['id'], task=task, policy_sha256=self.policy_sha256)
        try:
            raw = capture(argv, root, env, self.policy['timeout_seconds'], self.policy['output_bytes'])
        finally:
            if container:
                subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        raw.update(task=task, cog=manifest['id'], policy_sha256=self.policy_sha256)
        path = self.save('execution-observations', raw)
        raw['record_path'] = path
        self.execution_records.append(raw)
        self.journal('suite-isolated-operation-exit', task=task, exit_code=raw['exit_code'], record_path=path)
        if task != 'test' and raw['execution_status'] != 'exited':
            raise ValueError(raw['execution_status'] + '; bounded observation retained at '+path)
        if not expect_json: return raw
        require(raw['exit_code'] == 0, 'Declared operation failed; retained at '+path)
        return json.loads(raw['stdout'])
