from gdb_mi import Output
import keyword
import types
import pprint
import sys
import os
import pexpect
import asyncio


def _create_method(pyname, gdbname, doc):
    ''' Create a method named <pyname> that will
        invoke the gdb command <gdbname> using 'execute'.

        The <doc> will be used as the documentation of
        the method.
        '''
    def x(myself, *args, **kargs):
        cmd = (gdbname, ) + args

        exec_args = kargs.pop('exec_args', {})
        return myself.execute(' '.join(cmd), **exec_args)

    x.__doc__ = doc
    x.__name__ = pyname

    return x


def _console_lines(records):
    return [
        r.as_native()['value'] for r in records
        if r.is_stream(of_type='Console')
    ]


class GDBCtrl:
    ''' Spawn and control a gdb instance asynchronously, where
        the spawn(), send(), recv() and shutdown() are coroutines
        for spawning the debugger, send commands and receive records
        and shut down the debugger at the end.

        Note: due implementation details, only recv() is full async.
        The rest may block.
        '''
    def __init__(self, token_start=87362, timeout=None):
        self._cnt = None if token_start is None else token_start

        self._timeout = timeout
        self._mi = Output(nl='\n')
        self._gdb = None

    async def spawn(
        self,
        path2bin=None,
        path2data=None,
        args=None,
        encoding='utf-8',
        noinit=True,
        geometry=(24, 80)
    ):
        ''' Spawn the debugger in background.

            The debugger will be executed as 'gdb' and needs to be in the PATH.
            If it isn't, <path2bin> can be specified.

            The same for the 'data directory' with <path2data> (flag --data-directory)

            More flags will be passed:
                --quite (do not print version on startup)
                --interpreter=mi (use MI communication protocol)

            If <noinit> is True (default), no configuration file will be loaded
            by gdb (flags --nh and --nx).

            Extra arguments for gdb can be added with <args>.

            Once started, gdb is configured to turn off the confirmation of
            some operations so it will not block waiting for a human response.
            '''
        if self._gdb is not None:
            raise Exception(
                "This GDB Controller already has a gdb instance running."
            )

        rows, cols = geometry

        env = os.environ.copy()
        env.update({'LINES': str(rows), 'COLUMNS': str(cols)})

        cmd = 'gdb' if path2bin is None else path2bin
        args = list(args) if args is not None else list()

        if path2data is not None:
            args.append("--data-directory=%s" % path2data)

        args.append("--quiet")  # do not print version on startup
        args.append("-interpreter=mi")  # use MI interface mode

        if noinit:
            args.append("--nh")  # do not read ~/.gdbinit.
            args.append(
                "--nx"
            )  # do not read any .gdbinit files in any directory

        self._gdb = pexpect.spawn(
            cmd,
            args,
            echo=False,
            encoding=encoding,
            dimensions=(rows, cols),
            timeout=self._timeout,
            env=env
        )  # TODO blocking

        self._gdb.delaybeforesend = None
        self._gdb.delayafterread = None
        self._gdb.delayafterclose = None
        self._gdb.delayafterterminate = None

        # drop any initial output
        ix = await self._gdb.expect(
            [r'\(gdb\) \r?\n', pexpect.EOF], async_=True
        )
        if ix == 1:
            raise Exception("Unexpected EOF")

        await self.send('set confirm off')

        ix = await self._gdb.expect(
            [r'\(gdb\) \r?\n', pexpect.EOF], async_=True
        )
        if ix == 1:
            raise Exception("Unexpected EOF")

    async def shutdown(self):
        ''' Shutdown the debugger, trying to wake it up and telling it
            that we want to quit, nicely. If it doesn't work, kill it
            with SIGKILL.
            '''
        if self._gdb is None:
            return

        # wake up the debugger (SIGINT)
        self._gdb.sendintr()  # TODO blocking??
        await asyncio.sleep(0.5)

        # tell it that we want to exit
        self._gdb.write('-gdb-exit\n')  # TODO blocking
        self._gdb.flush()  # TODO blocking

        # close the stdin, this is another signal for the
        # debugger that we want to quit
        self._gdb.sendeof()  # TODO blocking???

        # read anything discarding what we read until
        # we get a EOF or a TIMEOUT or the process is dead
        n = 1
        while n:
            try:
                n = len(
                    self._gdb.read_nonblocking(1024, timeout=5)
                )  # TODO blocking
            except:
                break

        # close this by-hard (if the process is still alive)
        self._gdb.close(force=True)  # TODO blocking??
        self._gdb = None

    async def send(self, cmd, token=None):
        ''' Send the given command to the debugger but do
            not wait for any response from it. Use recv()
            for that.

            Keep in mind that recv() receives the next record and
            a send() may generate zero or more records so to get
            the 'full response' you may need to call recv() several
            times.

            One send() can trigger several records and asynchronous
            events in the debugger and in the debuggee can trigger
            records even without you calling send().

            Each command sent by send() will be prefixed with a
            token (a number) and return the token to you so you can
            match the response with recv().

            The token can be explicitly passed with send() or it
            can be autogenerated (default).
            The autogeneration can be disabled from GDBCtrl
            constructor passing token_start = None.
            '''
        # be extra carefully. if we add an extra newline, gdb
        # will re execute the last command again.
        if cmd.endswith('\n'):
            raise ValueError(
                "The command must not end with newline '%s'" % cmd
            )

        if token is None:
            if self._cnt is None:
                token = ''
            else:
                token = str(self._cnt)
                self._cnt += 1
        else:
            token = str(token)

        cmd = token + cmd + '\n'
        self._gdb.send(cmd)  # TODO blocking
        return token

    async def recv(self, timeout=-1):
        ''' Receive the next asynchronous/synchronous/stream record
            from the debugger and return it.

            Return None if EOF is hit otherwise return a GDB MI Record.

            There are four types of records in gdb:
             - AsyncRecord for asynchronous records (events, notifications)
               that happen so far since the last recv()
             - ResultRecord for "synchronous" records (results) product
               of a previous command. Despite the "synchronous" word,
               a ResultRecord may be the product of an old command so it
               is more like an asynchronous result.
             - StreamRecord for logging and gdb's console output that
               were written since the last recv()
             - TerminationRecord to mark the end of the response and debugger
               has the control again and it is accepting new commands.
               This is the '(gdb)' string.

            If <timeout> is None means no timeout and recv may block, otherwise
            on a timeout, recv will always return but you may need to call it
            again to keep retrieving the records.
            If <timeout> is -1, recv() will use as timeout the one specified
            in the GDBCtrl __init__.

            References:
             - https://sourceware.org/gdb/onlinedocs/gdb/GDB_002fMI-Output-Syntax.html#GDB_002fMI-Output-Syntax
             - https://pypi.python.org/pypi/python-gdb-mi
            '''
        tmp = [r'\r?\n', pexpect.EOF]
        if timeout is not None:
            tmp.append(pexpect.TIMEOUT)

        ix = await self._gdb.expect(tmp, async_=True, timeout=timeout)

        if ix >= 1:
            return

        assert '\n' not in self._gdb.before
        line = self._gdb.before + '\n'

        return self._mi.parse_line(line)


