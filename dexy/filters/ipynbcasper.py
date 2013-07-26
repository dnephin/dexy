from dexy.exceptions import UserFeedback
from dexy.filters.process import SubprocessFilter
import os
import subprocess
import time

try:
    import IPython.nbformat.current
    AVAILABLE = True
except ImportError:
    AVAILABLE = False

class IPythonCasper(SubprocessFilter):
    """
    Launch IPython notebook and run a casperjs script against the server.
    """
    aliases = ['ipynbcasper']

    _settings = {
            'input-extensions' : ['.ipynb'],
            'output-extensions' : ['.txt'],
            'args' : '--web-security=false --ignore-ssl-errors=true',
            'timeout' : 10000,
            'script' : ("Canonical name of input document to use as casper script.", "default.js"),
            'add-new-files' : True,
            "width" : ("Width of page to capture.", 800),
            "height" : ("Height of page to capture.", 5000),
            'executable' : 'casperjs',
            'cell-timeout' : ("Timeout (in microseconds) for running individual notebook cells.", 5000),
            'version-command' : 'casperjs --version',
            'ipython-port' : ("Port for the ipython notebook web app to run on.", 8987),
            'ipython-args' : ("Additional args to pass to ipython notebook command (list of string args).", None),
            "command-string" : "%(prog)s %(args)s %(script)s",
            }

    def is_active(self):
        return AVAILABLE

    def configure_casper_script(self, wd):
        scriptfile = os.path.join(wd, self.setting('script'))

        default_scripts_dir = os.path.join(os.path.dirname(__file__), "ipynbcasper")

        if not os.path.exists(scriptfile):
            # look for a matching default script
            script_setting = self.setting('script')

            filepath = os.path.join(default_scripts_dir, script_setting)
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    js = f.read()
            else:
                default_scripts = os.listdir(default_scripts_dir)
                args = (self.setting('script'), ", ".join(default_scripts),)
                raise UserFeedback("No script file named '%s' found.\nAvailable built-in scripts: %s" % args)

        else:
            with open(scriptfile, "r") as f:
                js = f.read()

        args = {
                'width' : self.setting('width'),
                'height' : self.setting('height'),
                'port' : self.setting('ipython-port'),
                'cell_timeout' : self.setting('cell-timeout')
                }

        with open(scriptfile, "w") as f:
            f.write(js % args)

    def launch_ipython(self, wd, env):
        # Another way to handle ports would be to let ipython launch on a
        # random port and parse the port from the ipython process's stdout.
        port = self.setting('ipython-port')
        port_string = "--port=%s" % port

        # This code is redundant with --port-retries=0 but would need a way to
        # detect that ipython server process has ended.
        try:
            import socket
            s = socket.socket()
            s.bind(('localhost', port,))
            s.close()
            self.log_debug("port %s is available" % port)
        except socket.error:
            raise UserFeedback("Port %s already in use." % port)

        command = ['ipython', 'notebook', '--log-level=0', '--port-retries=0', port_string, '--no-browser']
        command.extend(self.parse_additional_ipython_args())
        self.log_debug("About to run ipython command: '%s'" % ' '.join(command))
        proc = subprocess.Popen(command, shell=False,
                                    cwd=wd,
                                    stdin=None,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE,
                                    env=env)

        time.sleep(1)
        try:
            import socket
            s = socket.socket()
            s.bind(('localhost', port,))
            raise Exception("should not get here")
            s.close()
        except socket.error:
            self.log_debug("ipython notebook server started successfully")

        return proc

    def parse_additional_ipython_args(self):
        raw_ipython_args = self.setting('ipython-args')
        if raw_ipython_args:
            if isinstance(raw_ipython_args, basestring):
                user_ipython_args = raw_ipython_args.split()
            elif isinstance(raw_ipython_args, list):
                assert isinstance(raw_ipython_args[0], basestring)
                user_ipython_args = raw_ipython_args
            else:
                raise UserFeedback("ipython-args must be a string or list of strings")
            return user_ipython_args
        else:
            return []

    def process(self):
        env = self.setup_env()
        wd = self.parent_work_dir()

        ws = self.workspace()
        if os.path.exists(ws):
            self.log_debug("already have workspace '%s'" % os.path.abspath(ws))
        else:
            self.populate_workspace()

        # launch ipython notebook
        ipython_proc = self.launch_ipython(wd, env)

        try:
            ## run casper script
            self.configure_casper_script(wd)
    
            command = self.command_string()
            proc, stdout = self.run_command(command, self.setup_env())
            self.handle_subprocess_proc_return(command, proc.returncode, stdout)
            self.output_data.set_data(stdout)
    
            if self.setting('add-new-files'):
                self.add_new_files()

        except Exception as e:
            print e
        finally:
            # shut down ipython notebook
            os.kill(ipython_proc.pid, 9)
            # wait for it to finish shutting down
            time.sleep(3)