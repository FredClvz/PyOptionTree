import random, inspect, time, cPickle
from pyoptiontreeexceptions import *
from operator import itemgetter
import base64
import os, os.path

try:
    from hashlib import md5
except ImportError:
    from md5 import md5

OPTTREE_RANDALPHALENGTH  = 10
OPTTREE_MAXRECURSIONDEPTH = 32
OPTTREE_TRUNCATEDERRORSTRINGLENGTH = 60
OPTTREE_TARGETPRINTLINELENGTH = 50
OTdebug = False

######################################################################
# Helper Functions and classes.

def OTRandTag():
    s = []
    while len(s) < OPTTREE_RANDALPHALENGTH:
        ch = chr(random.randint(48,123))
        if ch.isalnum():
            s.append(ch)
            
    return ''.join(s)

OPTTREE_NONNONEXISTANTQUERY = '__' + OTRandTag()

def OTIsNameChar(s):
    return s.isalnum() or s == '[' or s == ']' or s == '_' or s == '/' or s == '.'

def OTIsNumberChar(s):
    return s.isdigit() or s == '.' or s == 'e' or s == 'E' or s == '-'

class OTTypeInfo:
    """
    Helps with parsing the option tree file; used internally.
    """

    def __init__(self, matchkey, endmarker, getvalue, description, matchlength=-1):
        if type(matchkey) == str:
            if matchkey[-1].isalnum():
                self.matchfunc = lambda s: (s.startswith(matchkey) and
                                            (len(s) <= len(matchkey) or not s[len(matchkey)].isalnum()))
            else:
                self.matchfunc = lambda s: s.startswith(matchkey)
                
            if matchlength == -1:
                self.matchlength = len(matchkey)
            else:
                self.matchlength = matchlength

        else:
            self.matchfunc = matchkey
            if matchlength == -1:
                self.matchlength = 1
            else:
                self.matchlength = matchlength

        self.endmarker = endmarker
        self.getvalue = getvalue
        self.description = description
        self.passname = ('name' in inspect.getargspec(getvalue)[0])

    def Matches(self, s):
        return self.matchfunc(s)

class OTFuncInfo(OTTypeInfo):
    """
    Helps with parsing the option tree file, used internally.
    """
    def __init__(self, *args):
        
        self.isuserfunc = False #Overridden if OTUserFunc is used

        self.name = args[0]
        function = args[1]

        self.evalimmediately = False
        description = self.name

        if len(args) > 2:
            if type(args[2]) == str:
                description = args[2]
            elif type(args[2]) == bool:
                self.evalimmediately = args[2]

        if len(args) > 3:
            if type(args[3]) == str:
                description = args[3]
            elif type(args[3]) == bool:
                self.evalimmediately = args[3]
            
        OTTypeInfo.__init__(self, self.name + '(', ')', function, description)

class OTUserFunc(OTFuncInfo):
    """
    What holds information about a user function, used internally.
    """

    def __init__(self, *args):
        OTFuncInfo.__init__(self, *args)
        self.isuserfunc = True
                    
class OTSearchFunc:
    def __init__(self, matchfunc, matchlength):
        self.matchfunc = matchfunc
        self.matchlength = matchlength

class OTChInfo:
    """
    Keeps track of information important to error parsing; used internally
    """
    def __init__(self, ch, line, column):
        self.ch = ch
        self.line = line
        self.column = column

# These are for linking stuff up
class LinkupBase:
    def __init__(self, string, loc, origsource, **kwargs):
        self.string = string
        self.loc = loc
        self.origsource = origsource
        self.__dict__.update(kwargs)

class OTSoftLink(LinkupBase):
    pass

class OTEvalStatement(LinkupBase):
    pass


######################################################################
# Define a function to evaluate

class OTFunctionEval:
    def __init__(self, branch, funcinfo, loc, rawvaluelist, name):
        self.branch = branch
        self.funcinfo = funcinfo
        self.loc = loc
        self.rawvaluelist = rawvaluelist
        self.name = name


