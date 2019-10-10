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
    #escape_code = '\033'
    escape_code = '\027'

    color_dictionary['error'] = escape_code + '[91m'
    color_dictionary['debug'] = escape_code + '[3;35m'
    color_dictionary['info'] = escape_code + '[3m'
    color_dictionary['warning'] = escape_code + '[1;33m'
    color_dictionary['stack'] = escape_code + '[1;93m'
    color_dictionary['underline'] = escape_code + '[4m'
    color_dictionary['reset'] = escape_code + '[0m'