class SyncGDBCtrl:
    ''' Spawn and control a gdb instance synchronously, where
        spawn(), send(), recv() and shutdown() are
        for spawning the debugger, send commands and receive records
        and shut down the debugger at the end.

        For convenience, recv_all() receives zero or more records and
        keeps receiving them until no record exists (for some period of
        time)

        The execute() is a high level method that combines a
        send() with a recv_all() offering a synchronous way to
        execute a command and get its result.

        SyncGDBCtrl is intended to be used by human in an interactive
        session so it will print the results by default and it will add some
        convenient methods to SyncGDBCtrl based on the commands that gdb can
        execute.
        '''
    def __init__(
        self, token_start=87362, timeout=1, loop=None, force_styling=False
    ):
        if loop:
            self._loop = loop
        else:
            self._loop = asyncio.get_event_loop()

        self._async_gdb = GDBCtrl(token_start, timeout=timeout)

        import blessings
        self._T = blessings.Terminal(force_styling=force_styling)

    def _sync_call(self, coro):
        return self._loop.run_until_complete(coro)

    def spawn(self, *args, **kargs):
        return self._sync_call(self._async_gdb.spawn(*args, **kargs))

    def shutdown(self):
        return self._sync_call(self._async_gdb.shutdown())

    def send(self, cmd, token=None):
        return self._sync_call(self._async_gdb.send(cmd, token))

    def recv(self):
        return self._sync_call(self._async_gdb.recv())

    def recv_all(self, timeout=-1, pretty_print=True):
        ''' Call recv() several times until we got a timeout and
            return all the records read (it could be empty)

            This method is intended to be used in an interactive
            session so it will pretty print the records by default.
            (disable this with <pretty_print> set to False)
            '''
        if timeout is None or (
            timeout == -1 and self._async_gdb._timeout is None
        ):
            end_set = ('(gdb)', None)
        else:
            end_set = (None, )

        tmp = []
        r = 1
        while r not in end_set:
            r = self._sync_call(self._async_gdb.recv(timeout))
            if r not in ('(gdb)', None):
                tmp.append(r)

        if pretty_print:
            for t in tmp:
                if t in ('(gdb)', None):
                    continue
                self._human_print_async(t)
                self._human_print_streams(t)
                self._human_print_result(t)

        return tmp

    def execute(self, cmd, timeout=-1, pretty_print=True, ret=False):
        ''' Execute the given gdb command and wait for the records.

            Combines the functionality of send() and recv_all() but
            without returning anything (the records can be read from
            <self.last>) but default (if <ret> is True, return them)

            Like recv_all(), this method is intended to be used in an
            interactive session so it will pretty print the records
            received.
            '''
        token = self.send(cmd)
        elems = self.recv_all(timeout=timeout, pretty_print=pretty_print)

        self.last = elems
        if ret:
            return elems

    def _execute(self, cmd, timeout=-1):
        return self.execute(cmd, timeout=timeout, pretty_print=False, ret=True)

    def extend_interface_with_gdb_commands(self):
        ''' Scan what commands are available in gdb and include them as
            methods.

            This is a best effort: not all the commands will be loaded,
            some of them will have rewritten names (prefixed with 'z')
            and their will not have a signature (formal parameters).
            '''
        # gdb's output lines result of the apropos command
        lines = self._execute('apropos -*', timeout=None)
        lines = _console_lines(lines)

        # gdb commands
        gcmds = (l.split('--', 1)[0].strip() for l in lines if '--' in l)

        # filter out things that are not commands
        gcmds = filter(lambda g: not g.startswith('set '), gcmds)
        # filter out things that are not commands
        # in this case the filtering happens trying to create an alias
        # for the command: if the command doesn't exist the alias creation
        # fails and we filter the command
        gcmds = filter(
            lambda ig: self._execute(
                'alias -a intwkqjwq%i = %s' % (ig[0], ig[1]), timeout=None
            )[-1].is_result('done'), enumerate(gcmds)
        )

        # pythonize the names of the gdb commands
        # => (python-name, gdb-name)
        names = (
            (c.strip().replace(' ', '_').replace('-', '_'), c)
            for _, c in gcmds
        )

        # discard any name that is not valid as a python method
        # => (python-name, gdb-name)
        ids = (n for n in names if n[0].isidentifier())

        # prefix with 'z' if the name is a python keyword or it
        # is a method of GDB class that we don't want to loose
        # => (python-name, gdb-name)
        reserved = [m for m in dir(self) if m[0] != '_']
        meths = (
            ('z' + i[0],
             i[1]) if keyword.iskeyword(i[0]) or i[0] in reserved else i
            for i in ids
        )

        for pyname, gdbname in meths:
            tmp = self._execute('help %s' % gdbname, timeout=None)
            tmp = _console_lines(tmp)

            tmp.insert(0, 'Command: %s\n\n' % gdbname)
            doc = ''.join(tmp)

            method = _create_method(pyname, gdbname, doc)

            setattr(self, pyname, types.MethodType(method, self))

    def _print(self, *args, **kargs):
        fixline = kargs.pop('fixline', False)
        if not fixline:
            print(*args, **kargs)
        else:
            assert len(args) == 1
            s = args[0]
            if not isinstance(s, (str, bytes)):
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

        T = self._T
        self._print(T.green(ob.type + ':'), end='')
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
        T = self._T
        if result is None:
            self._print(T.cyan('None'))
            return

        if not result.is_result():
            return

        c = {
            'error': T.red,
            'done': T.cyan,
            'running': T.yellow,
            'connected': T.yellow,
            'exit': T.yellow
        }.get(result.result_class, T.normal)

        r = result.as_native(include_headers=False)
        prefix = result.result_class.capitalize()
        if r:
            prefix += ':'

        self._print(c(prefix), end='' if r else '\n')

        if result.is_result(of_class='error'):
            msg = r.pop('msg', '')
            if msg:
                self._print(msg.strip())

        if r:
            self._print(r, fixline=True)
