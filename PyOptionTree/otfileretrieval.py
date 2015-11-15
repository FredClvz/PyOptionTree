import hashlib, commands, base64
from pyoptiontreeexceptions import PyOptionTreeRetrievalError

def OTFileRetrievalFunctions():
    """
    This creates a list of functions for the PyOptionTree parser to
    make file retrieval easier.  

    """
    return [('retrieve_file', OT_retrieve_file),
            ('retrieve_optfile', OT_retrieve_optfile)]

def OT_retrieve_file(filename, mode='rsync-ssh', keyfile='', args='', sshargs=''):
    """
    Retrieves ``filename`` from a remote location using the protocol
    specified in ``mode``.  If the retrieval mode uses ssh, optionally
    ``keyfile`` may give the location of the private key to use for
    authentication.  Additional parameters may be passed using
    ``args``.If the arguments to the main retrieval routine and the
    ssh connection are seperate, as with rsync-ssh, additional
    parameters to the ssh routine may be supplied with ``sshargs``.

    ``filename`` is the same form accepted by the retrieval function;
    in this case, ``[[user@]server:]file``.  The following are all
    valid filenames::

      hoytak@cs.ubc.ca:/home/hoytak/myfile.opt 
      cs.ubc.ca:/home/hoytak/myfile.opt 
      /home/hoytak/myfile.opt 

    The following arguments for ``mode`` are supported:

    \'url\'
      Uses wget to retrieve the file ``filename``, which is given as a
      valid url.  wget supports HTTP, HTTPS, and FTP, but defaults to
      HTTP if ``filename`` has no suffix.  All of the following are
      valid urls::

        www.cs.ubc.ca/~hoytak/myfile.dat
        http://www.cs.ubc.ca/~hoytak/myotherfile.dat
        ftp://www.myftpserver.com/myfile.dat
        https://www.myshttpserver.com/files/myfile.dat

      If the ftp server requires authentication, pass --user=<user>
      --password=<password> in args.

    \'scp\' or \'ssh\'
      If ``mode``=\'scp\' or \'ssh\', then retrieve_file() attempts to
      retrieve ``filename`` using the ``scp`` command, which copies
      the file using ssh.  If keyfile is given and not \'\' or None,
      authentication is first attempted using the key.  In this case,
      ``args`` and ``sshargs`` have the same effect, with ``sshargs``
      possibly overriding ``args``.

    \'rsync\'
      Attempts to retrieve the file using rsync.  rsync offers
      numerous advantages over scp, the main one being that, in the
      case of an already existing file, it copies only differences of
      files instead of the entire file and skips it if they are
      identical (as would likely be the case across successive
      runs). It can thus offer substantial speedup.  It also accepts
      numerous arguments, which can be passed to it through ``args``.
      In this case, ``keyfile`` and ``sshargs`` are ignored.

    \'rsync-ssh\' (default)
      This is identical to \'rsync\' except that it uses ssh for
      connections and is thus more secure than \'rsync\'.  If
      ``keyfile`` is supplied and not \'\' or None, ssh attempts
      authentication using it. Parameters specific to rsync may be
      passed through ``args`` and parameters specific to the ssh
      connection may be passed with ``sshargs``.

    If ``mode`` is not in the above list, it raises a
    PyOptionTreeParseError exception.

    retrieve_file() returns the name of a temporary file in /tmp/ that
    the remote file is copied to.  The name of the temporary file is
    '_PyOpT_' plus a hash of the filename and is thus identical as
    long as filename remains the same.

    For example, in an option tree file,::

      tree1 = loadfile(retrieve_file(\'hoytak@cs.ubc.ca:/home/hoytak/myfile.dat\',
                                     \'rsync-ssh\', \'~/.ssh/mykey\')) 

    copies myfile.dat to a local temporary file using rsync over an
    ssh connection authenticated with the private key
    \'~/.ssh/mykey\', then loads that file using the loadfile()
    function.

    On error, it raises a PyOptionTreeRetreival exception and includes
    the output of the given command as the error message,
    
    """

    tmpname =  ' /tmp/_PyOpT_' + base64.urlsafe_b64encode(hashlib.sha256(filename).digest()).replace('-', '').replace('_', '')[:8]
    filename = '\'' + filename + '\''

    if mode=='url':
        command = 'wget ' + args + ' -O ' + tmpname + ' ' + filename 
    elif mode=='scp' or mode=='ssh':
        command = 'scp '
        if type(keyfile) == str and len(keyfile) != 0: command += '-i ' + keyfile
        comand += ' ' + args + ' ' + sshargs + ' ' + filename + ' ' + tmpname 
    elif mode == 'rsync':
        command = 'rsync ' + args + ' ' + filename + ' ' + tmpname
    elif mode == 'rsync-ssh':
        command = ('rsync -c -e \'ssh '
                   + (' ', '-i ' + keyfile)[type(keyfile) == str and len(keyfile.strip()) != 0]
                   + ' -ax -o ClearAllForwardings=yes ' + sshargs + '\' ' + args + ' '
                   + filename + ' ' + tmpname)
    else:
        raise PyOptionTreeParseError('', 'mode invalid.  See documentation for valid modes.')

    print 'Retrieving file ', filename, ', temp file = ' + tmpname
    
    cstr = command.replace('   ', ' ').replace('  ', ' ')
    (errcode, result) = commands.getstatusoutput(cstr)
    
    if errcode != 0:
        raise PyOptionTreeRetrievalError("Evaluating command '" + cstr + "'", result)
    else:
        return tmpname.strip()


def OT_retrieve_optfile(filename, mode='rsync-ssh', keyfile='', args='', sshargs=''):

    """
    retrieve_optfile(...) is identical to retrieve_file(...), except
    that it returns a tuple that can be passed to optfile(...) that
    contains both the temporary file and ``filename``, thus indicating
    ``filename`` as the source.  This is the prefered method with optfile()
    """
    
    return (OT_retrieve_file(filename, mode, keyfile, args, sshargs), filename)
