import logging

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
    color_dictionary['error'] = '\033[91m'
    color_dictionary['debug'] = '\033[3;35m'
    color_dictionary['info'] = '\033[3m'
    color_dictionary['warning'] = '\033[1;33m'
    color_dictionary['stack'] = '\033[1;93m'
    color_dictionary['underline'] = '\033[4m'
    color_dictionary['reset'] = '\033[0m'