class PyOptionTree:
    """
    PyOptionTree Description
    =================================================================

    +--------------------+--------------------------------------------+
    |Author:             |Hoyt Koepke                                 |
    +--------------------+--------------------------------------------+
    |Contact:            |hoytak@cs.ubc.ca                            |
    +--------------------+--------------------------------------------+
    |Version:            |0.21                                        |
    +--------------------+--------------------------------------------+
    |Date:               |2008-02-15                                  |
    +--------------------+--------------------------------------------+
    |License:            |MIT                                         |
    +--------------------+--------------------------------------------+
    |Download Site:      |http://sourceforge.net/projects/pyoptiontree|
    +--------------------+--------------------------------------------+

    The PyOptionTree class reads a set of parameters from a text file,
    string, or from the command line into a hierarchical structure
    easily accessed by the program.  It provides an intuitive but
    sufficiently flexible way for researchers, programmers, or
    developers to incorporate user-set parameters into their program.
    The goal is to allow the user to *both* specify parameters *and*
    modify, control, structure, copy, and record them in a way that
    minimizes the effort on both the programming end and the execution
    end.

    With PyOptionTree, you can specify parameters to your program in
    text files, on the command line, passed as a string, set manually,
    or any combination thereof. For example, you could specify a
    default set of options in a text file but override them using
    command line arguments.  
    
    To make this as user-friendly as possible, PyOptionTree uses a
    simple syntax -- similar to Python -- and a hierarchical tree
    structure to allow for more structured parameters than a flat list
    of option=value statements.  It also provides a number of
    operations -- including linking, copying, loading files,
    manipulating the parameters, and evaluating embedded Python code
    -- which are transparent to the program but allow the user to
    employ inheritance, duplication, etc. among branches of the
    tree. Of course, if you want to stick to a straight list of
    <option>=<value> pairs, PyOptionTree supports that.

    Additionally, PyOptionTree can print or save the current tree --
    or any branch thereof -- as a reloadable and easily edited option
    tree file that incorporates any type within the tree.  This makes
    it easy to log what parameters your program ran with and when.
    Furthermore, it makes it a natural way to incorporate a GUI into
    your program to edit the options or as a way of saving them.
    
    Example
    -------
    
    Suppose a program needs to run a series of tasks, each with
    separate, but sometimes similar, parameters.  Additionally,
    suppose the user is only interested in running a subset of the
    tasks she has parameters written for.  This can be expressed as::

      # This is a list of the tasks to run, each linked to their
      # definitions below.  This list will be returned to the user as
      # a list of subtrees, themselves PyOptionTrees.

      Tasks = [jog, eatcereal, eattoast]

      # The { } defines a subtree.  The subtree is itself an
      # PyOptionTree.
      jog = {
        name = \"Go Jogging\"
        action = \"jog\"
        minutes = 30
        location = \"park\"
        # etc.
      }

      # This subtree won't show up in the above list
      ridebike = {
        name = \"Ride the bike\"
        action = \"ride bike\"
        minutes = 90
        location = \"trail by house\"
        # etc.
      }

      eatcereal = {
        name = \"Eat Breakfast\"
        action = \"eat\"
        food = \"cereal\"
        location = \"kitchen\"
        # etc.
      }

    Now suppose all the parameters from 'eattoast' are the same as
    those of 'eatceral' except the value of the 'food' parameter.  We
    can copy the whole subtree and overwrite that parameter::

      eattoast = copy(eatcereal)
      eattoast/food = \"toast\"
      
    In our program, we could load and use the above with::

      def runTests(opttreefile):
          o = PyOptionTree(opttreefile)
          for t in o.Tasks:      # According to the above definition,
              runTest(t)         # t is a subtree (branch).
          
      def runTest(ot):
          print \'Current Action: \', ot.name
          # Decide what do based on ot.action...
          # Do the action...

    Now that we've looked at a quick example, let\'s move on to the
    good stuff.


    Syntax
    ------

    Every option file is simply a list of statements of the form
    <name> = <value>.  A single space or and end-delimiting character
    is sufficient to separate most <value> definitions from the next
    statement; if this presents a problem, a \';\' may be used.

    The value can be a string, number, list, tuple, another name, a
    string of python code to evaluate, a tree node, or a function
    call.  The standard syntax for each value type is described below.
 
    Names can consist of any alphanumeric characters or underscores.
    Referencing names not in the local tree is done exactly like on
    \*nix filesystem: local names are separated by'/', '..' moves up
    the tree, and starting with a '/' starts the referencing from the
    root node of the tree (be careful using this; the target changes
    between when the tree is read in as a subtree and when it is the
    base tree).  Thus::

      ../tree1/opt1 = 5

    moves up one level and sets the value of opt1 inside tree1 to 5.
    If trees do not exist, they are created (so the above command
    would create \'tree1\' if it didn\'t exist.)

    Assignments with the same name are always resolved to the last one
    specified.  In the case of trees; subsequent trees of the same
    name are merged into previous trees; otherwise, when reading in a
    tag, any previously stored value with that name is overwritten.

    Comments
    ++++++++

    PyOptionTree supports a number of possible comment strings.
    ``//``, ``#``, and ``%`` all comment out the rest of the line;
    everything between a ``/*`` and a ``*/`` is commented out (nested
    comments not supported).

    Escape Characters
    +++++++++++++++++

    Any character preceded by a backslash is escaped out, meaning that
    any special functionality (like commenting out something or
    denoting a string) it might carry is ignored.

    Retrieving Values
    +++++++++++++++++

    There are two methods for retrieving values.

    The first is using the ``get()`` method described in the method
    reference section below.  The simplest use takes a string with
    exactly the same syntax as a link.  The second is to retrieve the
    names as members of the tree.  Thus the following are identical::

      ot.get('tree/subtree/element')
      ot.tree.subtree.element

    The get() method offers two advantages.  First, it allows a
    default value to be specified; if an error occurs when retrieving
    the requested value, it returns the default instead of raising an
    exception.  Second, it allows a dictionary of variables to be
    passed to any eval() statement.
    
    Basic Value Types
    -----------------

    Possible types of the <value> token: 
    
    Strings 
      Strings start with either \" or \' and end with the same character
      (same as Python).

    Numbers
      Numbers can include digits, a decimal mark (period), a minus sign,
      and E notation without spaces (e.g. 1.45e-5 or 14.1E56).  

    Boolean
      Boolean values are denoted by the keywords \'True\' and \'False\'.

    None
      \'None\' (no quotes in file) or \';\' return the null value None. 

    Links
      Links are simply the name of another node.  They can be thought
      of like soft links in a Linux file system; when the option tree
      retrieves a parameter whose value is a link, it returns whatever
      value the link (or chain of links) points to. (Note that
      recursive links will result in an PyOptionTreeResolution exception
      at runtime.)

      There are two issues to be aware of.  The first is that, if the
      name of the assignment resolves to another tree (e.g. \'tree1/o1
      = 1\' or \'../o1 = 1\') links are always resolved starting from
      the location of the local assignment.  For example, the
      following is correct::

        o1 = 1
        tree1/o2 = ../o1

      but the following is not::
      
        o1 = 1
        tree1/o2 = o1
      
      This is to avoid confusion with how nodes are handled, i.e. so
      the statements \'tree1/o2 = ../o1\' and \'tree1 = {o2 = ../o1}\'
      are identical.

      The second issue is that links are only resolved when the user
      requests a value, thus in the following code::

        o1 = 1
        o2 = o1
        o1 = 2

      retrieving o2 will return 2.  (See the copy() function for
      different behavior).

    Lists
      Lists, as in Python, start with \'[\' and end with \']\' and
      contain a comma separated sequence of zero or more basic values.
      Nested lists are allowed.

      Links involving lists may contain references to specific
      elements, or sublists of elements.  The syntax is standard
      Python.  For example, the following are all valid, and produce
      the expected behavior::

        l = [1,2,3,4,5]
        i1 = l[4]
        i2 = l[-1]
        l1 = l[1:2]
        l2 = l[:-1]

      Additionally, assignments modifying individual elements are
      allowed::

        l = [1,2,3,4,5]
        l[0] = 10

      Here, ``l`` would return ``[10,2,3,4,5]``


    eval(...), @(...)
      Any valid Python statement that returns a value can be embedded
      in the option tree file using \'@\' or \'eval\' followed by
      parenthesis.  Values of other option tree names and local
      functions can be included in the statement using \'$\' followed
      by parenthesis containing a link to the value.  In the following
      code::

        o1 = 1
        o2 = @(1 + $(o1))

      o1 will be 1 and o2 will be 2.

      Evaluation is done when the value is retrieved, unless forced by
      now() (see below). Normally, the functions available are
      identical to those returned by the global() function; however,
      the user may supply a dictionary of additional functions and/or
      values when retrieving the value using the get() method.

    Tuples
      Tuples have the same syntax as lists, except they start with \'(\'
      and end with \')\'.

    Subtrees
      Subtrees are denoted with a pair of curly braces \'{\' \'}\'.
      In between is a list of <name> = <value> statements.  Thus in
      the following example::

        tree1 = {
          o1 = 5
        }

      the user would access o1 as opttree.tree1.o1 or
      opttree.get(\"tree1/o1\"), assuming the option tree is in the
      opttree variable.  

      Note that including another option tree file using the optfile()
      function and simply putting the contents of that file inside
      curly braces result in the same option tree.

    Functions
    ---------

    Functions take a comma separated sequence of basic types and
    return a value. The syntax is the same as Python (and a number of
    other languages). An example of the optfile() function (mentioned
    above and described below) is:

      tree_from_file = optfile(\"othertree.opt\")

    There are a number of built in functions for basic operations, and
    the user may supply a list of additional functions which may be
    part of the parameter input.  See the documentation on the
    addUserFunctions() method for more information.

    Functions are normally evaluated when the user asks for the
    parameter they are referenced to, which allows the arguments to be
    links to items defined later. copy(), file(), now() and reref()
    are evaluated during the parsing, so any links given as arguments
    must point to items already defined.

    The built in functions are:

    add(arg1, ...), cat(arg1, ...), sum(arg1, ...)
      All three of these have identical behavior and add up the list
      of arguments using the + operator in Python.  Specifically, they
      calculate ((...((arg1 + arg2) + arg3) + ...) + argn).

    copy(arg1 [, arg2, ...])
      copy() takes one or more arguments (usually links to other
      trees) and returns a copy of each. If one argument is given,
      copy() returns a value; if multiple arguments are given, it
      returns a list.  The copying is done by building an identical
      tree, making copies of all lists, tuples, dictionaries, and
      subtrees.  All relative links are modified so they point to the
      same elements they did originally (see reref() for alternate
      behavior).

      copy() and reref() are executed within the parsing, so all the
      arguments to copy must already be defined.  

      copy() allows the user to modify elements in a duplicate tree
      without actually changing the value in the original tree.  For
      instance, in the following example::

        tree1={o1 = 1}
        tree2=tree1
        tree2/o1 = 10

      both ``tree1/o1`` and ``tree2/o1`` will hold the number 10.
      Using copy()::

        tree1={o1 = 1}
        tree2=copy(tree1)
        tree2/o1 = 10
      
      results in ``tree1/o1 = 1`` and ``tree2/o1 = 10``.

      Note that copying one base tree and modifying specific elements
      gives inheritance-like behavior (as in the first example).
    
    dict(arg1, ...)
      dict() takes a list of tuples and turns them into a python
      dictionary.  The list may either be a comma separated list, an
      actual list type, or a link to a list. 

    optfile(arg1, ...)
      optfile() reads a set of option tree parameters from file arg1
      and returns an option tree containing them.  arg1 may be either
      a string (or a link that ultimately resolves to a string)
      specifying the file, or a tuple containing two strings, the
      first being the file name and the second being the source name
      (used in error reporting and the tree description).

      If multiple arguments are given, optfile() treats them as if
      they were continuations of the first file.  In other words, it
      loads all the parameters into the same option tree, with
      conflicts being resolved in favor of the last name specified.
      
    now(arg1)
      Forces evaluation of any contained functions (including those
      pointed to by links) at parse time instead of at retrieval time.
      arg1 can be any basic value.

    range([start, ] end [, step])
      range() produces a list of evenly spaced values.  If all
      arguments are given, it returns an ordered list of all numbers
      of the form `start + i*step` for i = 0,1,2,... such that `start
      <= n < end` if `step` is positive and `start >= n > end` if
      `step` is negative 0. If ommitted, `start` defaults to 0 and
      `step` to 1.  If all arguments are integers, all the elements in
      the list are integers, otherwise they are floating points.  The
      following are examples::
      
        range(5) = [0,1,2,3,4]
        range(-1,4) = [-1,0,1,2,3]
        range(1.5,0,-0.2) = [1.5,1.3, 1.1, 0.9,0.7,0.5,0.3,0.1]

    rep(string1, ...):
      rep() replaces all the occurences of links in string1 and any
      additional strings with the string representation of their
      retrieved values.  Links are specified using `${<link>}` and are
      referenced from the current location.  Thus in the following
      example::

        name = 'Hoyt'
        tree1 = {
          author=rep('This example was written by ${../name}')
        }

      `tree1/author` would equal 'This example was written by Hoyt'.

    reref(arg1 [, arg2, ...])
      reref() is identical to copy() except that only links given as
      direct arguments are followed; all other relative links within
      the tree are left unmodified.  As an illustration of why this
      might be useful, consider the following, which specifies two
      lists of cities::

        list1 = {
          style1 = \"Bold\"
          style2 = \"Normal\"

          # here a list of (name, style) tuples
          items = [(\"Colorado\", style1),
                   (\"Denver\", style2)]
        }

        list2 = {
          style1 = \"Underlined\"
          style2 = \"Tiny\"
          items = reref(../List1/items)
        }

      In this example, list1/items would return::

        [(\"Colorado\",\"Bold\"), (\"Denver\", \"Normal\")],

      and list2/items would return::

        [(\"Colorado\",\"Underlined\"),(\"Denver\", \"Tiny\")]

      Note that the \'style1\' link in the first item list points to
      list1/style1\', whereas the reref() in \'list2\' copies
      \'list1/items\' to \'list2/items\' without modifying the
      hyperlinks in the original; thus they now point to
      \'list2/style*\'.

    outer_product(opttree, field1, field2,...)
      outerProduct() generates a list of new option trees based on
      opttree but with any lists in field1, field2, ... (string names
      of lists in opttree) reduced to scalars. Each resulting option
      tree has exaclty one combination of the elements in these lists,
      with the full list of trees having every combination.

      For example, in::

        Foo = {
          a = [1, 2]
          b = [3, 4]
          c = 12
        }

        Bar = outerProduct(Foo, 'a', 'b', 'c')

      Bar would contain a list of four option trees::

        Bar[0] = {a = 1; b = 3; c = 12 }
        Bar[1] = {a = 1; b = 4; c = 12 }
        Bar[2] = {a = 2; b = 3; c = 12 }
        Bar[3] = {a = 2; b = 4; c = 12 }

    unpickle(arg1,...), unpickle_string(arg1,...)
      unpickle() loads a python object from a pickle file and returns
      it.  unpickle_string(arg1, ...) is identical except that it
      assumes the pickle is imbedded within the option file in the
      string arg1, etc.  If multiple arguments are given, both
      functions return a list of objects.

      On error, both functions throw a PyOptionTreeRetrievalError
      exception.

    Errors
    ------

    Errors are handled by exceptions.  They fall into three
    categories, parse errors, retrieval errors, and evaluation errors.
    Parse errors occur when parsing input and will raise a
    PyOptionTreeParseError exception.  Retrieval errors occur when the
    user asks for a non-existant value or a link within the tree
    can\'t be resolved; these raise a PyOptionTreeRetrievalError
    exception.  Evaluation Errors occur when code inside an evaluation
    statement raised an exception; these throw a
    PyOptionTreeEvaluationError exception.

    All three exceptions are derived from the base class
    PyOptionTreeException and return the error message when str() is
    used on an instance.

    Other Issues
    ------------

    If you have any problems with the code, run into cases where it
    doesn't work, are confused by the documentation, or have a comment,
    please email me at the address above.  This project is still very much in 
    beta test mode.

    License (MIT License)
    ---------------------

    Copyright (c) 2007 Hoyt Koepke

    Permission is hereby granted, free of charge, to any person
    obtaining a copy of this software and associated documentation
    files (the \"Software\"), to deal in the Software without
    restriction, including without limitation the rights to use, copy,
    modify, merge, publish, distribute, sublicense, and/or sell copies
    of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be
    included in all copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND,
    EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
    MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
    NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
    HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
    WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
    DEALINGS IN THE SOFTWARE.

    """


    # This is where all the parsing definitions are defined.
    __newlinetag = '__NL__' + OTRandTag()
    
    ########################################
    # Comments
    __commenttags = [
        ('/*',    '*/' ),
        ('<!--',  '-->'),
        ('//',    __newlinetag),
        ('%',     __newlinetag),
        ('#',     __newlinetag)]

    ########################################
    # These characters denote character pairs to skip over in parsing a value

    __nestchars = [
        ('(', ')', False),
        ('[', ']', False),
        ('{', '}', False),
        ('\"','\"',True),
        ('\'','\'',True)]

    __escapechar = '\\'
    __escaped_chars = {}
    __escaped_tag_prefix = '_EC_'
    __listsepchar = ','
    __equalchar   = '='

    def __init__(self, arg = None, userfunclist=[], **kwargs):
        """
        Initializes the option tree based on the type of arg. If arg
        is None or not given, it creates a new root node tree.  If arg
        is another PyOptionTree, then it creates an identical copy of
        arg.  If arg is a string, it assumes it is a filename and
        attempts to load the file name specified. If arg is a list,
        then it treats the list as a set of command line parameters
        (see addCommandLineArgs(...) for options; the lookforfiles
        parameter can be set by name here, e.g. lookforfiles=False)
        
        userfunclist is a list of user defined functions which is
        passed to addUserFunctions() before any parsing is done.  See
        help on addUserFunctions() for more information.
        
        """

        # Handle the defaults

        self.__opts = {}
        self.__cilist= []
        self.__chstr = []
        self.__setvarrank = 0

        # Test to see if we're a branch of a parent tree
        if 'parent' in kwargs:  
            self.__parent = kwargs['parent']
            self.__types = None             # Found by going to root
            self.__userfunclist = self.__parent.__userfunclist
            self.__treename = kwargs['treename']
            self.__sources = self.__parent.__sources
            self.__RecordSource(kwargs['treesource'])
        elif isinstance(arg, PyOptionTree):
            copyot = arg.copy()
            self.__opts = copyot.__opts()
            self.__parent = copyot.__parent
            self.__treename = copyot.__treename
            self.__sources = copyot.__sources
            self.__cilist = copyot.__cilist
            self.__chstr = copyot.__chstr
            self.__types = copyot.__types
            self.__userfunclist = copyot.__userfunclist
            if userfunclist != []:
                self.addUserFunctions(userfunclist)
        else:
            self.__treename = '/'
            self.__sources = []
            self.__parent = None
            self.__sources = []

            if userfunclist != []:
                self.__userfunclist = userfunclist
            else:
                self.__userfunclist = []

            self.__CreateTypeTable()

            if type(arg) == list:
                self.addCommandLineArgs(arg)

            if type(arg) == str:
                self.addOptionsFile(arg)

    #####################################################################
    #  Routines for setting/getting the options

    def addOptionsFile(self, infile, sourcename=''):
        """
        Opens and parses the file given by infile and all the
        parameters within it to the current option tree. If infile is
        a string, addOptionsFile attempts to open the file and parse
        the contents. If infile is a open file, it attempts to read
        the contents using readlines() and parse them. If infile is a
        list, it adds each file in order.  All earlier definitions of
        a parameter are overwritten by later definitions, so be
        careful of adding multiple files.  The list may be names, open
        files, or a mixture of both.
        """

        try:
            if type(infile) == str:
                # Preserve the current directory
                cwd = os.path.abspath(os.getcwd())

                d, f = os.path.split(infile)
                if len(d) != 0:  os.chdir(os.path.join(cwd, d))

                self.addOptionsFile(open(f,"r"), sourcename)

                os.chdir(cwd)
                
            elif type(infile) == file:
                self.addString(''.join([s.replace('\n', ' \n') for s in infile.readlines()]),
                               sourcename = (sourcename, infile.name)[sourcename == ''])
        except PyOptionTreeException, ote:
            raise ote                      
        
    def addCommandLineArgs(self, arglist, lookforfiles=True):
        """
        Takes a list of parameters given on the command line, usually
        sys.argv[1:], and adds them, in order, to the option tree,
        overwriting any previous parameters by the same name.  If
        lookforfiles is True (default), then option tree files may be
        specified with -f <filename> or --file=<filename>. 

        Command line options are given just like they are in files.  

        On the command line, specify the option file with -f
        <filename>.  Multiple files can be specified; any options with
        the same name are overwritten by the last one specified.  All
        the options within the files can be overwritten on the command
        line by specifying these as long options, i.e.::

          MyOption = <value>

        in the option file can be overwritten by::
        
          --MyOption=<newvalue>

        on the command line.
        
        """

        ol = []
        curnum = 1
        
        a = arglist

        try:
            while len(a) != 0:
                if lookforfiles and (a[0] == '-f' or a[0] == '--file'):
                    if a[1] == '=':
                        ol += [('f', curnum+2, a[2])]
                        curnum += 3
                        del a[:3]
                    else:
                        ol += [('f', curnum+1, a[1])]
                        curnum += 2
                        del a[:2]
                elif lookforfiles and (a[0] == '-f=' or a[0] == '--file='):
                    ol += [('f', curnum+1, a[1])]
                    curnum += 2
                    del a[:2]
                elif lookforfiles and (a[0].startswith('-f') or a[0].startswith('--file')):
                    pos = a[0].find('=')
                    if pos == -1:
                        raise PyOptionTreeParseError('Parsing Command Line Options', '\"' + a[0] + '\" not understood.')
                    ol += [('f', curnum, a[0][pos+1:])]
                    curnum += 1
                    del a[:1]
                elif len(a) > 1 and a[1] == '=':
                    ol += [('c', (curnum,curnum+2), a[0] + ' = ' + a[2])]
                    curnum += 2
                    del a[:3] 
                elif a[0].endswith('=') or (len(a) > 1 and a[1].startswith('=')):
                    ol += [('c', (curnum,curnum+1) , a[0] + ' ' + a[1])]
                    curnum += 2
                    del a[:2]
                elif a[0].find('=') != -1:
                    ol += [('c', curnum, a[0])]
                    curnum += 1
                    del a[:1]
                elif a[0].startswith('--'):
                    ol += ('c', (curnum, curnum+1), a[0] + ' = ' + a[1])
                    curnum += 2
                    del a[:2]
                else:
                    raise PyOptionTreeParseError('Parsing Command Line Options',
                                               'Unrecognized sequence: ' + ''.join([s + ' ' for s in a]))
        except IndexError:
            raise PyOptionTreeParseError('Parsing Command Line Options', 'Expected parameter at end.')

        try:
            for command, n, s in ol:
                if command == 'f':
                    self.addOptionsFile(s)
                elif command == 'c':
                    if type(n) == tuple:
                        source = '<Command line args ' + str(n[0]) + '-' + str(n[1]) + '>'
                    else:
                        source = '<Command line arg ' + str(n) + '>'

                    if s.startswith('--'):
                        self.addString(s[2:], sourcename = source) 
                    elif s.startswith('-'):
                        self.addString(s[1:], sourcename = source)
                    else:
                        self.addString(s, sourcename = source)
        except PyOptionTreeException, ote:
            raise ote
        
            
    def addString(self, s, sourcename = ''):
        """
        Adds options located in a string s.  Optionally, the source
        may be provided with a sourcename used by the description()
        and fullName() methods and the error reporting functions.
        """

        if sourcename == '':
            sourcename = '<string input>'

        cilist = []
        
        linenum, colnum = 1, 0
        escapeflag = False

        # Translate newline characters and escaped characters
        for c in s:
            colnum += 1
            if escapeflag:
                cilist += [OTChInfo(cc, linenum, colnum) for cc in self.__NewEscapedCharTag(c)]
                escapeflag = False
            elif c == self.__escapechar:
                escapeflag = True
            elif c == '\n':
                cilist += [OTChInfo(cc, linenum, colnum) for cc in self.__newlinetag]
                linenum += 1
                colnum = 0
            else:
                cilist += [OTChInfo(c, linenum, colnum)]

        cilist += [OTChInfo(cc, linenum, colnum) for cc in self.__newlinetag]

        chstr = ''.join([ci.ch for ci in cilist])

        elimstack = []

        # Eliminate all the comments, skipping immune nest chars

        searchpairs = ([(sc, (ec, False)) for sc,ec,t in filter(lambda (sc,ec,im): im, self.__nestchars)]
                       +[(sc, (ec, True)) for sc,ec in self.__commenttags])
        

        ps = 0
        while ps < len(chstr):
            changemade = False

            for ts, (te, cutout) in searchpairs:
                if chstr[ps:].startswith(ts):
                    pe = chstr[ps + len(ts):].find(te)
                    if pe == -1:
                        raise PyOptionTreeParseError(self.__LocString(cilist[ps:], action = 'Removing Comments'),
                                                     '\'' + ts + '\' missing end tag \'' + te + '\'')
                    if cutout: elimstack += [(ps, ps + pe + len(ts) + len(te))]
                    ps += pe + len(ts) + len(te)
                    changemade = True

            if not changemade: ps += 1
                
        #self.__dbprint('\n\n\n\n######################### Eliminating!')
        for es, ee in sorted(elimstack, reverse=True):
            #self.__dbprint(''.join([ci.ch for ci in cilist[es:ee]]))
            cilist[es:ee] = []

        # Now process the list
        try:
            self.__ParseCharList(''.join([ci.ch for ci in cilist]), cilist, sourcename)
        except PyOptionTreeException, ote:
            raise ote
        
    def get(self, name, default=OPTTREE_NONNONEXISTANTQUERY, vardict={}, recursionsleft=OPTTREE_MAXRECURSIONDEPTH):
        """
        Returns the parameter given by ``name``.  If ``default`` is
        given and the key is not found, or an error occurs retrieving
        the key, ``get()`` returns the default value instead of
        raising an exception.

        ``vardict`` is an optional dictionary of variables and/or
        functions that are used in addition to globals() when
        evaluating any of the Python code.
        
        ``name`` is in the same format as links, namely
        `tree1/subtree/parameter`.  Referencing from the root of the
        tree when ``get()`` is called from a subtree is possible with
        a \'/\' prefix, and moving from a subtree to a parent tree is
        possible using \'..\'.
        """

        required = (default == OPTTREE_NONNONEXISTANTQUERY)

        if recursionsleft == 0:
            raise PyOptionTreeRetrievalError(self.__LocString(), 'Maximum Recursion Depth Exceeded.')

        try:
            return self.__GetValue(name, default, required, vardict, recursionsleft)
        except PyOptionTreeException, ote:
            if required:
                raise ote.PrependMessage(self.__LocString(action='Resolving key \"' + name + '\"'))
            else:
                return default
            
    def __call__(self, name, default=OPTTREE_NONNONEXISTANTQUERY, vardict={}):
        """
        Identical to get().
        """

        return self.get(name,default,vardict)

    def isValid(self, name, vardict = {}):
        """
        Returns True if name exists and is valid (no errors) and False
        otherwise.  
        """

        try:
            return (self.get(name, default = OPTTREE_NONNONEXISTANTQUERY+'__', vardict=vardict)
                    != OPTTREE_NONNONEXISTANTQUERY + '__')
        except PyOptionTreeException, ote:
            raise ote

    def __contains__(self, name):
        """
        Same as isValid(name)
        """
        
        return self.isValid(name)

    def set(self, name, value):
        """
        Manually sets the value of an option. Returns a reference to
        the option tree.
        """

        if len(name) == 0:
            raise PyOptionTreeParseError(self.__LocString(action='Setting Value'), 'Empty name given.')            
        try:
            namelist = self.__Name2NameList(name)            
            self.__GetOrCreateBranch(namelist[:-1]).__SetValue(namelist[-1], value)
        except PyOptionTreeException, ote:
            raise ote.PrependMessage(self.__LocString(action='Setting key \"' + name + '\"'))

        return self
            
    def description(self):
        """
        Returns a description of the tree formed from the tree names
        and input sources on the path from the root to this node.
        """
        
        if self.parent() != None:
            s = self.parent().description() + '/'
        else:
            s = '/'

        return s + self.fullTreeName()

        
    def treeName(self):
        """
        Returns the name of the tree.
        """
        return self.__treename 

    def fullTreeName(self):
        """
        Returne the name of the tree along with sources.
        """

        if len(self.__sources) != 0:
            return self.treeName() + '(' + ''.join([s + ',' for s in self.__sources[:-1]]) + self.__sources[-1] + ')' 
        else:
            return self.treeName()

    def root(self):
        """
        Returns the root tree.
        """

        if self.__parent == None:
            return self
        else:
            return self.__parent.root()
            

    def parent(self):
        """
        Returns the parent of the tree, or ``None`` if it's the root.
        """

        return self.__parent

    def pathFromRoot(self):
        """
        Returns the list of tree names from the root of the tree to
        this one, starting with '/'.
        """
        
        if self.parent() == None:
            return ['/']
        else:
            return self.parent().pathFromRoot() + [self.treeName()]

    def nameFromRoot(self):
        """
        Returns the full name of the tree, referenced from the root.
        """
        
        return self.__NameList2Name(self.pathFromRoot())

    def items(self):
        """
        Returns a list of (<name>, <value>) tuples of all the
        parameters and branches in the local tree.
        """

        return [(n, self.__ReadyValue(v)) for n, (v, o) in self.__opts.items()]
    

    def itemList(self):
        """
        Returns a list of the names of all the items in the local tree.
        """

        return [n for n, (v, o) in self.__opts.items()]

    def leaves(self):
        """
        Returns a list of (<name>, <value>) tuples of all the
        parameters in the tree, excluding branches.
        """

        return [(n, v) for n,v in
                filter(lambda (n,v): not isinstance(v, PyOptionTree),
                       [(n,self.__ReadyValue(v)) for n,(v,o) in self.__opts.items()])]
    
    def leafList(self):
        """
        Returns a list of the names of all the parameters in the tree,
        excluding branches.
        """

        return [n for n,v in self.leaves()]

    def branches(self):
        """
        Returns a list of (<name>, <value>) tuples of all the branches
        in the tree.
        """

        return [(n, v) for n,v in
                filter(lambda (n,v): isinstance(v, PyOptionTree),
                       [(n,self.__ReadyValue(v)) for n,(v,o) in self.__opts.items()])]
    
    def branchList(self):
        """
        Returns a list of the names of the branches of the local tree.
        """
        return [n for n, v in self.branches()]
    

    def addUserFunctions(self, userfunclist):
        """
        Adds a list of user defined functions that help with the
        parsing, overriding any previously specified with the same
        name.  Each function will be passed the values given in the
        option tree (links will be followed and other functions will
        be evaluated).  Whatever it returns will be stored in that
        option parameter.

        Any exception propegates back up to the calling program.
        
        userfunclist is a list of 2 or 3 element tuples. The first
        element is the name of the function (str) and the second is
        the function itself.  Optionally, the third element may be
        True which signifies that the function should be evaluated
        when it's parsed instead of when the program requests it. An
        example list might be [('loadMyData', MyLoadFunction),
        ('loadmyDataNow', MyLoadFunction, True)].

        Calling the function works just like in Python.  If the
        function is called \"foo\", and the corresponding function is
        myFunc, then::

          earlierparam = 343
          myparam = foo('bar', 2, earlierparam)

        in the parameter file will produce a call to myFunc with
        'bar', 2, and 343 as the arguments and store the return value
        in myparam.

        """
        
        self.__userfuncs = userfunclist + self.__userfuncs        
        self.__CreateTypeTable()

    def copy(self):
        """
        Returns a copy of the tree.  If the tree has a parent, the
        copy would share the same parent and name as the original, but
        all name resolutions from the original node ignore this one.
        """

        ot = PyOptionTree(None, userfunclist = self.__userfunclist)
        ot.__parent = self.parent()
        ot.__treename = self.__treename
        ot.__sources = self.__sources
        ot.__opts = {}
        for k, (v, r) in self.__opts.items():
            #self.__dbprint('COPY>  Copying key=' + str(k) + '  v=' + str(v) + '   r=' + str(r) + '\n\n')
            ot.__SetValue(k, ot.__CopyIn(self, v, k, rerefsl = False), r)

        return ot

    def fetch(self, ot, *keys):
        """
        Imports all the keys and their corresponding retrieved values
        from the option tree ot into this tree.
        """

        for key in keys:
            if type(key) == list or type(key) == tuple:
                self.fetch(ot, *key)
            elif type(key) == str:
                self.set(key, ot(key))
    
    def printTree(self):
        """
        Prints the string representation of the tree to stdout.  See
        the reference for ``__str__()`` for info about the format of the
        string.

        """
        print str(self)

    def saveTree(self, filename):
        """
        Saves the tree to an option tree file given by ``filename``
        that can be reloaded and used.  Note that any existing file by
        the name of ``filename`` will be overwritten.
        """
        f = file(filename, 'w')
        f.write(str(self))
        f.close()

    def saveTreeAsLog(self, fileprefix, filesuffix='opt'):
        """
        Saves the tree to an option tree file that can be reloaded and
        used.  The name of the file is given by
        fileprefix-<timestamp>.filesuffix, and is thus useful for logging
        purposes.  The time stamp is in the format
        year-month-day-hour-min-sec, for example 2007-07-29-22-32-00,
        which indicates 10:32 pm on July 29, 2007.

        Note that the results of a test could be put into the tree
        using the set() method and then saved as part of the log file. 
        """
        self.saveTree(fileprefix +'-' + time.strftime("%Y-%m-%d-%H-%M") + '.' + filesuffix)

    def __str__(self):
        """
        Returns a string representation of the tree.  The string can
        be passed back to the ``addString()`` method to reproduce the tree
        exactly, assuming any user-defined types that are stored in
        the tree can be pickled and unpickled properly.

        All of the basic types and any functions not evaluated at
        parse time are turned into their string representations.  Any
        types without a representation as a basic value are turned
        into a Python pickle using protocol=0, which can be manually
        edited.  To make the file more readable, these are all put at
        the end of the file with links within the option tree pointing
        to them.

        This string can be saved as a valid option tree file;
        reloading it produces an exact copy of the tree when saved,
        assuming any dependent files that are not loaded at parse time
        haven't changed (see the ``now()`` function to force
        evaluation at parse time).

        Warning: If the given tree is not the root tree, any links
        pointing back to earlier nodes will be invalid.
        
        """

        return self.__TurnToString(level=0) 

    def string(self, includeheader=False):
        """
        This is the same as __str__(), but it allows some extra
        options.
        """
        return self.__TurnToString(level=0, includeheader=includeheader)

    def strhash(self):
        """
        Returns a string hash of alphanumeric characters of the option
        tree.  The current implementation is a little slow, as it
        retrieves all the values, thus it is immune to links and the
        like.
        """

        # return base64.b64encode(md5(self.string()).digest()).replace('/', '').replace('+', '')[:8]

        mhash = md5()

        def updatehash(v):
            if type(v) == list or type(v) == tuple:
                for ve in v: updatehash(ve)
            elif type(v) == dict:
                for k, ve in v.items():
                    updatehash(k)
                    updatehash(ve)
            elif type(v) == str:
                mhash.update(v)
            elif type(v) == float or type(v) == int:
                mhash.update(str(v))
            elif isinstance(v, PyOptionTree):
                mhash.update(v.strhash())
            else:
                mhash.update(cPickle.dumps(v))

        updatehash(self.items())

        return base64.b64encode(mhash.digest()).replace('/', '').replace('+', '')[:8]

    def __eq__(self, ot):
        """
        Tests the equality of two trees.  Currently uses hashes, which
        is slower than directly, but this will hopefully change soon.
        """

        if not isinstance(ot, PyOptionTree): return False


        return self.strhash() == ot.strhash()
    
        
    def update(self, udict):
        """
        This function updates the current option tree with all the
        key, value pairs in `udict`.  The keys can be anything in link
        format, and the value pairs can be any type.
        """

        for k,v in udict.items():
            self.set(k,v)

        return self

    def size(self):
        """
        Returns the number of variables and branches in this node of the tree.
        """
        
        return len(self.__opts)
    

    ######################################################################
    #  Automatic Python Functions

