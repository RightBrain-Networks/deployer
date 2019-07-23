import unittest
import __init__ as deployer
import sys, subprocess

try:
    from StringIO import StringIO
except ImportError:
    from io import StringIO



class DeployerTestCase(unittest.TestCase):
    def test_version(self):
        #Checks if -v returns the version stored in the python file
        v = ""
        from deployer import __version__ 
        try:
            v = subprocess.check_output(['python', 'deployer/__init__.py', '-v']).rstrip()
        except SystemExit as exit:
            if exit.code != 0:
                raise exit
        self.assertEqual(__version__, v)

    def test_help(self):
        #Checks if -h returns the help message
        output = ""
        try:
            output = subprocess.check_output(['python', 'deployer/__init__.py', '-h'])
        except SystemExit as exit:
            if exit.code != 0:
                raise exit
        self.assertTrue("show this help message and exit" in output)

    def test_intialize(self):
        pass




def main():
    unittest.main()

if __name__ == "__main__":
    main()