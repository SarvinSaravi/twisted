# -*- test-case-name: twisted.trial.test -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Infrastructure for test running and suites.
"""

import doctest
import warnings, gc

from twisted.python import components

from twisted.trial import itrial, reporter
from twisted.trial._synctest import _logObserver

pyunit = __import__('unittest')

from zope.interface import implements

def suiteVisit(suite, visitor):
    """
    Visit each test in C{suite} with C{visitor}.

    Deprecated in Twisted 8.0.

    @param visitor: A callable which takes a single argument, the L{TestCase}
    instance to visit.
    @return: None
    """
    warnings.warn("Test visitors deprecated in Twisted 8.0",
                  category=DeprecationWarning)
    for case in suite._tests:
        visit = getattr(case, 'visit', None)
        if visit is not None:
            visit(visitor)
        elif isinstance(case, pyunit.TestCase):
            case = itrial.ITestCase(case)
            case.visit(visitor)
        elif isinstance(case, pyunit.TestSuite):
            suiteVisit(case, visitor)
        else:
            case.visit(visitor)



class TestSuite(pyunit.TestSuite):
    """
    Extend the standard library's C{TestSuite} with support for the visitor
    pattern and a consistently overrideable C{run} method.
    """

    visit = suiteVisit

    def __call__(self, result):
        return self.run(result)


    def run(self, result):
        """
        Call C{run} on every member of the suite.
        """
        # we implement this because Python 2.3 unittest defines this code
        # in __call__, whereas 2.4 defines the code in run.
        for test in self._tests:
            if result.shouldStop:
                break
            test(result)
        return result



class TestDecorator(components.proxyForInterface(itrial.ITestCase,
                                                 "_originalTest")):
    """
    Decorator for test cases.

    @param _originalTest: The wrapped instance of test.
    @type _originalTest: A provider of L{itrial.ITestCase}
    """

    implements(itrial.ITestCase)


    def __call__(self, result):
        """
        Run the unit test.

        @param result: A TestResult object.
        """
        return self.run(result)


    def run(self, result):
        """
        Run the unit test.

        @param result: A TestResult object.
        """
        return self._originalTest.run(
            reporter._AdaptedReporter(result, self.__class__))



def _clearSuite(suite):
    """
    Clear all tests from C{suite}.

    This messes with the internals of C{suite}. In particular, it assumes that
    the suite keeps all of its tests in a list in an instance variable called
    C{_tests}.
    """
    suite._tests = []


def decorate(test, decorator):
    """
    Decorate all test cases in C{test} with C{decorator}.

    C{test} can be a test case or a test suite. If it is a test suite, then the
    structure of the suite is preserved.

    L{decorate} tries to preserve the class of the test suites it finds, but
    assumes the presence of the C{_tests} attribute on the suite.

    @param test: The C{TestCase} or C{TestSuite} to decorate.

    @param decorator: A unary callable used to decorate C{TestCase}s.

    @return: A decorated C{TestCase} or a C{TestSuite} containing decorated
        C{TestCase}s.
    """

    try:
        tests = iter(test)
    except TypeError:
        return decorator(test)

    # At this point, we know that 'test' is a test suite.
    _clearSuite(test)

    for case in tests:
        test.addTest(decorate(case, decorator))
    return test



class _PyUnitTestCaseAdapter(TestDecorator):
    """
    Adapt from pyunit.TestCase to ITestCase.
    """


    def visit(self, visitor):
        """
        Deprecated in Twisted 8.0.
        """
        warnings.warn("Test visitors deprecated in Twisted 8.0",
                      category=DeprecationWarning)
        visitor(self)



class _BrokenIDTestCaseAdapter(_PyUnitTestCaseAdapter):
    """
    Adapter for pyunit-style C{TestCase} subclasses that have undesirable id()
    methods. That is C{unittest.FunctionTestCase} and C{unittest.DocTestCase}.
    """

    def id(self):
        """
        Return the fully-qualified Python name of the doctest.
        """
        testID = self._originalTest.shortDescription()
        if testID is not None:
            return testID
        return self._originalTest.id()



class _ForceGarbageCollectionDecorator(TestDecorator):
    """
    Forces garbage collection to be run before and after the test. Any errors
    logged during the post-test collection are added to the test result as
    errors.
    """

    def run(self, result):
        gc.collect()
        TestDecorator.run(self, result)
        _logObserver._add()
        gc.collect()
        for error in _logObserver.getErrors():
            result.addError(self, error)
        _logObserver.flushErrors()
        _logObserver._remove()


components.registerAdapter(
    _PyUnitTestCaseAdapter, pyunit.TestCase, itrial.ITestCase)


components.registerAdapter(
    _BrokenIDTestCaseAdapter, pyunit.FunctionTestCase, itrial.ITestCase)


_docTestCase = getattr(doctest, 'DocTestCase', None)
if _docTestCase:
    components.registerAdapter(
        _BrokenIDTestCaseAdapter, _docTestCase, itrial.ITestCase)


def iterateTests(testSuiteOrCase):
    """
    Iterate through all of the test cases in C{testSuiteOrCase}.
    """
    try:
        suite = iter(testSuiteOrCase)
    except TypeError:
        yield testSuiteOrCase
    else:
        for test in suite:
            for subtest in iterateTests(test):
                yield subtest



# Support for Python 2.3
try:
    iter(pyunit.TestSuite())
except TypeError:
    # Python 2.3's TestSuite doesn't support iteration. Let's monkey patch it!
    def __iter__(self):
        return iter(self._tests)
    pyunit.TestSuite.__iter__ = __iter__
