import logging
import subprocess

# create logger
logger = logging.getLogger('simple_example')
logger.setLevel(logging.DEBUG)

# create console handler and set level to INFO
console_logger = logging.StreamHandler()
console_logger.setLevel(logging.INFO)

# create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# add formatter to console_logger
console_logger.setFormatter(formatter)

# add console_logger to logger
logger.addHandler(console_logger)

def update_colors(color_dictionary):
    subprocess.call('', shell=True) # Called to enable ANSI encoding on Windows
    escape_code = u'\033'

    color_dictionary['error'] = escape_code + u'[91m'
    color_dictionary['debug'] = escape_code + u'[3;35m'
    color_dictionary['info'] = escape_code + u'[3m'
    color_dictionary['warning'] = escape_code + u'[1;33m'
    color_dictionary['stack'] = escape_code + u'[1;93m'
    color_dictionary['underline'] = escape_code + u'[4m'
    color_dictionary['reset'] = escape_code + u'[0m'