##     def __getattr__(self, name):
##          try:
##              return self.get(name)
##          except PyOptionTreeRetrievalError, pe:
##              raise AttributeError(name + ' not a valid attribute: ' + str(pe))

    def __copy__(self):
        """
        Identical to copy().
        """
        return self.copy()

    def __len__(self):
        """
        Identical to size()
        """
        
        return self.size()


    ######################################################################
    # Lookup tables for the parsing; initialized and deleted as needed to minimize storage requirements
    
    def __CreateTypeTable(self):

        ########################################

        # Type matching.  Tests in order of insertion; put most
        # frequent first for precedence Also note that these functions
        # are passed a branch pointer indicating which branch they
        # should use, so the 'self' is irrelevant.

        # Those labeled with OTTypeInfo are primitive types;

        notname = OTSearchFunc(lambda s: not OTIsNameChar(s[0:1]), 0)
        notnum  = OTSearchFunc(lambda s: not OTIsNumberChar(s[0:1]), 0)
        
        self.__types = [
            OTTypeInfo(lambda sh: sh[0].isdigit(), notnum, self.__Function_Number, 'Numeric',matchlength=0),
            OTTypeInfo('[',     ']',     self.__Function_List,     'List'),
            OTTypeInfo('(',     ')',     self.__Function_Tuple,    'Tuple'),
            OTTypeInfo('{',     '}',     self.__Function_Branch,   'Branch'),
            OTTypeInfo('\'',    '\'',    self.__Function_String,   'String'),
            OTTypeInfo('\"',    '\"',    self.__Function_String,   'String'),
            OTTypeInfo('..',    notname, self.__Function_SoftLink, 'SoftLink',matchlength=0),
            OTTypeInfo('./',    notname, self.__Function_SoftLink, 'SoftLink',matchlength=0),
            OTTypeInfo('/',     notname, self.__Function_SoftLink, 'SoftLink',matchlength=0),
            OTTypeInfo('@(',    ')',     self.__Function_Eval,     'Evaluation Code'),
            OTTypeInfo('eval(', ')',     self.__Function_Eval,     'Evaluation Code'),
            OTTypeInfo('-',     notnum,  self.__Function_Number,   'Numeric',matchlength=0),
            OTTypeInfo('.',     notnum,  self.__Function_Number,   'Numeric',matchlength=0),
            OTTypeInfo('_',     notname, self.__Function_SoftLink, 'SoftLink',matchlength=0),
            OTTypeInfo(';',     '',      self.__Function_None,     'Null Value'),

            # Append the functions; i.e. those that take a list of primitive types as their argument
            OTFuncInfo('dict',           self.__Function_Dict,     'Create Dictionary from list of tuples.'),
            OTFuncInfo('add',            self.__Function_CatList,  'Concatenation (+) List'),
            OTFuncInfo('cat',            self.__Function_CatList,  'Concatenation (+) List'),
            OTFuncInfo('sum',            self.__Function_CatList,  'Concatenation (+) List'),
            OTFuncInfo('rep',            self.__Function_Rep,      'String Replacement Function'),
            OTFuncInfo('optfile',        self.__Function_OptFile,  'Option Tree File', True),
            OTFuncInfo('copy',           self.__Function_Copy,     'Copy Item', True), 
            OTFuncInfo('reref',          self.__Function_ReRef,    'Copy Item (rereferenced)', True),
            OTFuncInfo('range',          self.__Function_Range,    'Creates sequence list (similar to range() in python)'),
            OTFuncInfo('seqrep',         self.__Function_SeqRep,   'Sequence Element Replacer'),
            OTFuncInfo('outer_product',  self.__Function_OuterProduct,'Expands option tree based on list fields'),
            OTFuncInfo('timestamp',      self.__Function_TimeStamp,'Create Time Stamp (python time.strftime())', True),
            OTFuncInfo('strftime',       self.__Function_TimeStamp,'Create Time Stamp (python time.strftime())', True),
            OTFuncInfo('now',            self.__Function_Now,      'Forces Evaluation During Parsing', True),
            OTFuncInfo('unpickle',       self.__Function_Unpickle, 'Unpickles an object from a pickle file'),
            OTFuncInfo('unpickle_string',self.__Function_Unpickle_string, 'Unpickles an object from a string')]

        
        # Append the user defined functions
        for l in self.__userfunclist:
            self.__types.append(OTUserFunc(*list(l)) )

        # These conflict with the more specific ones above; thus need to go at the end
        self.__types += [
            OTTypeInfo('None',  '',      self.__Function_None,     'Null Value'),
            OTTypeInfo('True',  '',      self.__Function_TrueBool, 'Bool Value'),
            OTTypeInfo('true',  '',      self.__Function_TrueBool, 'Bool Value'),
            OTTypeInfo('Yes',   '',      self.__Function_TrueBool, 'Bool Value'),
            OTTypeInfo('yes',   '',      self.__Function_TrueBool, 'Bool Value'),
            OTTypeInfo('False', '',      self.__Function_FalseBool,'Bool Value'),
            OTTypeInfo('false', '',      self.__Function_FalseBool,'Bool Value'),
            OTTypeInfo('No',    '',      self.__Function_FalseBool,'Bool Value'),
            OTTypeInfo('no',    '',      self.__Function_FalseBool,'Bool Value'),
            OTTypeInfo(lambda sh: sh[0].isalpha(), notname, self.__Function_SoftLink, 'SoftLink',matchlength=0)]
    
    ######################################################################
    #   Helper functions for setting things
            
    def __SetValue(self, name, value, rank=None):
        # This assumes name is local; use __GetOrCreateBranch to reach this point
        if type(name) == tuple and len(name) == 1:
            name = name[0]
        elif type(name) == str and name.find('[') != -1:
            name = self.__Name2NameListIndices(name)

        if type(name) == tuple:

            #self.__dbprint("SETVALUE>  Getting tuple value")
            v = self.__GetValue([name[0]], default = OPTTREE_NONNONEXISTANTQUERY, required = False, readyvalue=False)
            #self.__dbprint("SETVALUE>  Creating Seq Rep")
            if v == OPTTREE_NONNONEXISTANTQUERY:
                v = []
            self.__SetValue(name[:-1],
                            OTFunctionEval(branch=self,
                                           funcinfo=OTFuncInfo('seqrep',self.__Function_SeqRep,'Sequence Element Replacer'),
                                           loc = None,
                                           rawvaluelist = [v, (name[-1], value)],
                                           name=self.__NameList2Name(name[:-1])))
        else:
            if name == './': return
            self.__VerifyName(name)

            if rank == None:
                rank = self.__setvarrank
                self.__setvarrank += 1
            self.__opts[name] = (value, rank)
        return value
                 
    def __GetOrCreateBranch(self, namelist):

        if type(namelist) == str:
            namelist = self.__Name2NameList(namelist)

        if namelist == []:
            return self
        elif namelist[0] == '/':
            return self.root().__GetOrCreateBranch(namelist[1:])
        elif namelist[0] == '..':
            if self.__parent == None:
                raise PyOptionTreeParseError(self.__LocString(action='Walking Tree'), 'No parent to resolve \'' + '..' +'\' to.')
            return self.__parent.__GetOrCreateBranch(namelist[1:])
        else:
            if namelist[0] not in self.__opts:
                return self.__SetValue(self.__NameList2Name([namelist[0]]),
                                       self.__NewBranch(self.__NameList2Name([namelist[0]])).__GetOrCreateBranch(namelist[1:]))
            else:
                try:
                    v = self.get(self.__NameList2Name(namelist[0]))
                except PyOptionTreeException, ote:
                    raise ote.PrependMessage(self.__LocString(action='Walking Tree (Branch \"' + self.__NameList2Name([namelist[0]]) + '\"' ))

                if isinstance(v, PyOptionTree):
                    return v.__GetOrCreateBranch(namelist[1:])
                else:
                    raise PyOptionTreeParseError(self.__LocString(action='Creating Branch'),
                                               'Name \"' + self.__NameList2Name([namelist[0]]) + '\" already declared as a non-branch item.')

    def __CreateNewBranch(self, name):
        if type(name) == str:
            l = self.__Name2NameList(name)
            return self.__GetOrCreateBranch(l[:-1]).__NewBranch(self.__NameList2Name([l[-1]]))
        else:
            return self.__GetOrCreateBranch(name[:-1]).__NewBranch(self.__NameList2Name([name[-1]]))
    
    def __NewBranch(self, name):
        #self.__dbprint('NEWBRANCH> treename ' + name)
        return PyOptionTree(isbranch=True, parent = self, treename = name, treesource = self.__CurSource())

    ######################################################################
    #   Helper functions for finding and retrieving stuff

    def __GetValue(self, name, default=None, required=True, vardict={},
                        recursionsleft=OPTTREE_MAXRECURSIONDEPTH,readyvalue=True):
        #  Does the real workings of retreiving a value.

        if type(name) == str:
            name = self.__Name2NameList(name)

        if name[0] == '/':
            return self.root().__GetValue(name[1:], default, required, vardict, recursionsleft, readyvalue)
        else:
            v = self.__RetrieveLocalValue(name[0], default, required, vardict, recursionsleft, readyvalue)
            
            if len(name) == 1:  
                # If we're at the end; get the value; if we're not, pass it on
                return v
            else:
                if isinstance(v, PyOptionTree):
                    return v.__GetValue(name[1:], default, required, vardict, recursionsleft, readyvalue)
                else:
                    if not required:
                        return default
                    else:
                        raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Value'),
                                                        '\"' + str(name[0]) + '\" is not a branch.')

    def __RetrieveLocalValue(self, namekey, default=None, required=True,
                             vardict={}, recursionsleft=OPTTREE_MAXRECURSIONDEPTH, readyvalue=True):
        if type(namekey) == tuple:
            # okay, we have a tuple to resolve.  This indicates we
            # have to return an element of an array
            v = self.__RetrieveLocalValue(namekey[0], default,required,vardict,recursionsleft)
            
            for idx in xrange(1, len(namekey)):
                n = namekey[idx]
                if type(v) == list or type(v) == tuple:
                    n = self.__ReadyValue(n, vardict=vardict, recursionsleft = recursionsleft)
                    
                    if type(n) == int:
                        try:
                            v = v[n]
                        except Exception, e:
                            if required:
                                raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Indexed Value'),str(e))
                            else:
                                return default
                            
                    elif type(n) == list or type(n) == tuple:
                        try:
                            v = [v[ne] for ne in n]
                        except Exception, e:
                            if required:
                                raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Indexed Value'),str(e))
                            else:
                                return default
                    else:
                        try:
                            v = eval('VARLIST[' + n + ']', {}, {'VARLIST' : v})
                        except Exception, e:
                            if required:
                                raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Indexed Value'),str(e))
                            else:
                                return default

