import os
import sys
import unittest

import pexpect


class HandlersTest(unittest.TestCase):
    def test_handlers(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        child = pexpect.spawn(
            "ansible-playbook playbook.yaml",
            cwd="tests/handlers",
            env={
                "PATH": "%s:%s"
                % (
                    os.path.join(dir_path, "..", "venv", "bin"),
                    os.environ.get("PATH", "/bin"),
                ),
                "AOT_LOGGING": "true",
            },
        )
        child.logfile = sys.stdout.buffer
        child.expect("OT: opentracing.tracer initialized")
        child.expect("PLAY")
        child.expect("TASK.*task 1")
        child.expect("OT: Reporting span .*?:1 Ansible.Running on localhost")

        child.expect("PLAY RECAP")
        child.expect("ok=2")
        child.expect("changed=1")
        child.expect("unreachable=0")
        child.expect("skipped=0")
        child.expect("rescued=0")
        child.expect("ignored=0")
