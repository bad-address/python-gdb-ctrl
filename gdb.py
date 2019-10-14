from byexample.runner import PexpectMixin
from byexample.options import Options
from gdb_mi import Output
import re
import keyword
import types
import pprint
import sys

def create_method(pyname, gdbname, doc):
    def x(myself, *args):
        cmd = (gdbname, ) + args
        result, out_of_band = myself.send(' '.join(cmd))
        for ob in out_of_band:
            myself._human_print_async(ob)
            myself._human_print_streams(ob)
            myself._human_print_result(ob)
        myself._human_print_result(result)

        if result is None:
            return

        r = result.as_native(include_headers=False)
        if not r:
            return

        return r

    x.__doc__ = doc
    x.__name__ = pyname

    return x

def are_tty_colors_supported(output):
    def get_colors():
        try:
            import curses
            curses.setupterm()
            return int(curses.tigetnum('colors'))
        except:
            # assume that we have a terminal with color support
            return 8
    return output.isatty() and \
           'm' not in os.getenv('TERM', '').split('-') and \
           get_colors() >= 8

import os
import pexpect
class GDB:
    RESERVED = ('shutdown', 'send')
    def __init__(self, path2bin=None, path2data=None, args=None,
                 encoding='utf-8', noinit=True, geometry=(24,80),
                 use_colors=None, token_start=87362):
        rows, cols = geometry

        if use_colors is None:
            self._use_colors = are_tty_colors_supported(sys.stdout)
        else:
            self._use_colors = use_colors

        self._cnt = token_start

        env = os.environ.copy()
        env.update({'LINES': str(rows), 'COLUMNS': str(cols)})

        cmd = 'gdb' if path2bin is None else path2bin
        args = list(args) if args is not None else list()

        if path2data is not None:
            args.append("--data-directory=%s" % path2data)

        args.append("--quiet")          # do not print version on startup
        args.append("-interpreter=mi")  # use MI interface mode

        if noinit:
            args.append("--nh")   # do not read ~/.gdbinit.
            args.append("--nx")   # do not read any .gdbinit files in any directory

        self._gdb = pexpect.spawn(cmd, args,
                echo=False,
                encoding=encoding,
                dimensions=(rows, cols),
                env=env)

        self._gdb.delaybeforesend = None
        self._gdb.delayafterread = None

        self.last_out_of_band = []

        self._gdb.expect(r'\(gdb\) \r?\n') # drop any initial output
        with_carriage = self._gdb.before.endswith('\r\n')

        self._mi = Output(nl='\r\n' if with_carriage else '\n')
        self.send('set confirm off')


    def shutdown(self):
        ''' Shutdown the debugger, trying to wake it up and telling it
            that we want to quit, nicely. If it doesn't work, kill it
            with SIGKILL.
            '''
        # wake up the debugger (SIGINT)
        self._gdb.sendintr()
        time.sleep(0.5)

        # tell it that we want to exit
        self._gdb.write('-gdb-exit\n')
        self._gdb.flush()

        # close the stdin, this is another signal for the
        # debugger that we want to quit
        self._gdb.sendeof()

        # read anything discarding what we read until
        # we get a EOF or a TIMEOUT or the process is dead
        n = 1
        while n:
            try:
              n = len(self._gdb.read_nonblocking(1024, timeout=5))
            except:
              break

        # close this by-hard (if the process is still alive)
        self._gdb.close(force=True)

    def send(self, cmd, console_lines=False):
        # be extra carefully. if we add an extra newline, gdb
        # will rexecute the last command again.
        if cmd.endswith('\n'):
            raise ValueError("The command must not end with newline '%s'" % cmd)

        token = str(self._cnt)
        cmd = token + cmd + '\n'
        self._cnt += 1

        self._gdb.send(cmd)
        self._gdb.expect(r'%s.*\(gdb\) \r?\n' % token)

        tmp = []
        output = self._gdb.before + self._gdb.match.group(0)
        for line in output.splitlines(True):
            r = self._mi.parse_line(line)
            tmp.append(r)

        if not tmp or tmp[-1] != '(gdb)':
            raise Exception("Missing '(gdb)'")
        tmp.pop()

        result = None
        if tmp and tmp[-1].type == 'Sync':
            result = tmp.pop()

        out_of_band = tmp
        self.last_out_of_band = out_of_band

        if console_lines:
            return [s.as_native()['value'] for s in out_of_band if s.is_stream(of_type='Console')]
        else:
            return result, out_of_band

    def _include_gdb_commands(self):
        ''' Scan what commands are available in GDB and include them as
            methods.

            This is a best effort: not all the commands will be loaded,
            some of them will have rewritten names (prefixed with 'z')
            and their will not have a signature (formal parameters).

            The output of each method/command will be processed to be
            more human friendly.

            If you want to interact with GDB directly without any fancy
            feature, use send().
            '''
        # gdb's output lines result of the apropos command
        lines = self.send('apropos -*', console_lines=True)

        # gdb commands
        gcmds = (l.split('--', 1)[0].strip() for l in lines if '--' in l)

        # filter out things that are not commands
        gcmds = filter(lambda g: not g.startswith('set '), gcmds)
        # filter out things that are not commands
        # in this case the filtering happens trying to create an alias
        # for the command: if the command doesn't exist the alias creation
        # fails and we filter the command
        gcmds = filter(lambda ig: self.send('alias -a intwkqjwq%i = %s' % (ig[0], ig[1]))[0].is_result('done'), enumerate(gcmds))

        # pythonize the names of the gdb commands
        # => (python-name, gdb-name)
        names = ((c.strip().replace(' ', '_').replace('-', '_'), c) for _, c in gcmds)

        # discard any name that is not valid as a python method
        # => (python-name, gdb-name)
        ids = (n for n in names if n[0].isidentifier())

        # prefix with 'z' if the name is a python keyword or it
        # is a method of GDB class that we don't want to loose
        # => (python-name, gdb-name)
        meths = (('z' + i[0], i[1]) if keyword.iskeyword(i[0]) or i[0] in GDB.RESERVED else i for i in ids)

        for pyname, gdbname in meths:
            tmp = self.send('help %s' % gdbname, console_lines=True)
            tmp.insert(0, 'Command: %s\n\n' % gdbname)
            doc = ''.join(tmp)

            method = create_method(pyname, gdbname, doc)

            setattr(self, pyname, types.MethodType(method, self))

    def _print(self, *args, **kargs):
        fixline = kargs.pop('fixline', False)
        if not fixline:
            print(*args, **kargs)
        else:
            assert len(args) == 1
            s = args[0]
            if not isinstance(s, (str,bytes)):
                s = pprint.pformat(s)
            if '\n' in s:
                print('\n', s, sep='')
            else:
                print(' ', s, sep='')

    def _human_print_streams(self, stream):
        ''' From the GDB MI's documentation:
             - `Console`: output that should be displayed as is in the console.
                          It is the textual response to a CLI command.
             - `Target`: output produced by the target program.
             - `Log`: output text coming from GDB’s internals, for instance messages that
                      should be displayed as part of an error log.
            Ref https://sourceware.org/gdb/onlinedocs/gdb/GDB_002fMI-Output-Syntax.html#GDB_002fMI-Output-Syntax
            '''
        if stream.is_stream(of_type=('Console', 'Target')):
            s = stream.as_native()['value']
            self._print(s.rstrip())
        elif stream.is_stream(of_type='Log'):
            pass


    def _human_print_async(self, async_result):
        ''' From the GDB MI's documentation:
             - `Exec`: asynchronous state change on the target (stopped, started, disappeared).
             - `Status`: on-going status information about the progress of a slow operation. It can be discarded.
             - `Notify`: supplementary information that the client should handle (e.g., a new breakpoint information).

            Ref https://sourceware.org/gdb/onlinedocs/gdb/GDB_002fMI-Output-Syntax.html#GDB_002fMI-Output-Syntax
            '''
        if not async_result.is_async():
            return

        ob = async_result

        self._print(self._colored(ob.type + ':', 'green'), end='')
        s = ob.as_native(include_headers=False)
        self._print(s, fixline=True)

    def _human_print_result(self, result):
        ''' From the GDB MI's documentation:
             - `done`
             - `running`
             - `connected`
             - `error`
             - `exit`

            Ref https://sourceware.org/gdb/onlinedocs/gdb/GDB_002fMI-Result-Records.html#GDB_002fMI-Result-Records
            '''
        if result is None:
            self._print(self._colored('None', 'cyan'))
            return

        if not result.is_result():
            return

        c = {'error': 'red', 'done': 'cyan',
             'running': 'yellow', 'connected': 'yellow',
             'exit': 'yellow'}.get(result.result_class, 'none')

        r = result.as_native(include_headers=False)
        prefix = result.result_class.capitalize()
        if r:
            prefix += ':'

        self._print(self._colored(prefix, c), end='' if r else '\n')

        if result.is_result(of_class='error'):
            msg = r.pop('msg', '')
            if msg:
                self._print(msg.strip())

        if r:
            self._print(r, fixline=True)

    def _colored(self, s, color):
        if self._use_colors:
            if color == 'none':
                return s
            c = {'green': 32, 'red': 31, 'yellow': 33, 'cyan': 36}[color]
            return "\033[%sm%s\033[0m" % (c, s)
        else:
            return s