##                 elif type(v) == dict:
##                     if type(n) == int:
##                         try:
##                             v = v[n]
##                         except:
##                             raise PyOptionTreeParseError(self.__LocString(action='Retrieving Keyed Value'),
##                                                        'Key \"' + str(n) + '\" not valid.')
##                     else:
##                         try:
##                             k = self.__ReadyValue(self.__ParseValue( (0, len(n)), name, n))
##                             v = v[k]
##                         except PyOptionTreeException, ote:
##                             raise ote.PrependMessage(self.__LocString(action='Retrieving Keyed Value'))
##                         except Exception, e:
##                             raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Keyed Value'), str(e))
                else:
                    if required:
                        raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Indexed Value'),'Indexing non-list or tuple' )
                    else:
                        return default

            if readyvalue:
                return self.__ReadyValue(v, default, required, vardict, recursionsleft)
            else:
                return v
        else:
            if namekey == '..':
                if self.__parent == None:
                    if required:
                        raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Value'),
                                                         'No parent to resolve \'..\' to.')
                    else:
                        return default
                else:
                    return self.__parent
            elif namekey in self.__opts:
                if readyvalue:
                    return self.__ReadyValue(self.__opts[namekey][0], default, required, vardict, recursionsleft)
                else:
                    return self.__opts[namekey][0]
            else:
                if required:
                    raise PyOptionTreeRetrievalError(self.__LocString(action='Retrieving Value'),
                                                     'Key \"' + namekey + '\" does not exist.')
                else:
                    return default

    ######################################################################
    # Functions for preparing a value; i.e. following softlinks, evaluating statements, etc.
    
    def __ReadyValue(self, v, default=None, required=True,
                     vardict={}, recursionsleft=OPTTREE_MAXRECURSIONDEPTH):
        # Resolve softlinks and evaluate statements

        if type(v) == list:
            try:
                return [self.__ReadyValue(val, default, required, vardict, recursionsleft) for val in v]
            except PyOptionTreeException, ote:
                if required:
                    raise ote.PrependMessage(self.__LocString(action='Preparing List'))
                else:
                    return default
        elif type(v) == tuple:
            try:
                return tuple([self.__ReadyValue(val, default, required, vardict, recursionsleft) for val in v])
            except PyOptionTreeException, ote:
                if required:
                    raise ote.PrependMessage(self.__LocString(action='Preparing Tuple'))
                else:
                    return default
        elif type(v) == dict:
            try:
                return dict([(self.__ReadyValue(key, default, required, vardict, recursionsleft),
                              self.__ReadyValue(val, default, required, vardict, recursionsleft))
                             for key, val in v.items()])
            except PyOptionTreeException, ote:
                if required:
                    raise ote.PrependMessage(self.__LocString(action='Preparing Dictionary'))
                else:
                    return default
        elif type(v) == str:
            return self.__OriginalString(v)
        elif isinstance(v, OTSoftLink):
            try:
                if required:
                    return self.get(v.string, vardict=vardict, recursionsleft=recursionsleft-1)
                else:
                    return self.get(v.string, default, vardict=vardict, recursionsleft=recursionsleft-1)

            except PyOptionTreeException, ote:
                if required:
                    raise ote.PrependMessage(self.__LocString(v.loc, 'Resolving SoftLink to \"' + v.string + '\"',
                                                              v.origsource))
                else:
                    return default
        elif isinstance(v, OTEvalStatement):
            try:
                return self.__EvaluateStatement(v, vardict, recursionsleft)
            except PyOptionTreeException, ote:
                if required:
                    raise ote.PrependMessage(self.__LocString(v.loc, 'Evaluating exec statement', v.origsource))
                else:
                    return default
        elif isinstance(v, OTFunctionEval):
            try:
                return self.__EvaluateStoredFunction(v, default, required, vardict, recursionsleft)
            except PyOptionTreeException, ote:
                raise ote.PrependMessage(self.__LocString(pos = v.loc,
                                                          action = 'Evaluating Function \"' + v.funcinfo.name +'\" ('
                                                          + v.funcinfo.description + ')'))
        else:
            return v
        

    def __EvaluateStatement(self, evs, vardict, recursionsleft=OPTTREE_MAXRECURSIONDEPTH):
        # This evaluates the statement given...

        # First go through and retrieve the variables in the original vardict

        rvars = vardict.copy()

        try:
            for k, e in evs.sldict.items():
                #self.__dbprint("k=" + str(self.__Value2Str(1,e,0)))
                rvars[k] = self.__ReadyValue(e, vardict=vardict, recursionsleft=recursionsleft-1)
        except PyOptionTreeException, ote:
            raise ote.PrependMessage(self.__LocString(evs.loc, action = 'Evaluating Expression',
                                                source = evs.origsource))

        try:
            #self.__dbprint('EVAL> ' + str(evs.string) + ' >< Locals = ' + str(rvars))
            return eval(evs.string, globals(), rvars)
        except Exception, e:
            errstring = self.__LocString(evs.loc, action = 'Evaluating Expression', source =evs.origsource)
            raise PyOptionTreeEvaluationError(errstring, str(e))

    def __FindPairs(self, s, cilist, p1, p2):

        ret = []

        p = 0
        while True:
            np = s[p:].find(p1)
            if np == -1:
                break
            
            np += p
            startp = np + len(p1)
            endp = self.__NextInstance(startp, p2, len(s), s)

            if endp == -1:
                if cilist != None:
                    raise PyOptionTreeParseError(self.__LocString(cilist[np], action = 'Finding (\'' + p1 + '\', \'' + p2 + '\' pairs.'),
                                                 '\'' + p1 + '\' token not terminated with \'' + p2 + '\'')
                else:
                    raise PyOptionTreeParseError(self.__LocString(None, action = 'Finding (\'' + p1 + '\', \'' + p2 + '\' pairs.'),
                                                 '\'' + p1 + '\' token not terminated with \'' + p2 + '\'')

            ret += [ (np, startp, endp, endp + len(p2) )]
            p = endp + 1

        return ret

    def __EvaluateStoredFunction(self, sf, default=None, required=True, vardict={}, recursionsleft=OPTTREE_MAXRECURSIONDEPTH):

        funcargs = inspect.getargspec(sf.funcinfo.getvalue)[0]

        if sf.funcinfo.isuserfunc:
            return self.__ReadyValue(sf.funcinfo.getvalue(*sf.branch.__ReadyValue(sf.rawvaluelist, recursionsleft = recursionsleft)))
        else:
            kwargs = {}

            if 'branch' in funcargs:
                kwargs['branch'] = sf.branch
            if 'loc' in funcargs:
                kwargs['loc'] = sf.loc
            if 'rawvaluelist' in funcargs:
                kwargs['rawvaluelist'] = sf.rawvaluelist
            if 'valuelist' in funcargs:
                kwargs['valuelist'] = sf.branch.__ReadyValue(sf.rawvaluelist, recursionsleft = recursionsleft)
            if 'name' in funcargs:
                kwargs['name'] = sf.name
            if 'readyfunc' in funcargs:
                kwargs['readyfunc'] = lambda v: sf.branch.__ReadyValue(v, default, required, vardict, recursionsleft)

            return self.__ReadyValue(sf.funcinfo.getvalue(**kwargs))
    
    ######################################################################
    #  Tools for name bookkeeping

    def __Name2NameList(self, name):

