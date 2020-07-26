# Python GDB Controller

``python-gdb-ctrl`` is a thin interface on top of
[GDB](https://sourceware.org/gdb/), the debugger of the GNU Project.

It will let you to spawn and control the debugger from a Python console
or program.

``python-gdb-ctrl`` has two use modes: asynchronous and
synchronous.

The former is intended to be used by another application, the latter is
more a toy-example but handy while experimenting from a Python console.

## ``GDBCtrl`` - Asynchronous interface

The class ``GDBCtrl`` is suitable from integrating
``python-gdb-ctrl`` and the debugger with an UI
or other event-based software.

It has the basic primitives:
 - ``spawn``: to run the debugger
 - ``shutdown``: to quit or kill the debugger
 - ``send``: to send GDB commands
 - ``recv``: to receive GDB records

All of them are *coroutines* that can be integrated in an
``asyncio`` loop.

> Note: due limitations in one of the dependencies of
> ``python-gdb-ctrl`` all the primitives except ``recv``
> may block as they are not full asynchronous.


## ``SyncGDBCtrl`` - Synchronous interface

While ``GDBCtrl`` is the class that you should use in a program, it is
much easier to play interactively with ``SyncGDBCtrl``.

```python
>>> from gdb_ctrl import SyncGDBCtrl
>>> gdb = SyncGDBCtrl(force_styling=None)
```

The ``spawn`` and ``shutdown`` methods now are normal methods (they
are not coroutines)

```python
>>> gdb.spawn()
```

The same applies for ``send`` and ``recv``

```python
>>> gdb.send('file example/glad')
'<token>'
```

However a synchronous ``recv`` is tricky because GDB may return several
records for a given ``send`` so you need to know beforehand how many
times you need to call ``recv``:

```python
>>> gdb.recv()
{'type': 'Log', 'value': 'file example/glad\n'}

>>> gdb.recv()
{'type': 'Console', 'value': 'Reading symbols from example/glad...'}

>>> gdb.recv()
{'type': 'Console', 'value': 'done.\n'}

>>> gdb.recv()      # byexample: +paste
{'class': 'done', 'token': <token>, 'type': 'Result'}

>>> gdb.recv()
'(gdb)'
```

Notice how the ``send`` returned a ``<token>``: you can use
this to pair the command with its result.

Unfortunately this works only for the results, other GDB responses
will not have this token so you cannot know if the ``Log`` response
above is the product of the execution of ``file example/glad`` or
it is the product of other command.

Using the synchronous ``recv`` is annoying: you need to know
how many responses you will receive.

``SyncGDBCtrl`` is mostly for interactive session so it provides handy
``execute`` method to send a command and receive the records in one
shot taking care of retrieving all the responses.

This is specially useful for certain commands that they do more
than one thing.

The ``start`` command is an example of this:

```python
>>> gdb.execute('start')
Temporary breakpoint 1 <...>: file glad.c, line 52.
Notify:
{'bkpt': {'addr': '<...>',
          'disp': 'del',
          'enabled': 'y',
          'file': 'glad.c',
          'fullname': '<...>/example/glad.c',
          'func': 'main',
          'line': '52',
          <...>
          'times': '0',
          'type': 'breakpoint'}}
Starting program: /home/user/proj/python-gdb-ctrl/example/glad
<...>
Running
Exec: {'thread-id': 'all'}
<...>
Notify:
{'bkpts': [{'addr': '<...>',
            'disp': 'del',
            'enabled': 'y',
            'file': 'glad.c',
            'fullname': '<...>/example/glad.c',
            'func': 'main',
            'line': '52',
            'number': '1',
            'original-location': 'main',
            'thread-groups': ['i1'],
            'times': '1',
            'type': 'breakpoint'}]}
<...>
Temporary breakpoint 1, main (argc=1, argv=0x<...>) at glad.c:52
52          pthread_create(&th, NULL, release_neurotoxins, NULL);
Exec:
{'bkptno': '1',
 <...>
 'reason': 'breakpoint-hit',
 'stopped-threads': 'all',
 'thread-id': '1'}
<...>
```

That's a lot! When GDB executes ``start``, it sets a temporal breakpoint
in the `main` function, it runs the binary and it notifies us when the
breakpoint is hit and the program is stopped.

That generates a lot of messages (in fact I omitted several ones).

For convenience, ``execute()`` will print what it receives so you don't
need to parse anything.

If you want to use ``SyncGDBCtrl`` programmatically you can but I would
recommend against it and use ``GDBCtrl`` instead.

### A pythonic interface

Besides ``execute()``, ``SyncGDBCtrl`` can be *extended* with several
methods that will call a GDB command in a *pythonic* way:

```python
>>> gdb.extend_interface_with_gdb_commands()
```

Now instead of calling ``execute('list')`` you can call ``list`` directly.

```python
>>> gdb.list()
47          return 0;
48      }
49
50      int main(int argc, char *argv[]) {
51          pthread_t th;
52          pthread_create(&th, NULL, release_neurotoxins, NULL);
53
54          int cores[CORES] = {1};
55
56          for (int i = 1; i < argc; ++i) {
Done
```

The beauty of this is that you can request the documentation from
a Python shell:

```python
>>> print(gdb.list.__doc__)
<...>
List specified function or line.
With no argument, lists ten more lines after or around previous listing.
"list -" lists the ten lines before a previous ten-line listing.
One argument specifies a line, and ten lines are listed around that line.
Two arguments with comma between specify starting and ending lines to list.
Lines can be specified in these ways:
  LINENUM, to list around that line in current file,
  FILE:LINENUM, to list around that line in that file,
  FUNCTION, to list around beginning of that function,
  FILE:FUNCTION, to distinguish among like-named static functions.
  *ADDRESS, to list around the line containing that address.
With two args, if one is empty, it stands for ten lines away from
the other arg.
<...>
```

> Note: GDB commands that have an invalid name for Python will be prefixed
> with a `z`

Finally, don't forget to shutdown the debugger:

```python
>>> gdb.shutdown()                  # byexample: +pass -skip
```

## Install

Just run:

```
$ pip install python-gdb-ctrl         # byexample: +pass
```

You will find the `python-gdb-ctrl` package at [PyPI](https://pypi.python.org/pypi/python-gdb-ctrl)

## Hacking/Contributing

Go ahead! Clone the repository, do a small fix/enhancement, run `make deps-dev`
to install the development dependencies including the test engine
[byexample](https://byexamples.github.io), then run `make test` to
ensure that everything is working as expected and finally
propose your Pull Request!
