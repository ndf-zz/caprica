
# Imports
import argparse

# Config
VERSION = '1.0.0'
DEFPORT = 16372

def main():
    parser = argparse.ArgumentParser(description='Galactica/DHI Replacement')
    parser.add_argument('-p', '--port', help='DHI port number (default 16372)',
                        type=int, default=DEFPORT)
    parser.add_argument('-v', '--version', help='print version',
                        action='version',
                        version='%(prog)s ' + VERSION)
    args = parser.parse_args()

if __name__ == '__main__':
    main()