#        brloc = name.find('[')
#        if brloc == -1:
        l = [s.strip() for s in name.split('/')]
#        else:
            
        if l[0] == '' and len(l) != 1:
            l[0] = '/'
            
        # Allow us to resolve to an option tree
        l= [self.__Name2NameListIndices(s) for s in
            self.__CollapseNameList(filter(lambda s: s != '' and s != '.',l))]
#        #self.__dbprint("SPLIT NAME $" + name + "$ into " + str(l))
        return l

    def __Name2NameListIndices(self, name):
        indexstart = name.find('[')

        if indexstart == -1:
            return name
        else:
            pos = indexstart
            namekey = [name[:indexstart]]

            while True:
                newpos = name[pos:].find('[')
                
                if newpos == -1:
                    break
                
                newpos += pos + 1

                endpos = self.__NextInstance(newpos, ']', len(name), name)
                
                if endpos == len(name):
                    raise PyOptionTreeRetrievalError(self.__LocString(action='Determining Name Indices'), 'Parse Error: matching \']\' not found.')
                try:
                    n = int(name[newpos:endpos])
                except:
                    n = name[newpos:endpos].strip()
                
                namekey += [n]
                pos = endpos + 1

        return tuple(namekey)


    def __CollapseNameList(self, l):
        pos = 0
        while True:
            if pos >= len(l)-1:
                return l
            if l[pos] != '..' and l[pos+1] == '..':
                l[pos:pos+1] = []
            else:
                pos += 1

    def __NameList2Name(self,l):

        if type(l) == tuple or type(l) == str:
            l = [l]

        if l == []:
            return './'

        if l[0] == '/':
            n = '/'
            spos = 1
        else:
            n = ''
            spos = 0

        for li in l[spos:]:
            if type(li) == tuple:
                n += li[0] + '[' + ''.join([str(i) + '][' for i in li[1:-1]]) + str(li[-1]) + ']/'
            else:
                n += li + '/'
        
        return n[:-1]  # Ignore last '/'

    def __TidyName(self, n):
        return self.__NameList2Name(self.__CollapseNameList(self.__Name2NameList(n)))

    def __VerifyName(self, name):
        if name == '':
            raise PyOptionTreeParseError(self.__LocString(action='Verifying Name'), 'Empty Name')

       # Verify the name
        for c in name:
            if not (c.isalnum() or c == '_'):
                raise PyOptionTreeParseError(self.__LocString(action='Verifying Name'), 'Character \''
                                           + c + ' in name \"' + name + '\" not alphanumeric or \'_\'')
        if not (name[0] != '_' or name[0].isalpha()):
            raise PyOptionTreeParseError(self.__LocString(action='Verifying Name'),'Name \"' + name + '\" cannot start with \''
                                         + name[0] + '\'; must be alphabetic or \'_\'')

    #####################################################################
    #  Routine for adding in the options

    def __ParseCharList(self, chstr, cilist, source):
        """
        Main routine for adding in the options.  Used internally and between trees.
        """
        
        self.__RecordSource(source)
        
        #self.__dbprint('__PARSECHARLIST: STARTINGSTRING = $' + self.__TruncateErrorString(chstr) + '$')

        # Add the current parsing information to the stack
        self.__chstr += [chstr]
        self.__cilist += [cilist]

        # Run with them
        (rl, rr) = self.__ShrinkRange( (0, len(self.__ChS())) )
        
        while True:
            p = self.__NextInstance(rl, self.__equalchar, rr)
            
            if p == rr:
                if rl < rr:
                    raise PyOptionTreeParseError(self.__LocString(rl, action = 'Parsing Token'),
                                               'Token \"' + self.__TruncatedErrorString( (rl, rr) )
                                               + '\" not of form <tag> = <value>') 
                else:
                    break
            
            tagr = self.__ShrinkRange( (rl, p) )
            #self.__dbprint('PARSECHARLIST> tag = ' +  '$' + self.__TruncateErrorString(self.__ChS()[tagr[0]:tagr[1]]) + '$')

            try:
                name = self.__TidyName(self.__OriginalString(tagr))
            except PyOptionTreeException, ote:
                raise ote.PrependMessage(self.__LocString(tagr, action = 'Parsing Name'))
                
            valuer = (self.__NextNonWSPos(p+1, skipsemicolons = False), rr)

            #self.__dbprint('value =    ' '$' + self.__TruncateErrorString(self.__ChS()[valuer[0]:valuer[1]]) + '$')
            
            try:
                # Now get the value and set it
                #self.__dbprint('__ParseCharList name =    ' + name)         
                namel = self.__Name2NameList(name)
                #self.__dbprint('__ParseCharList name list =    ' + str(namel))
                destbranch = self.__GetOrCreateBranch(namel[:-1])
                if len(namel) == 0:
                    varname = './'
                else:
                    varname = self.__NameList2Name(namel[-1])
                #self.__dbprint('__ParseCharList varname =    ' + varname)
                #self.__dbprint("IN PARSECHARLIST: self.__ChS() = " + self.__TruncateErrorString(self.__ChS()))
                destbranch.__chstr += [self.__ChS()]
                destbranch.__cilist += [self.__CiL()]
                (value, endpos) = destbranch.__ParseValue(valuer, varname)
                destbranch.__chstr.pop()
                destbranch.__cilist.pop()
                destbranch.__SetValue(varname, value)
            except PyOptionTreeException, ote:
                raise ote.PrependMessage(self.__LocString(rl, action = 'Parsing Token ' + self.__TruncateErrorString(name)))
            
            rl = self.__NextNonWSPos(endpos)

        # Clean up unneeded memory as we use a lot of it
        self.__chstr.pop()
        self.__cilist.pop()

    def __ParseValue(self, r, name):
        # Resolve the item

        #self.__dbprint("PARSEVALUE> : self.__ChS() = $" + self.__TruncateErrorString(self.__ChS()) +"$" )
        #self.__dbprint("PARSEVALUE> : self.__ChS()[r..] = $" + self.__TruncateErrorString(self.__ChS()[r[0]:r[1]]) + "$")
                
        r = self.__ShrinkRange(r, skipsemicolons = False)
        if r[0] >= r[1]:
            return (None, r[1])

        for t in self.__TypeList():
            if t.Matches(self.__ChS()[r[0]:r[1]]):
                rl = r[0] + t.matchlength

                endpos = self.__NextInstance(rl, t.endmarker, r[1])

                erroractionstr = self.__LocString(r, action = 'Parsing $' + self.__TruncateErrorString(self.__ChS()[rl:]) + '$ As ' + t.description)

                #self.__dbprint('PARSEVALUE> Parsing $' + self.__TruncateErrorString(self.__ChS()[rl:]) + '$ As ' + t.description)
                
                if endpos == r[1] and type(t.endmarker) == str and len(t.endmarker) != 0: 
                    raise PyOptionTreeParseError(self.__LocString(action = erroractionstr),
                                                 'Terminating \'' + t.endmarker + '\' not found.')

                # Get the value
                try:
                    if isinstance(t, OTFuncInfo):
                        rvl = self.__Function_List(self, (rl, endpos), name=name)

                        otf = OTFunctionEval(branch=self, funcinfo=t, loc = self.__MakeLocTag((rl, endpos)),
                                             rawvaluelist = rvl, name=name)

                        if t.evalimmediately:
                            v = self.__ReadyValue(otf)
                        else:
                            v = otf
                    else:
                        if t.passname:
                            v = t.getvalue(self, (rl, endpos), name=name)
                        else:
                            v = t.getvalue(self, (rl, endpos))
                    
                except PyOptionTreeException, ote:
                    raise ote.PrependMessage(self.__LocString( (rl, endpos), action = erroractionstr))

                return (v, endpos + self.__Len(t.endmarker))

        # Nothing matches, so...
        raise PyOptionTreeParseError(self.__LocString(r, action = 'Parsing Value'),
                                   'Type not recognized: \"'
                                   + self.__TruncateErrorString(self.__ChS()[r[0]:]) + '\"')

    ######################################################################
    # Parsing the various things 

    ####################
    # Numeric
    def __Function_Number(self, branch, r):
        r = branch.__ShrinkRange(r);
        s = branch.__OriginalString(r);
        try:
            if s.find('.') != -1:
                return float(s)
            else:
                return int(s)
        except ValueError:
            raise PyOptionTreeParseError(branch.__LocString(r, action = 'Parsing Number'),
                                         'Unable to convert \"' + s + '\" to a numeric value.')
    ####################
    # Strings
    def __Function_String(self, branch, r):
        return branch.__OriginalString(r)

    ####################
    # List
    def __Function_List(self, branch, r, name):
        # First split up the list
        r = branch.__ShrinkRange(r)
        rl = r[0]
        l = []

        try:
            while rl < r[1]:
                (v, ep) = branch.__ParseValue( (rl, r[1]), name + '[' + str(len(l)) + ']')
                l += [v]
                rl = branch.__NextInstance(ep, self.__listsepchar, r[1]) + 1
                
        except PyOptionTreeException, ote:
            raise ote.PrependMessage(branch.__LocString(r[0], action = 'Parsing Sequence '))

        return l

    ####################
    # Tuples
    def __Function_Tuple(self, branch, r, name):
        return tuple(branch.__Function_List(branch,r, name))

    ####################
    # Branch
    def __Function_Branch(self, branch, r, name):

        ot = branch.__GetOrCreateBranch(name)
        #self.__dbprint("__FUNCTION_BRANCH: STRING = " + branch.__TruncatedErrorString(r))
        ot.__ParseCharList(branch.__ChS()[r[0]:r[1]], branch.__CiL()[r[0]:r[1]], branch.__CurSource())
        return ot

    ####################
    # Soft Link
    def __Function_SoftLink(self, branch, r):
        (rl, rr) = branch.__ShrinkRange(r)
        #print "SOFTLINK = " + branch.__TidyName(branch.__OriginalString(branch.__ChS()[rl:rr]))
        return OTSoftLink(branch.__TidyName(branch.__OriginalString(branch.__ChS()[rl:rr])),
                          branch.__MakeLocTag( (rl, rr) ), branch.__CurSource())

    ####################
    # Evaluation statement
    def __Function_Eval(self, branch, r):
        (rl, rr) = branch.__ShrinkRange(r)

        estr = branch.__ChS()[rl:rr]
        elist = branch.__CiL()[rl:rr]

        sl = list(estr)

        try:
            pairs = branch.__FindPairs(estr, elist, '$(', ')') + branch.__FindPairs(estr, elist, '${', '}')
        except PyOptionTreeException, ote:
            errs = branch.__LocString(elist, action = 'Tying Variables in Evaluation Code')
            raise ote.PrependMessage(errs)

        vdict = {}

        #self.__dbprint('OT_FUNCTION_EVAL> Pairlist = ' + str(pairs))
        
        for p in reversed(pairs):
            varrepname = 'VAR_' + OTRandTag()
            vdict[varrepname] = branch.__ParseValue( (rl+p[1], rl+p[2]), varrepname)[0] 
            sl[p[0]:p[3]] = list(varrepname+' ')
        

        #self.__dbprint('OT_FUNCTION_EVAL> sl = ' + ''.join(sl))
        return OTEvalStatement(self.__OriginalString(''.join(sl)),
                               loc=branch.__MakeLocTag( (rl, rr) ),
                               origsource=branch.__CurSource(),
                               sldict=vdict,
                               origstring=self.__OriginalString(estr))

    def __Function_None(self, branch, r, name):
        return None

    ####################
    # Bool
    def __Function_TrueBool(self, branch, r, name):
        return True

    def __Function_FalseBool(self, branch, r, name):
        return False


    ######################################################################
    # Now the functions (non-primitives)


    def __Function_WrapListEval(self, func, valuelist, firstlevel=True):
        # First a function that helps handle the fact that arguments are
        # given as lists, and functions are expected to return a single
        # value if only one is given, and a list if there are multiple
        # ones.  Sends only non-list items 
        
        if type(valuelist) != list:
            return func(valuelist)
        
        if len(valuelist) != 0:
            l = [self.__Function_WrapListEval(func, v, False) for v in valuelist]
            if firstlevel and len(l) == 1:
                return l[0]
            else:
                return l
        else:
            return None
                
    ####################
    # List for concatenating
    def __Function_CatList(self, valuelist, loc):

        if valuelist == []:
            return None

        tot = valuelist[0]

        for v in valuelist[1:]:
            try:
                tot = tot + v
            except Exception, e:
                raise PyOptionTreeRetrievalError(self.__LocString(pos=loc, action = '+ing values'), str(e))

        return tot

    ####################
    # Option File
    def __Function_OptFile(self, branch, valuelist, name):
        ot = branch.__GetOrCreateBranch(name)

        errlist = []
        
        files = [(t, (t,t))[type(t) != tuple] for t in valuelist]
        for t in files:
            if len(t) != 2 or type(t[0]) != str or type(t[1]) != str:
                raise PyOptionTreeParseError(branch.__LocString(action = "Importing Option File"),
                                             "Expected 2-tuple (file, name) or string, got \'" + str(t) +"\'" )
        
        for f, n in files:
            f, n = f.strip(), n.strip()
            
            try:
                ot.addOptionsFile(f, sourcename=n)
            except IOError, ioe:
                errlist += ['Error Opening File \'' + n + '\': ' + str(ioe) + '\n']
            except PyOptionTreeException, ote:
                errlist += [ote.message]
        
        if len(errlist) > 0:
            raise PyOptionTreeParseError(branch.__LocString(action = str(valuelist)),
                                       ''.join(errlist))

        return ot


    ######################################################################
    #   Functions to perform copies

    def __Function_Copy(self, branch, rawvaluelist, name):
        return branch.__CopyInitialList(rawvaluelist, name, True)

    def __Function_ReRef(self, branch, rawvaluelist, name):
        return branch.__CopyInitialList(rawvaluelist, name, False)

    def __CopyInitialList(self, rawvaluelist, name, rerefsl = True):
        if len(rawvaluelist) == 0:
            return None
        elif len(rawvaluelist) == 1:
            return self.__CopyIn(None, rawvaluelist[0], name, rerefsl)
        else:
            return self.__CopyIn(None, rawvaluelist, name, rerefsl)

    def __CopyIn(self, srcbranch, v, name, rerefsl = True, depth = -1):

        # Copies v, assumed to be a member of
        # srcbranch, into self.  self. has name name.
        
        #-1 for depth indicates it's waiting for src branch
        if type(v) == list:
            return [self.__CopyIn(srcbranch, e, name + '[' + str(i) + ']', rerefsl, depth)
                    for e, i in zip(v, xrange(len(v)))]
        elif type(v) == tuple:
            return tuple(self.__CopyIn(srcbranch, list(v), name, rerefsl, depth))
        elif isinstance(v, PyOptionTree):
            ot = self.__GetOrCreateBranch(self.__Name2NameList(name))

            ot.__sources = self.__sources            
            
            for k, e, n in sorted([(k,e,n) for k, (e,n) in v.__opts.items()], key=itemgetter(2)):
                ot.__SetValue(k, ot.__CopyIn(v, e, k, rerefsl, depth+1))
            return ot
        elif isinstance(v, OTSoftLink):
            # If v points outside the tree, add prefix if reref is true,
            # if v is internal or absolute, leave alone.            

            if srcbranch == None:
                # Okay, don't know the src branch yet; need to resolve this til we find it
                try:
                    return self.__CopyIn(srcbranch, self.__GetValue(v.string, readyvalue=False),
                                         name, rerefsl, depth)
                except PyOptionTreeException, ote:
                    raise ote.PrependMessage(self.__LocString(action='In __CopyIn, srcbranch setting.'))
            else:
                ts = v.string
                if ts[0] == '/':
                    return v 
                else:
                    tl = self.__Name2NameList(ts)

                    if rerefsl and len(filter(lambda e: e == '..', tl)) > depth:
                        return OTSoftLink(
                            self.__NameList2Name(self.__CollapseNameList(['..']*(len(self.pathFromRoot())-1)
                                                                         + srcbranch.pathFromRoot()[1:] + tl)),
                            v.loc, v.origsource)
                    else:
                        return v
        elif isinstance(v, OTFunctionEval):
            return OTFunctionEval(self, v.funcinfo, v.loc, 
                                  [self.__CopyIn(srcbranch, e, name, rerefsl, depth)
                                   for e in v.rawvaluelist],
                                  v.name)
        elif isinstance(v, OTEvalStatement):
            return OTEvalStatement(v.string, v.loc, v.origsource,
                                   sldict = dict([(k, self.__CopyIn(srcbranch, e, name, rerefsl, depth))
                                                  for k,e in v.sldict.items()]))
        else:
            try: 
                return v.copy()
            except AttributeError:
                return v

    ######################################################################
    # Sequence stuff

    def __Function_Range(self, branch, loc, valuelist):
        from math import floor

        # Creates a list; identical behavior to arange in numpy

        if len(valuelist) == 1:
            start = 0
            end = valuelist[0]
            step = 1
        elif len(valuelist) == 2:
            start = valuelist[0]
            end = valuelist[1]
            step = 1
        elif len(valuelist) == 3:
            start = valuelist[0]
            end = valuelist[1]
            step = valuelist[2]
        elif len(valuelist) > 3:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Creating Range'),
                                         'Too many arguments for range([start, ]end[, step])')
        elif len(valuelist) == 0:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Creating Range'),
                                         'Too few arguments for range([start, ]end[, step])')

        if step == 0:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Creating Range'),
                                         'Step size of zero creates infinite sequence.')

        nsteps = int(floor((end - start)/step))

        if nsteps < 0:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Creating Range'),
                                         'Wrong sign on step size.' )

        return [start + i*step for i in xrange(nsteps)]

    def __Function_SeqRep(self, branch, valuelist, loc):
        # Unfortunately have to use valuelist here since we have to know what we're replacing
        
        vl = valuelist[0]
        replist = valuelist[1:]

        if vl == OPTTREE_NONNONEXISTANTQUERY:
            vl = []

        if type(vl) == list or type(vl) == tuple:
            for reptup in replist:
                try:
                    n, v = reptup
                except:
                    raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Evaluating List Replacer'),
                                               'Replacement directive \"' + str(reptup) + '\" must be a tuple of the form (<index>, <new value>)')

                if type(n) == int:

                    if n >= len(vl):
                        vl += [None]*(n+1 - len(vl))
                    
                    try:
                        vl[n] = v
                    except:
                        raise PyOptionTreeParseError(branch.__LocString(pos=loc,
                                                                      action='Evaluating List Replacer'),
                                                   'Replacement Index ' + str(n) + ' not valid.')
                else:
                    try:
                        exec('VariableReplacementList[' + n + '] = NewValue', {},
                             {'VariableReplacementList' : vl, 'NewValue': v})
                    except Exception, e:
                        raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Evaluating List Replacer'),
                                                   str(e))
