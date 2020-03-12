import os
import sys
import unittest

import pexpect


class DoubleTest(unittest.TestCase):
    def test_double(self):
        dir_path = os.path.dirname(os.path.realpath(__file__))
        child = pexpect.spawn(
            "ansible-playbook playbook.yaml",
            cwd="tests/double",
            env={
                "PATH": os.path.join(dir_path, "..", "venv", "bin"),
                "AOT_LOGGING": "true",
            },
        )
        child.logfile = sys.stdout.buffer
        child.expect("OT: opentracing.tracer initialized")
        child.expect("PLAY")
        child.expect("TASK.*task 1")
        child.expect("OT: Reporting span (.*?):.*:(.*):1 Ansible.Running on localhost")
        id = child.match.groups()[0].decode()
        rid = child.match.groups()[1].decode()

        child.expect(f"OT: Reporting span {id}:.*:{rid}:1 Ansible.Running on 127.0.0.1")

        child.expect("TASK.*task 2")
        child.expect(f"OT: Reporting span {id}:(.*) Ansible.Running on localhost")

        child.expect("TASK.*task 3")
        child.expect(f"OT: Reporting span {id}:.*:(.*):1 Ansible.Running on localhost")
        run_id = child.match.groups()[0].decode()

        child.expect("PLAY RECAP")
        child.expect("ok=3")
        child.expect("changed=0")
        child.expect("unreachable=0")
        child.expect("skipped=0")
        child.expect("rescued=0")
        child.expect("ignored=1")

        child.expect(f"OT: Reporting span {id}:{run_id}:(.*?):1 Ansible.Task task 3")
        play_id = child.match.groups()[0].decode()

        child.expect(f"OT: Reporting span {id}:{play_id}:(.*?):1 Ansible.Play")
        playbook_id = child.match.groups()[0].decode()

        child.expect(f"OT: Reporting span {id}:{playbook_id}:(.*?):1 Ansible.Playbook")
        ansible_id = child.match.groups()[0].decode()

        child.expect(f"OT: Reporting span {id}:{ansible_id}:0:1 Ansible.Ansible")
