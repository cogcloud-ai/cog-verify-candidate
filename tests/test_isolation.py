"""Process limits and real Docker confinement; no model calls."""
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'));sys.path.insert(0,str(ROOT.parent/'cog-workbench/src'))
from isolated_execution import ExecutionSuite, capture
from workbench_suite import Suite, package_digest

class LimitsTests(unittest.TestCase):
    def test_timeout_kills_process_group(self):
        result=capture([sys.executable,'-c','import time;time.sleep(30)'],ROOT,os.environ,1,1024)
        self.assertEqual(result['execution_status'],'timeout');self.assertLess(result['elapsed_seconds'],3)
    def test_combined_output_is_bounded(self):
        result=capture([sys.executable,'-c',"import sys;sys.stdout.write('x'*1000000);sys.stdout.flush()"],ROOT,os.environ,3,1024)
        self.assertEqual(result['execution_status'],'output-limit');self.assertEqual(len(result['stdout'].encode())+len(result['stderr'].encode()),1024)
    def test_nonzero_exit_is_retained(self):
        result=capture([sys.executable,'-c',"print('diagnostic');raise SystemExit(7)"],ROOT,os.environ,3,1024)
        self.assertEqual(result['exit_code'],7);self.assertIn('diagnostic',result['stdout'])
    def test_exited_process_group_permission_race_retains_observation(self):
        with patch('isolated_execution.os.killpg', side_effect=PermissionError):
            result=capture([sys.executable,'-c',"print('x'*100000)"],ROOT,os.environ,3,1024)
        self.assertEqual(result['execution_status'],'output-limit')

    def test_docker_requires_pinned_image_without_host_fallback(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            base=Suite(ROOT.parent,Path(folder)/'state',journal=lambda _:None)
            with self.assertRaisesRegex(ValueError,'pinned'):
                ExecutionSuite(base,[ROOT],{'mode':'docker','image':'python:latest'})

@unittest.skipUnless(os.environ.get('COG_VERIFY_ISOLATION_IMAGE'),'Set COG_VERIFY_ISOLATION_IMAGE to run actual container policy checks')
class DockerTests(unittest.TestCase):
    def test_files_network_environment_and_limits(self):
        with tempfile.TemporaryDirectory(dir=ROOT.parent) as folder:
            package=Path(folder)/'candidate';package.mkdir()
            (package/'src').mkdir()
            (package/'src/probe.py').write_text('''import os,socket\nfrom pathlib import Path\nassert 'COG_PRIVATE_TEST_SECRET' not in os.environ\nassert os.getuid()==65534\nassert Path('/sys/fs/cgroup/memory.max').read_text().strip()=='268435456'\nassert Path('/sys/fs/cgroup/pids.max').read_text().strip()=='64'\nfor target in ['/candidate/src/changed','/etc/changed','/host/secret']:\n try: Path(target).write_text('changed')\n except OSError: pass\n else: raise AssertionError(target)\ns=socket.socket();s.settimeout(.5)\ntry:s.connect(('1.1.1.1',443))\nexcept OSError:pass\nelse:raise AssertionError('network')\nPath('/tmp/allowed').write_text('bounded temp')\nprint('confined')\n''')
            (package/'pixi.toml').write_text('''[workspace]\nname="probe"\nversion="0.1.0"\n[tasks]\ntest="python src/probe.py"\n[tool.cog]\nschema="openteams/cog-manifest [0.1]"\nid="test/probe"\nkind="code"\nrequires=[]\nreaches=[]\ninterfaces=[]\n''')
            base=Suite(ROOT.parent,Path(folder)/'state',journal=lambda _:None)
            suite=ExecutionSuite(base,[package],{'mode':'docker','image':os.environ['COG_VERIFY_ISOLATION_IMAGE'],'timeout_seconds':10})
            before=package_digest(package)
            with patch.dict(os.environ, {'COG_PRIVATE_TEST_SECRET': 'host-only-secret'}):
                result=suite.call(package,'test',expect_json=False)
            self.assertEqual(result['exit_code'],0,result);self.assertIn('confined',result['stdout'])
            self.assertEqual(package_digest(package),before)
            # Exercise regular-file bundle mounts under restrictive host umask.
            manifest = package / 'pixi.toml'
            manifest.write_text(manifest.read_text().replace('interfaces=[]',
                'interfaces=[{name="run",audience="usage",kind="command",task="run"}]').replace(
                'test="python src/probe.py"', 'test="python src/probe.py"\nrun="python src/probe.py"'))
            (package / 'src/probe.py').write_text("import json,sys;print(json.dumps(json.load(open(sys.argv[2]))))")
            bundle = Path(folder) / 'bundle.json'; bundle.write_text('{"ready":true}'); bundle.chmod(0o600)
            self.assertEqual(suite.call(package, 'run', ['--bundle', bundle]), {'ready': True})
            (package/'src/probe.py').write_text('import time;time.sleep(30)')
            suite.policy['timeout_seconds']=1
            timed=suite.call(package,'test',expect_json=False)
            self.assertEqual(timed['execution_status'],'timeout')
            self.assertEqual(timed['container_cleanup'],'removed')
            (package/'src/probe.py').write_text("print('x'*1000000)")
            suite.policy['timeout_seconds']=10;suite.policy['output_bytes']=1024
            self.assertEqual(suite.call(package,'test',expect_json=False)['execution_status'],'output-limit')