##         elif  type(vl) == dict:
##             for reptup in replist:
##                 try:
##                     n, v = reptup
##                 except:
##                     raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Evaluating Dictionary Replacer'),
##                                                'Replacement directive \"' + str(reptup) + '\" must be a tuple of the form (<key>, <new value>)')

##                 if type(n) == int:
##                     try:
##                         vl[n] = v
##                     except:
##                         raise PyOptionTreeParseError(branch.__LocString(pos=loc,
##                                                                       action='Evaluating List Replacer'),
##                                                    'Replacement Index ' + str(n) + ' not valid.')
##                 else:
##                     try:
##                         k = self.__ReadyValue(self.__ParseValue( (0, len(n)), name, n))
##                     except PyOptionTreeException, ote:
##                         raise ote.PrependMessage(branch.__LocString(pos=loc, action='Evaluating List Replacer'))
        else:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Evaluating List Replacer'),
                                       'First argument must be list, dictionary, or tuple.')


        return vl
    
    def __Function_Dict(self, branch, valuelist, loc):
        try:
            if len(valuelist) == 1 and type(valuelist[0]) == list:
                return dict(valuelist[0])
            else:
                return dict(valuelist)
        except Exception, e:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Turning 2-Tuple list into dictionary.'),
                                       str(e))
        
    def __Function_TimeStamp(self, branch, valuelist, loc):
        if valuelist == []:
            return time.strftime('%Y-%m-%d-%H-%M')
        elif type(valuelist[0]) == str:
            return time.strftime(valuelist[0])
        else:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Creating Time Stamp'), 'Argument must be nonexistant or a string.')
    
    def __Function_Now(self, valuelist):
        if len(valuelist) == 1:
            return valuelist[0]
        elif len(valuelist) == 0:
            return None
        else:
            return valuelist

    def __Function_Unpickle(self, branch, valuelist, loc):
        if type(valuelist) == list:
            return self.__Function_WrapListEval(lambda v: self.__Function_Unpickle(branch, v, loc), valuelist)
        
        if type(valuelist) == str:
            try:
                return cPickle.load(valuelist)
            except cPickle.PicklingError, pe:
                raise PyOptionTreeRetrievalError(branch.__LocString(pos=loc, action='Unpickling File ' + str(valuelist)),
                                                 str(pe))
        else:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Unpickling File'),
                                         'All arguments must be names, or lists of names, of pickle files.')
                
    def __Function_Unpickle_string(self, branch, valuelist, loc):
        if type(valuelist) == list:
            return self.__Function_WrapListEval(lambda v: self.__Function_Unpickle_string(branch, v, loc), valuelist)
        
        if type(valuelist) == str:
            try:
                return cPickle.loads(valuelist)
            except cPickle.PicklingError, pe:
                raise PyOptionTreeRetrievalError(branch.__LocString(pos=loc, action='Unpickling String ' + str(valuelist)),
                                                 str(pe))
        else:
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Unpickling String'),
                                         'All arguments must be strings, or lists of strings.')

    def __Function_OuterProduct(self, branch, name, loc, rawvaluelist, valuelist):
        if type(valuelist) != list or len(valuelist) < 2: 
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Expanding Outer Product'),
                                         'Arguments must be of form (opttree, field1, field2,...)')

        if not isinstance(valuelist[0], PyOptionTree):
            raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Expanding Outer Product'),
                                         'First argument must be link to option tree.')

        ot = valuelist[0]

        for i, field in enumerate(valuelist[1:]):
            if type(field) != str:
                raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Expanding Outer Product'),
                                             'Argument ' + str(i+2) + ' not a string.')
            if not ot.isValid(field):
                raise PyOptionTreeParseError(branch.__LocString(pos=loc, action='Expanding Outer Product'),
                                             'Argument ' + str(i+2) + ' (\'' + str(field) + '\') not a valid field in option tree (argument 1).')

        # Okay, we've checked everything, now just expand out

        def ensureList(l):
            if type(l) == list:
                return l
            elif type(l) == tuple:
                return list(l)
            else:
                return [l]

        fllist = filter(lambda t: len(t[1]) != 0, zip(valuelist[1:], [ensureList(ot.get(f)) for f in valuelist[1:]]))
        fl = [n for n, v in fllist]
        flvals = [v for n,v in fllist]
        idxlist = [0]*len(fl)
        idxlims = [len(fv) for fv in flvals]

        def incidxlist():
            for i in reversed(xrange(len(idxlist))):
                if idxlist[i] + 1 < idxlims[i]:
                    idxlist[i] += 1
                    return False
                else:
                    idxlist[i] = 0
                if i == 0:
                    return True

        def listprod(l):
            ret = 1
            for n in l: ret *= n
            return ret

        otret = [branch.__CopyIn(None, rawvaluelist[0], name + '[' + str(i) + ']')
                 for i in xrange(listprod(idxlims))]

        idx = 0
        while True:
            
            for i in xrange(len(idxlist)):
                otret[idx].__SetValue(fl[i], flvals[i][idxlist[i]])

            idx += 1
            
            if incidxlist():
                break

        return otret

    def __Function_Rep(self, name, loc, branch, valuelist):

        if type(valuelist) == list:
            ret = [self.__Function_Rep(name, loc, branch, l) for l in valuelist]
            if len(ret) == 1:
                return ret[0]
            else:
                return ret
        elif type(valuelist) == str:

            s =  valuelist
            sl = list(valuelist)

            try:
                pairs = branch.__FindPairs(s, None, '$(', ')') + branch.__FindPairs(s, None, '${', '}')
            except PyOptionTreeException, ote:
                errs = branch.__LocString(loc, action = 'Tying Variables in String Replacement')
                raise ote.PrependMessage(errs)

            vdict = {}

            #self.__dbprint('OT_FUNCTION_STRREP> Pairlist = ' + str(pairs))

            for p in reversed(pairs):
                try:
                    sl[p[0]:p[3]] = [str(branch.get(s[p[1]:p[2]]))]
                except PyOptionTreeException, ote:
                    raise ote.PrependMessage(branch.__LocString(loc, action = 'Tying Variables in Spring Replacement'))


            return ''.join(sl)


    ######################################################################
    # Bookkeeping functions

    def __NewEscapedCharTag(self, ch):
        tag =  OTRandTag() +'_'
        self.__escaped_chars[tag] = ch;
        return self.__escaped_tag_prefix + tag

    def __OriginalString(self, a):
        # Translates a string back into its original form

        if type(a) == str:
            s = a
        elif type(a) == tuple:
            s = self.__ChS()[a[0]:a[1]]
            
        sl = s.split(self.__escaped_tag_prefix)
        rs = sl[0]

        for ss in sl[1:]:
            if ss[:OPTTREE_RANDALPHALENGTH+1] in self.__escaped_chars:
                rs += self.__escaped_chars[ss[:OPTTREE_RANDALPHALENGTH+1] ] + ss[OPTTREE_RANDALPHALENGTH+1:]
            else:
                rs += ss
                    
        return rs.replace(self.__newlinetag, '\n')
       
    def __ShrinkRange(self, r, s = None, skipsemicolons=True):
        return (self.__NextNonWSPos(r[0], s, skipsemicolons), self.__FirstNonWSPos(r[1], s))

    def __NextNonWSPos(self, rl, s = None, skipsemicolons=True):
        
        if s == None:
            s = self.__ChS()

        while rl < len(s):
            if s[rl].isspace():
                rl += 1
            elif skipsemicolons and s[rl] == ';':  # We want to skip over the ; on the left, these don't matter
                rl += 1
            elif s[rl:].startswith(self.__newlinetag):
                rl += len(self.__newlinetag)
            else:
                break
            
        return rl

    def __FirstNonWSPos(self, rr, s=None):
        if s == None:
            s = self.__ChS()
        #lnlt = len(self.__newlinetag)
        while rr > 0:
            if s[rr-1].isspace():
                ##self.__dbprint('Skipping back on $' + s[rr-1] + '$')
                rr -= 1
            elif s[:rr].endswith(self.__newlinetag):
                ##self.__dbprint('Skipping back on $' + s[max(0, rr-lnlt):rr] + '$')
                rr -= len(self.__newlinetag)
            else:
                break

        return rr

    def __NextInstance(self, pos, searchmarker, endpos, st = '', hasimmunity = False):
        if st == '':
            st = self.__ChS()

        searchstack = [searchmarker]

        immunity = hasimmunity
        
        while pos < endpos:
            if type(searchstack[-1]) == str and st[pos:].startswith(searchstack[-1]):
                match = True
                jumplength = len(searchstack[-1])
            elif isinstance(searchstack[-1], OTSearchFunc) and searchstack[-1].matchfunc(st[pos:]):
                match = True
                jumplength = searchstack[-1].matchlength
            else:
                match = False

            if match: 
                if len(searchstack) == 1:
                    return pos

                searchstack.pop()
                immunity = False
                pos += jumplength
            else:
                if not immunity:
                    for k,r,im in self.__nestchars:
                        if st[pos:].startswith(k):
                            searchstack.append(r)
                            immunity = im
                            pos += len(k) - 1 
                            break
                pos += 1
            
        return endpos

    def __Len(self, s):
        if type(s) == str:
            return len(s)
        elif isinstance(s, OTSearchFunc):
            return s.matchlength
        
        

    ######################################################################
    # Error Reporting Functions
    def __LocString(self, pos=None, action = '', source = None):
        # Need to translate pos to be a tuple of two indices in l

        s = self.description() + ':\n\t'

        if type(pos) == int:
            pos = (pos, pos)
            l = self.__CiL()
            endflag = True
        elif type(pos) == list and len(pos) != 0:
            l = pos
            pos = (0, len(pos) - 1)
            endflag = False
        elif type(pos) == tuple:
            if isinstance(pos[0], OTChInfo):
                l = list(pos)
                pos = (0, 1)
                endflag = False
            else:
                l = self.__CiL()
                endflag = True
        elif isinstance(pos, OTChInfo):
            l = [pos]
            pos = (0, 0)
            endflag = False

        if source == None:
            s += 'In ' + self.__CurSource() + ':\n\t'
        else:
            s += 'In ' + source + ':\n\t'
            
        if pos != None:
            if pos[0] >= len(l) and endflag:
                s += 'End'
            elif pos[1] - pos[0] <= 1:
                s += 'Line ' + str(l[pos[0]].line) + ', Col ' + str(l[pos[0]].column)
            elif pos[1] >= len(l) and endflag:
                s += 'Line ' + str(l[pos[0]].line) + ', Col ' + str(l[pos[0]].column) + ' to End'
            else:
                l1 = str(l[pos[0]].line)
                l2 = str(l[pos[1]].line)
                c1 = str(l[pos[0]].column)
                c2 = str(l[pos[1]].column)

                if l1 == l2:
                    s += 'Line ' + str(l1) + ', Columns ' + str(c1) + '-' + str(c2)
                else:
                    s += 'Line ' + str(l1) + ', Col ' + str(c1) + ' to Line ' + str(l2) + ', Col ' + str(c2)
            s += ':\n\t'
            
        return s + action.strip() 

    def __TruncatedErrorString(self, r, length = OPTTREE_TRUNCATEDERRORSTRINGLENGTH):
        return self.__TruncateErrorString(self.__OriginalString(r), length)

    def __TruncateErrorString(self, s, length = OPTTREE_TRUNCATEDERRORSTRINGLENGTH):
        s = self.__OriginalString(s).replace('\n', '\\n')
        if len(s) > length:
            return s[0:length-2] + '...'
        else:
            return s

    def __MakeLocTag(self, r):
        return (self.__CiL()[r[0]], self.__CiL()[max(r[0], r[1]-1)])

    def __RecordSource(self, sourcename):
        # The space is really important in the next line; distinguishes from <Command Line>
        self.__sources = filter(lambda n: not n.startswith('<Command Line '), self.__sources)

        if sourcename != '':
            if sourcename.startswith('<Command Line'):
                self.__RecordSource(self, '<Command Line>')
            if sourcename in self.__sources:
                self.__sources = filter(lambda s: s != sourcename, self.__sources)
            self.__sources += [sourcename]

    def __CurSource(self):
        if self.__sources != []:
            return self.__sources[-1]
        else:
            return ''

    ######################################################################
    # Bookkeeping
    def __ChS(self):
        if self.__chstr == []:
            return self.parent().__ChS()
        else:
            return self.__chstr[-1]

    def __CiL(self):
        if self.__cilist == []:
            return self.parent().__CiL()
        else:
            return self.__cilist[-1]

    def __TypeList(self):
        if self.__types == None:
            return self.parent().__TypeList()
        else:
            return self.__types
    
    def __dbprint(self, s):
        if OTdebug:
            print('#######>' + self.__OriginalString(s).replace('\n', '\\n'))
    

    ####################################################################################################
    # Functions for printing the tree out.
    
    def __TurnToString(self, level=0, includeheader=True):
        # This turns the string into a set of 
        vallinks = []

        if level == 0 and includeheader:
            s = ('  '*level + '#'*40 + '\n'
                 + '  '*level + '# ' + 'Tree: ' + self.fullTreeName() + '\n'
                 + '  '*level + '# ' + time.strftime('%F %T') + '\n\n')
        else:
            s = ''
        
        for k,v,n in sorted([(k,v,n) for k, (v,n) in self.__opts.items()], key=itemgetter(2)):
            # use basestr to allow indentation in lists or tuples
            basestr = '  '*level + str(k) + ' = '
            (vs, advallinks) = self.__Value2Str(level, v,len(basestr))
            s += basestr + vs + '\n'
            vallinks += advallinks

        if level == 0:
            # Write out all the values linked to at the end of the file
            for k, vs in vallinks:
                s += '#'*50 + '\n' + k  + '=\n' + self.__Value2Str(0, vs, 0)[0] + '\n'
            return s
        else:
            return (s, vallinks)

        
    def __Value2Str(self, level, v, indentlength): 
        if type(v) == str:
            # Escape all the special characters
            return ('\'' + self.__OriginalString(v).replace('\\', '\\\\').replace('\'', '\\\'') + '\'', [])
        elif type(v) == float or type(v) == int:
            return (str(v), [])
        elif type(v) == list:
            (vs, vl) = self.__List2Str(level, v, indentlength + 1) 
            return ('[' + vs + ']', vl)
        elif type(v) == tuple:
            (vs, vl) = self.__List2Str(level, v, indentlength + 1) 
            return ('(' + vs + ')', vl)
        elif type(v) == bool:
            if v:
                return ('True', [])
            else:
                return ('False', [])
        elif v == None:
            return ('None', [])
        elif isinstance(v, OTFunctionEval):
            (vs, vl) = self.__List2Str(level, v.rawvaluelist, indentlength + len(v.funcinfo.name))
            return (v.funcinfo.name + '(' + vs + ')', vl)
        elif isinstance(v, OTSoftLink):
            return (v.string, [])
        elif isinstance(v, OTEvalStatement):
            return ('@(' + v.origsource + ')', [])
        elif isinstance(v, PyOptionTree):
            if v.size() == 0:
                return '{}'
            else:
                (rs, rv) = v.__TurnToString(level+1)
                return ('{\n' + rs + level*'  ' + '}\n', rv)
        else:
            # Pickle the result
            s = cPickle.dumps(v, 0)
            linkname = '_Pickle_' + OTRandTag()
            return ('../'*level + linkname, [(linkname, s)])
    
    def __List2Str(self, level, v, indentlength):
        if v == []:
            return ('', [])
        
        retl = []
        basers = ''
        queuedrs = ''

        for e in v[:-1]:
            (rs, rl) = self.__Value2Str(level, e, indentlength+len(queuedrs))
            retl += rl
            queuedrs += rs

            if len(queuedrs) + indentlength+1 > OPTTREE_TARGETPRINTLINELENGTH:
                basers += queuedrs + ',\n' + ' '*indentlength
                queuedrs = ' '
            else:
                queuedrs += ', '

        (rs, rl) = self.__Value2Str(level, v[-1], indentlength+len(queuedrs))

        return (basers + queuedrs + rs, retl + rl)

## class PyOptionStruct:
##     """
##     This class is just a trimmed-down, optimized version of the
##     PyOptionStruct that uses only the bare minimum to keep access
##     fast.  It is created using the toStruct() method of the option
##     tree, at which time all variables are realized and stored in this
##     structure.  Thus all changes to this structure are completely
##     local.
##     """
