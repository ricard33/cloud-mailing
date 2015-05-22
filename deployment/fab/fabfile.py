# Copyright 2015 Cedric RICARD
#
# This file is part of CloudMailing.
#
# CloudMailing is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# CloudMailing is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with CloudMailing.  If not, see <http://www.gnu.org/licenses/>.

import glob
import os
import random
import tempfile
from fabric.api import env, cd, run, put, settings, prefix, task, local, get
from fabric.contrib.project import rsync_project
from fabric.contrib.files import append
import sys

env.shell = "/bin/sh -c"

try:
    import local_settings
    env.roledefs = local_settings.roledefs
    default_cm_config = local_settings.default_cm_config
except ImportError:
    print >> sys.stderr, "Can't find local_settings.py ; No roles definitions"
    default_cm_config = {}

FAB_PATH = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = os.path.abspath(os.path.join(FAB_PATH, "..", ".."))
TARGET_PATH = '/usr/local/cm'


@task
def get_system_name():
    return run("uname")


@task
def cm_stop():
    run("supervisorctl stop cm:cm_master")
    run("supervisorctl stop cm:cm_satellite")


@task
def cm_start():
    run("supervisorctl start cm:cm_master")
    run("supervisorctl start cm:cm_satellite")


@task
def stop_master():
    run("supervisorctl stop cm:cm_master")


@task
def start_master():
    run("supervisorctl start cm:cm_master")


@task
def stop_satellite():
    run("supervisorctl stop cm:cm_satellite")


@task
def start_satellite():
    run("supervisorctl start cm:cm_satellite")


@task
def test():
    with cd(TARGET_PATH):
        print 'exist:', os.path.exists('/Users')


def clean_compiled_files():
    # cleanup *.pyc / *.pyo files
    put(os.path.join(WORKSPACE, 'deployment', "cm_compile.py"), TARGET_PATH)
    with cd(TARGET_PATH):
        run("python cm_compile.py -c")


def compile_python_files():
    # create *.pyc / *.pyo files
    put(os.path.join(WORKSPACE, 'deployment', "cm_compile.py"), TARGET_PATH)
    with cd(TARGET_PATH):
        run("python -O cm_compile.py")


def sync_sources(test_only=False):

    rsync_project(
        TARGET_PATH,
        local_dir=WORKSPACE + "/",
        delete=True,
        extra_opts='-ci --filter=". %s"' % os.path.join(FAB_PATH, "rsync_filter") + (test_only and " --dry-run" or ""),
        #extra_opts="-ci --dry-run",
    )



@task
def deploy_cm_master():
    run("mkdir -p %s" % TARGET_PATH)
    clean_compiled_files()
    sync_sources()
    compile_python_files()

    # put(os.path.join(WORKSPACE, "requirements.txt"), TARGET_PATH)

    with cd(TARGET_PATH):
        with settings(warn_only=True):
            if run("test -d .env").failed:
                run("virtualenv .env")

        with prefix('. .env/bin/activate'):
            run('pip install -r requirements.txt --upgrade')
            # run('pip install -r requirements-testing.txt')

    # with cd(TARGET_PATH):
    #     with prefix('. .env/bin/activate'):
            # run('python manage.py syncdb --noinput')
            # run('python manage.py migrate')
            # run('python manage.py clearsessions')
            # run('python manage.py collectstatic --noinput')

    run("chown -R cm:cm %s" % TARGET_PATH)


# @task
# def init_db():
#     run("createuser -U pgsql cm")
#     run("createdb -O cm -U pgsql cm")
#

@task
def create_user():
    """
    create the 'cm' user and group on new system.
    @return:
    """
    remote_system = get_system_name()
    if remote_system == "Linux":
        run("adduser --home %(TARGET_PATH)s --shell /bin/tcsh --disabled-password --disabled-login cm" % {'TARGET_PATH': TARGET_PATH})
    elif remote_system == "FreeBSD":
        run("pw useradd cm -d %(TARGET_PATH)s -m -s /bin/tcsh -w no" % {'TARGET_PATH': TARGET_PATH})
    else:
        print("create_user: Unsupported remote system '%s'" % remote_system)



@task
def create_initial_config():
    """
    create a new config file for CloudMailing.
    @return:
    """
    config_filename = os.path.join(TARGET_PATH, 'config', 'config.ini')

    from ConfigParser import RawConfigParser
    config = RawConfigParser()
    config.add_section("CM_MASTER")
    config.set('CM_MASTER', 'API_KEY', "".join([random.choice("abcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*(-_=+)") for i in range(50)]))

    test_target = default_cm_config.get('test_target')
    if test_target:
        config.add_section("MAILING")
        config.set('MAILING', 'test_target_ip', test_target['ip'])
        config.set('MAILING', 'test_target_port', test_target['port'])

    with tempfile.NamedTemporaryFile('w+t') as tmp:
        config.write(tmp)
        tmp.flush()
        run("mkdir -p %s/config" % TARGET_PATH)
        put(tmp.name, config_filename)
    run("chown cm:cm %s" % config_filename)


@task
def create_supervisord_config():
    """
    create the supervisord config files for CloudMailing jobs
    @return:
    """
    config = """[group:cm]
programs=cm_master,cm_satellite

[program:cm_master]
command=%(TARGET_PATH)s/.env/bin/python -O bin/cm_master.py
directory=%(TARGET_PATH)s
numprocs=1
stdout_logfile=/var/log/cm_master.supervisor.log
autostart=true
autorestart=true
user=cm

[program:cm_satellite]
command=%(TARGET_PATH)s/.env/bin/python -O bin/cm_satellite.py
directory=%(TARGET_PATH)s
numprocs=1
stdout_logfile=/var/log/cm_satellite.supervisor.log
autostart=true
autorestart=true
user=cm
""" % {'TARGET_PATH': TARGET_PATH}
    with tempfile.NamedTemporaryFile('w+t') as tmp:
        tmp.write(config)
        tmp.flush()
        remote_system = get_system_name()
        if remote_system == "Linux":
            put(tmp.name, "/etc/supervisor/conf.d/cloud_mailing.conf")
        elif remote_system == "FreeBSD":
            put(tmp.name, "/usr/local/etc/supervisord.d/cloud_mailing.conf")

    run("supervisorctl reread")
    run("supervisorctl update")

@task
def remove_mf_from_startup():
    remote_system = get_system_name()
    if remote_system == "FreeBSD":
        conf_path = "/usr/local/etc/supervisord.d"
    else:
        conf_path = "/etc/supervisor/conf.d"
    run("supervisorctl stop mf_master")
    run("supervisorctl stop mf_satellite")
    run("rm %s/mf_master.conf" % conf_path)
    run("rm %s/mf_satellite.conf" % conf_path)
    run("supervisorctl reread")
    run("supervisorctl update")

@task()
def first_setup():
    # init_db()
    create_user()
    create_initial_config()
    create_supervisord_config()
    deploy_cm_master()
    cm_start()


@task()
def diff():
    sync_sources(test_only=True)


@task(default=True)
def deploy():
    cm_stop()
    deploy_cm_master()
    cm_start()


