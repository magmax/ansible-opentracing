import logging
import os
import platform
import time
import traceback

from ansible.plugins.callback import CallbackBase
from jaeger_client import Config


def init_tracer(service):
    if "AOT_LOGGING" in os.environ.keys():
        logging.getLogger("").handlers = []
        logging.basicConfig(format="OT: %(message)s", level=logging.DEBUG)

    config = Config(
        config={
            "sampler": {"type": "const", "param": os.environ.get("AOT_SAMPLER_RATE", 1)},
            "local_agent": {
                "reporting_host": os.environ.get("AOT_JAEGER_HOST", "localhost"),
                "reporting_port": os.environ.get("AOT_JAEGER_PORT", "5775"),
            },
            "logging": True,
        },
        service_name=service,
    )

    return config.initialize_tracer()


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 0.1
    CALLBACK_TYPE = "aggregate"
    CALLBACK_NAME = "org.magmax.ansible.opentracing"
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        self._tracer = init_tracer("Ansible")
        self._scope = self._tracer.start_active_span("Ansible")
        super(CallbackModule, self).__init__()

        self._playbook_scope = None
        self._play_scope = None
        self._task_scope = None
        self._runner_spans = {}

        self._spans = [self._scope]
        self._namedspans = {}
        self._scope.span.set_tag(
            "callback.name", getattr(self, "CALLBACK_NAME", "unnamed")
        )
        self._scope.span.set_tag("callback.type", getattr(self, "CALLBACK_TYPE", "old"))
        self._scope.span.set_tag("callback.version", getattr(self, "CALLBACK_VERSION"))
        self._scope.span.set_tag("disabled", getattr(self, "disabled", False))
        self._scope.span.set_tag("system.python.version", platform.python_version())
        self._scope.span.set_tag("system.user", os.environ.get("USER"))
        self._scope.span.set_tag("system.hostname", platform.node())
        self._scope.span.set_tag("system.type", platform.platform())
        for k, v in getattr(self, "_plugin_options", {}).items():
            self._scope.span.set_tag("option.{k}", v)

    def _add_span(self, name):
        scope = self._tracer.start_active_span(name)
        self._spans.append(scope)
        return scope

    def v2_playbook_on_start(self, playbook):
        self._playbook_scope = self._tracer.start_active_span("Playbook")
        super().v2_playbook_on_start(playbook)
        span = self._playbook_scope.span
        span.set_tag("playbook.basedir", getattr(playbook, "_basedir", None))
        span.set_tag("playbook.filename", getattr(playbook, "_file_name", None))
        span.set_tag("playbook.entries", len(getattr(playbook, "_entries", [])))

    def playbook_on_stats(self, stats):
        super().playbook_on_stats(stats)
        print("Sending final stats to Opentracing server...")
        while self._spans:
            self._spans.pop().close()
        if self._task_scope:
            self._task_scope.close()
        if self._play_scope:
            self._play_scope.close()
        self._playbook_scope.close()
        self._scope.close()
        time.sleep(2)
        self._tracer.close()

    def v2_playbook_on_play_start(self, play):
        if self._play_scope:
            self._play_scope.close()
        self._play_scope = self._tracer.start_active_span("Play")
        super().v2_playbook_on_play_start(play)
        atts = [
            "name",
            "become",
            "tags",
            "hosts",
            "ignore_errors",
            "only_tags",
            "gather_facts",
        ]
        for att in atts:
            self._play_scope.span.set_tag(f"play.{att}", getattr(play, att, None))

    def v2_playbook_on_no_hosts_remaining(self):
        with self._tracer.start_active_span("No Hosts Remaining") as scope:
            scope.span.log_kv({"stacktrace": "\n".join(traceback.format_stack())})

    def v2_playbook_on_no_hosts_matched(self):
        with self._tracer.start_active_span("No Hosts Matched") as scope:
            scope.span.log_kv({"stacktrace": "\n".join(traceback.format_stack())})

    def v2_playbook_on_task_start(self, task, is_conditional):
        if self._task_scope:
            self._task_scope.close()
            for span in self._runner_spans.values():
                span.finish()
            self._runner_spans = {}
        self._task_scope = self._tracer.start_active_span(f"Task {task.get_name()}")
        super().v2_playbook_on_task_start(task, is_conditional)
        atts = ["name", "become"]
        for att in atts:
            self._task_scope.span.set_tag(f"task.{att}", getattr(task, att, None))

    def v2_playbook_on_handler_task_start(self, task):
        self.v2_playbook_on_task_start(task, None)
        self._task_scope.span.set_tag("handler", True)

    #    def on_any(self, *args, **kwargs):
    #        with self._tracer.start_active_span("on_any") as scope:
    #            super().on_any(*args, **kwargs)
    #            scope.span.log_kv({'stacktrace': '\n'.join(traceback.format_stack())})
    #            if args:
    #                scope.span.set_tag('args_add', str(args))
    #            for k, v in kwargs.items():
    #                scope.span.set_tag(f'kwargs_add_{k}', str(v))

    # def v2_on_any(self, *args, **kwargs):
    #    with self._tracer.start_active_span("v2_on_any") as scope:
    #        super().v2_on_any(*args, **kwargs)
    #        scope.span.log_kv(
    #            {'stacktrace': '\n'.join(traceback.format_stack(limit=4))}
    #        )
    #        if args:
    #            scope.span.set_tag('args_add', str(args))
    #        for k, v in kwargs.items():
    #            scope.span.set_tag(f'kwargs_add_{k}', str(v))
    #    def v2_on_any(self, *args, **kwargs):
    #        with self._tracer.start_active_span("v2_on_any") as scope:
    #            super().v2_on_any(*args, **kwargs)
    #            scope.span.log_kv(
    #                {'stacktrace': '\n'.join(traceback.format_stack(limit=4))}
    #            )
    #            if args:
    #                scope.span.set_tag('args_add', str(args))
    #            for k, v in kwargs.items():
    #                scope.span.set_tag(f'kwargs_add_{k}', str(v))

    def _add_result_tags(self, span, result):
        span.set_tag("result.is_changed", result.is_changed())
        span.set_tag("result.is_skipped", result.is_skipped())
        span.set_tag("result.is_failed", result.is_failed())
        span.set_tag("result.is_unreachable", result.is_unreachable())

    def v2_runner_on_start(self, host, task):
        span = self._tracer.start_span(f"Running on {host}")
        super().v2_runner_on_start(host, task)
        self._runner_spans[host] = span
        span.set_tag("task.host", host)
        atts = ["name", "become"]
        for att in atts:
            span.set_tag(f"task.{att}", getattr(task, att, None))

    def v2_runner_on_ok(self, result):
        super().v2_runner_on_ok(result)
        span = self._runner_spans[result._host]
        self._add_result_tags(span, result)
        span.finish()
        del self._runner_spans[result._host]

    def v2_runner_on_failed(self, result, ignore_errors=False):
        super().v2_runner_on_failed(result, ignore_errors)
        span = self._runner_spans[result._host]
        span.set_tag("result.ignore_errors", ignore_errors)
        span.set_tag("error", True)
        self._add_result_tags(span, result)
        span.finish()
        del self._runner_spans[result._host]
