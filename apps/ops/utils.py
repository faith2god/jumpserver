# ~*~ coding: utf-8 ~*~
import re

import time
from django.utils import timezone

from common.utils import get_logger, get_object_or_none, get_short_uuid_str
from .ansible import AdHocRunner, CommandResultCallback
from .inventory import JMSInventory
from .ansible.exceptions import AnsibleError
from .models import AdHocRunHistory, Task, AdHoc

logger = get_logger(__file__)
UUID_PATTERN = re.compile(r'[0-9a-zA-Z\-]{36}')


def is_uuid(s):
    if UUID_PATTERN.match(s):
        return True
    else:
        return False


def record_adhoc(func):
    def _deco(adhoc, **options):
        record = AdHocRunHistory(adhoc=adhoc)
        time_start = time.time()
        try:
            result = func(adhoc, **options)
            record.is_finished = True
            if result.results_summary.get('dark'):
                record.is_success = False
            else:
                record.is_success = True
            record.result = result.results_raw
            record.summary = result.results_summary
            return result
        finally:
            record.date_finished = timezone.now()
            record.timedelta = time.time() - time_start
            record.save()
    return _deco


def get_adhoc_inventory(adhoc):
    if adhoc.become:
        become_info = {
            'become': {
               adhoc.become
            }
        }
    else:
        become_info = None

    inventory = JMSInventory(
        adhoc.hosts, run_as_admin=adhoc.run_as_admin,
        run_as=adhoc.run_as, become_info=become_info
    )
    return inventory


def get_inventory(hostname_list, run_as_admin=False, run_as=None, become_info=None):
    return JMSInventory(
        hostname_list, run_as_admin=run_as_admin,
        run_as=run_as, become_info=become_info
    )


def get_adhoc_runner(hostname_list, run_as_admin=False, run_as=None, become_info=None):
    inventory = get_inventory(
        hostname_list, run_as_admin=run_as_admin,
        run_as=run_as, become_info=become_info
    )
    runner = AdHocRunner(inventory)
    return runner


@record_adhoc
def run_adhoc_object(adhoc, **options):
    """
    :param adhoc: Instance of AdHoc
    :param options: ansible support option, like forks ...
    :return:
    """
    name = adhoc.task.name
    inventory = get_adhoc_inventory(adhoc)
    runner = AdHocRunner(inventory)
    for k, v in options:
        runner.set_option(k, v)

    try:
        result = runner.run(adhoc.tasks, adhoc.pattern, name)
        return result
    except AnsibleError as e:
        logger.error("Failed run adhoc {}, {}".format(name, e))
        raise


def run_adhoc(hostname_list, pattern, tasks, name=None,
              run_as_admin=False, run_as=None, become_info=None):
    if name is None:
        name = "Adhoc-task-{}-{}".format(
            get_short_uuid_str(),
            timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        )

    inventory = get_inventory(
        hostname_list, run_as_admin=run_as_admin,
        run_as=run_as, become_info=become_info
    )
    runner = AdHocRunner(inventory)
    return runner.run(tasks, pattern, play_name=name)


def create_and_run_adhoc(hostname_list, pattern, tasks, name=None,
                         run_as_admin=False, run_as=None, become_info=None):
    if name is None:
        name = "Adhoc-task-{}-{}".format(
            get_short_uuid_str(),
            timezone.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
    task = Task(name=name)
    task.save()
    adhoc = AdHoc(
        task=task, pattern=pattern, name=name,
        run_as_admin=run_as_admin, run_as=run_as
    )
    adhoc.hosts = hostname_list
    adhoc.tasks = tasks
    adhoc.become = become_info
    adhoc.save()


def get_task_by_name(name):
    task = get_object_or_none(Task, name=name)
    return task


def create_task(name, created_by=""):
    return Task.objects.create(name=name, created_by=created_by)


def create_adhoc(task, hosts, tasks, pattern='all', options=None,
                 run_as_admin=False, run_as="",
                 become_info=None, created_by=""):
    adhoc = AdHoc(task=task, pattern=pattern, run_as_admin=run_as_admin,
                  run_as=run_as, created_by=created_by)
    adhoc.hosts = hosts
    adhoc.tasks = tasks
    adhoc.options = options
    adhoc.become = become_info
    adhoc.save()
    return adhoc
