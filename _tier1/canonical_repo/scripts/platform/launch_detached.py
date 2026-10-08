"""Launch a python target fully detached (new session, file-backed stdout).

Usage: python launch_detached.py <target_script> <arg1> <arg2> ...  <logfile>
Example: python launch_detached.py F:/AI/monitor_10m.py F:/AI/silverwing-10m-monitor.log
The child inherits stdout->logfile, is reparented to init (start_new_session), and
survives this launcher exiting or any shell-session TTL. Prints CHILD_PID and exits.
"""
import subprocess, sys, os
target = sys.argv[1]
logfile = sys.argv[2]
args = sys.argv[3:]
env = dict(os.environ)
env["SILVERWING_WORK_DIR"] = "F:/AI/silverwing-10m"
logf = open(logfile, "wb")
p = subprocess.Popen(
    [sys.executable, "-u", target, *args],
    stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
    env=env, start_new_session=True,
)
logf.close()
print("CHILD_PID", p.pid, "TARGET", target, "LOG", logfile)
