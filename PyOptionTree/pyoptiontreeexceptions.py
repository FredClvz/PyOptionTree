#######################################################################
# Exceptions for the exception-based error reporting system.

class PyOptionTreeException(Exception):
    """
    The base class for all exceptions.  Use str(<exception instance>)
    to retrieve the error. 
    """

    def __init__(self, message, a):
        self.SetInitMessage(message,a)
    def SetInitMessage(self, message, a): 
        if a == '': 
            self.message = message 
        else: 
            self.message = message + ':' + str(a) 
    def PrependMessage(self,message): 
        self.message = message + ':\n' + self.message 
        return self 
    def __str__(self):
        return '\n\n' + self.message 

class PyOptionTreeParseError(PyOptionTreeException):
    """
    The exception class raised when the parser encounters an error
    while parsing the file.
    """
    
    def __init__(self, a1, a2):
        self.SetInitMessage(a1,'\n' +a2)

class PyOptionTreeRetrievalError(PyOptionTreeException):
    """
    The exception class raised when an error is encountered retrieving
    a value.
    """
    def __init__(self, a1, a2):
        self.SetInitMessage(a1,'\n'+ a2)
        
class PyOptionTreeEvaluationError(PyOptionTreeException):
    """
    The exception class raieed when any error is encountered
    evaluating a piece of Python code embedded in the option tree
    file.
    """
    
    def __init__(self, a1, a2):
        self.SetInitMessage(a1,'\n' + a2)
